"""Trade journal persistence for the Python layer.

Unlike the ``metrics`` table — which the Rust engine owns and writes — the trade
journal is authored and consumed by this Python + Claude-agent layer, so this
module owns its schema. Entries live in the same SQLite database as the metrics
(the ``METRICS_DB`` path) so each trade can be joined to the microstructure
regime that was in force when it was entered.

Everything here is plain ``sqlite3`` and free functions, matching the read layer
in ``backtest.api``.
"""

import csv
import sqlite3
import time
from collections.abc import Sequence
from pathlib import Path
from typing import Any

# Fields the caller supplies for a new entry. The store manages ``id`` (an
# autoincrement surrogate key) and ``created_at_ns`` (insertion time). These are
# also the only columns an update is allowed to touch.
_INPUT_COLUMNS = (
    "symbol",
    "side",
    "entered_at_ns",
    "exited_at_ns",
    "entry_price",
    "exit_price",
    "size",
    "pnl",
    "notes",
    "emotion",
)
_UPDATABLE_COLUMNS = frozenset(_INPUT_COLUMNS)

# Full column set returned when reading a row back.
_ROW_COLUMNS = ("id", *_INPUT_COLUMNS, "created_at_ns")

# Regime columns attached to each entry by ``list_enriched`` / ``get_entry``.
# Present (possibly ``None``) on every enriched row so consumers see a stable shape.
_REGIME_COLUMNS = (
    "regime_bucket_start_ns",
    "regime_window_ns",
    "regime_ofi",
    "regime_realized_volatility",
    "regime_vwap",
)

_INT_FIELDS = frozenset({"entered_at_ns", "exited_at_ns", "size"})
_FLOAT_FIELDS = frozenset({"entry_price", "exit_price", "pnl"})

# SELECT..FROM for a plain read and for a regime-enriched read. The enriched read
# picks, per entry, the metric bucket whose window contains the entry time; when
# several window sizes coexist it prefers the finest (smallest) window. A LEFT
# JOIN leaves the regime columns NULL when no bucket matches (or metrics is empty).
_PLAIN_SELECT = f"SELECT {', '.join(_ROW_COLUMNS)} FROM journal_entries"

_ENRICHED_SELECT = f"""
SELECT
    {", ".join("j." + c for c in _ROW_COLUMNS)},
    r.bucket_start_ns     AS regime_bucket_start_ns,
    r.window_ns           AS regime_window_ns,
    r.ofi                 AS regime_ofi,
    r.realized_volatility AS regime_realized_volatility,
    r.vwap                AS regime_vwap
FROM journal_entries j
LEFT JOIN metrics r ON r.rowid = (
    SELECT m.rowid FROM metrics m
    WHERE m.bucket_start_ns <= j.entered_at_ns
      AND j.entered_at_ns < m.bucket_start_ns + m.window_ns
    ORDER BY m.window_ns ASC, m.bucket_start_ns DESC
    LIMIT 1
)
"""

# INSERT for one row: the caller-supplied columns plus the managed created_at_ns.
_INSERT_SQL = (
    f"INSERT INTO journal_entries ({', '.join(_INPUT_COLUMNS)}, created_at_ns) "
    f"VALUES ({', '.join(['?'] * (len(_INPUT_COLUMNS) + 1))})"
)


class InvalidEntryUpdate(ValueError):
    """Raised when a partial update would leave the stored entry inconsistent.

    Specifically, when the resulting ``exited_at_ns`` would fall before
    ``entered_at_ns`` once the update is applied to the stored row. The API maps
    this to a 422.
    """


def init_db(conn: sqlite3.Connection) -> None:
    """Create the ``journal_entries`` table if it does not already exist."""
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS journal_entries (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            symbol        TEXT    NOT NULL,
            side          TEXT    NOT NULL,
            entered_at_ns INTEGER NOT NULL,
            exited_at_ns  INTEGER,
            entry_price   REAL    NOT NULL,
            exit_price    REAL,
            size          INTEGER NOT NULL,
            pnl           REAL,
            notes         TEXT,
            emotion       TEXT,
            created_at_ns INTEGER NOT NULL
        )
        """
    )


def insert_entry(path: str | Path, entry: dict[str, Any]) -> dict[str, Any]:
    """Insert a journal entry, returning the stored row (including its ``id``).

    Missing optional fields default to ``None``; the required NOT NULL columns
    must be present or SQLite raises ``IntegrityError``.
    """
    values = tuple(entry.get(col) for col in _INPUT_COLUMNS)
    with sqlite3.connect(path) as conn:
        conn.row_factory = sqlite3.Row
        init_db(conn)
        cursor = conn.execute(_INSERT_SQL, (*values, time.time_ns()))
        stored = conn.execute(
            f"SELECT {', '.join(_ROW_COLUMNS)} FROM journal_entries WHERE id = ?",
            (cursor.lastrowid,),
        ).fetchone()
    return dict(stored)


def get_entry(path: str | Path, entry_id: int) -> dict[str, Any] | None:
    """Return one journal entry (regime-enriched) by id, or ``None`` if absent."""
    path = Path(path)
    if not path.exists():
        return None
    with sqlite3.connect(path) as conn:
        conn.row_factory = sqlite3.Row
        try:
            if _has_metrics_table(conn):
                query = f"{_ENRICHED_SELECT} WHERE j.id = ?"
            else:
                query = f"{_PLAIN_SELECT} WHERE id = ?"
            row = conn.execute(query, (entry_id,)).fetchone()
        except sqlite3.OperationalError:
            return None
    return _with_regime(row) if row is not None else None


def update_entry(path: str | Path, entry_id: int, fields: dict[str, Any]) -> dict[str, Any] | None:
    """Apply a partial update to an entry, returning the updated (enriched) row.

    Only recognised, mutable columns in ``fields`` are written; ``id`` and
    ``created_at_ns`` are never touched. Returns ``None`` if the entry does not
    exist. An empty update is a no-op that returns the current row.

    The time-ordering rule (``exited_at_ns`` >= ``entered_at_ns``) is enforced
    against the *stored* row: a partial update touching only one endpoint is
    checked against the other as it already stands, raising
    :class:`InvalidEntryUpdate` if the result would put the exit before the
    entry. Nothing is written in that case.
    """
    updates = {col: value for col, value in fields.items() if col in _UPDATABLE_COLUMNS}
    if not updates:
        return get_entry(path, entry_id)
    path = Path(path)
    if not path.exists():
        return None
    assignments = ", ".join(f"{col} = ?" for col in updates)
    with sqlite3.connect(path) as conn:
        conn.row_factory = sqlite3.Row
        try:
            current = conn.execute(
                "SELECT entered_at_ns, exited_at_ns FROM journal_entries WHERE id = ?",
                (entry_id,),
            ).fetchone()
        except sqlite3.OperationalError:
            return None
        if current is None:
            return None
        _check_times_ordered(updates, current)
        conn.execute(
            f"UPDATE journal_entries SET {assignments} WHERE id = ?",
            (*updates.values(), entry_id),
        )
    return get_entry(path, entry_id)


def delete_entry(path: str | Path, entry_id: int) -> bool:
    """Delete an entry by id, returning ``True`` if a row was removed."""
    path = Path(path)
    if not path.exists():
        return False
    with sqlite3.connect(path) as conn:
        try:
            cursor = conn.execute("DELETE FROM journal_entries WHERE id = ?", (entry_id,))
        except sqlite3.OperationalError:
            return False
    return cursor.rowcount > 0


def list_entries(
    path: str | Path,
    limit: int,
    *,
    since_ns: int | None = None,
    until_ns: int | None = None,
) -> list[dict[str, Any]]:
    """Return journal entries newest first, optionally bounded by entry time.

    ``since_ns`` is inclusive, ``until_ns`` exclusive. Empty if none / no DB.
    """
    query, params = _build_list_query(_PLAIN_SELECT, "entered_at_ns", since_ns, until_ns)
    return _read(path, query, (*params, limit))


def list_enriched(
    path: str | Path,
    limit: int,
    *,
    since_ns: int | None = None,
    until_ns: int | None = None,
) -> list[dict[str, Any]]:
    """Return journal entries newest first, each joined to its market regime.

    Every row carries the ``regime_*`` columns; they are ``None`` when the
    metrics table is missing/empty or no bucket covers the entry time. ``since_ns``
    is inclusive and ``until_ns`` exclusive. This is the join that lets the agent
    correlate behavior with the microstructure context at the time of each trade.
    """
    path = Path(path)
    if not path.exists():
        return []
    with sqlite3.connect(path) as conn:
        conn.row_factory = sqlite3.Row
        try:
            if _has_metrics_table(conn):
                query, params = _build_list_query(
                    _ENRICHED_SELECT, "j.entered_at_ns", since_ns, until_ns
                )
            else:
                query, params = _build_list_query(
                    _PLAIN_SELECT, "entered_at_ns", since_ns, until_ns
                )
            rows = conn.execute(query, (*params, limit)).fetchall()
        except sqlite3.OperationalError:
            return []
    return [_with_regime(row) for row in rows]


def import_csv(csv_path: str | Path, path: str | Path) -> int:
    """Bulk-load journal entries from a CSV, returning the number inserted.

    Used to seed the synthetic sample journal. Empty cells become ``None``;
    numeric columns are coerced to int/float.
    """
    with open(csv_path, newline="") as handle:
        rows = list(csv.DictReader(handle))
    with sqlite3.connect(path) as conn:
        init_db(conn)
        for row in rows:
            values = tuple(_coerce(col, row.get(col)) for col in _INPUT_COLUMNS)
            conn.execute(_INSERT_SQL, (*values, time.time_ns()))
    return len(rows)


def _build_list_query(
    select: str, time_column: str, since_ns: int | None, until_ns: int | None
) -> tuple[str, list[Any]]:
    clauses: list[str] = []
    params: list[Any] = []
    if since_ns is not None:
        clauses.append(f"{time_column} >= ?")
        params.append(since_ns)
    if until_ns is not None:
        clauses.append(f"{time_column} < ?")
        params.append(until_ns)
    where = f" WHERE {' AND '.join(clauses)}" if clauses else ""
    return f"{select}{where} ORDER BY {time_column} DESC LIMIT ?", params


def _check_times_ordered(updates: dict[str, Any], current: sqlite3.Row) -> None:
    """Raise :class:`InvalidEntryUpdate` if applying ``updates`` to ``current``
    would put ``exited_at_ns`` before ``entered_at_ns``.

    Each endpoint takes its updated value if present, else the stored one; the
    check is skipped when the effective exit is ``None`` (an open position).
    """
    entered = updates.get("entered_at_ns", current["entered_at_ns"])
    exited = updates.get("exited_at_ns", current["exited_at_ns"])
    if entered is not None and exited is not None and exited < entered:
        raise InvalidEntryUpdate("exited_at_ns must be >= entered_at_ns")


def _read(path: str | Path, query: str, params: Sequence[Any]) -> list[dict[str, Any]]:
    path = Path(path)
    if not path.exists():
        return []
    with sqlite3.connect(path) as conn:
        conn.row_factory = sqlite3.Row
        try:
            rows = conn.execute(query, params).fetchall()
        except sqlite3.OperationalError:
            return []
    return [dict(row) for row in rows]


def _with_regime(row: sqlite3.Row) -> dict[str, Any]:
    record = dict(row)
    for column in _REGIME_COLUMNS:
        record.setdefault(column, None)
    return record


def _has_metrics_table(conn: sqlite3.Connection) -> bool:
    row = conn.execute(
        "SELECT name FROM sqlite_master WHERE type = 'table' AND name = 'metrics'"
    ).fetchone()
    return row is not None


def _coerce(field: str, raw: str | None) -> Any:
    if raw is None or raw == "":
        return None
    if field in _INT_FIELDS:
        return int(raw)
    if field in _FLOAT_FIELDS:
        return float(raw)
    return raw
