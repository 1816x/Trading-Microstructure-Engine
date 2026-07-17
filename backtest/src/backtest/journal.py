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
from pathlib import Path
from typing import Any

# Fields the caller supplies for a new entry. The store manages ``id`` (an
# autoincrement surrogate key) and ``created_at_ns`` (insertion time).
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

# Full column set returned when reading a row back.
_ROW_COLUMNS = ("id", *_INPUT_COLUMNS, "created_at_ns")

# Regime columns attached to each entry by ``list_enriched``. Present (possibly
# ``None``) on every enriched row so downstream consumers see a stable shape.
_REGIME_COLUMNS = (
    "regime_bucket_start_ns",
    "regime_window_ns",
    "regime_ofi",
    "regime_realized_volatility",
    "regime_vwap",
)

_INT_FIELDS = frozenset({"entered_at_ns", "exited_at_ns", "size"})
_FLOAT_FIELDS = frozenset({"entry_price", "exit_price", "pnl"})

# For each journal entry, pick the metric bucket whose window contains the entry
# time. When several window sizes coexist, prefer the finest (smallest window),
# which describes the regime most tightly. A LEFT JOIN leaves the regime columns
# ``NULL`` when no bucket matches (or the metrics table is empty).
_ENRICHED_QUERY = f"""
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
ORDER BY j.entered_at_ns DESC
LIMIT ?
"""

_PLAIN_QUERY = (
    f"SELECT {', '.join(_ROW_COLUMNS)} FROM journal_entries ORDER BY entered_at_ns DESC LIMIT ?"
)


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
    created_at_ns = time.time_ns()
    placeholders = ", ".join(["?"] * (len(_INPUT_COLUMNS) + 1))
    with sqlite3.connect(path) as conn:
        conn.row_factory = sqlite3.Row
        init_db(conn)
        cursor = conn.execute(
            f"INSERT INTO journal_entries ({', '.join(_INPUT_COLUMNS)}, created_at_ns) "
            f"VALUES ({placeholders})",
            (*values, created_at_ns),
        )
        stored = conn.execute(
            f"SELECT {', '.join(_ROW_COLUMNS)} FROM journal_entries WHERE id = ?",
            (cursor.lastrowid,),
        ).fetchone()
    return dict(stored)


def list_entries(path: str | Path, limit: int) -> list[dict[str, Any]]:
    """Return journal entries newest first (by entry time). Empty if none yet."""
    return _read(path, _PLAIN_QUERY, limit)


def list_enriched(path: str | Path, limit: int) -> list[dict[str, Any]]:
    """Return journal entries newest first, each joined to its market regime.

    Every row carries the ``regime_*`` columns; they are ``None`` when the
    metrics table is missing/empty or no bucket covers the entry time. This is
    the join that lets the agent correlate behavior with the microstructure
    context at the time of each trade.
    """
    path = Path(path)
    if not path.exists():
        return []
    with sqlite3.connect(path) as conn:
        conn.row_factory = sqlite3.Row
        try:
            query = _ENRICHED_QUERY if _has_metrics_table(conn) else _PLAIN_QUERY
            rows = conn.execute(query, (limit,)).fetchall()
        except sqlite3.OperationalError:
            return []
    enriched: list[dict[str, Any]] = []
    for row in rows:
        record = dict(row)
        for column in _REGIME_COLUMNS:
            record.setdefault(column, None)
        enriched.append(record)
    return enriched


def import_csv(csv_path: str | Path, path: str | Path) -> int:
    """Bulk-load journal entries from a CSV, returning the number inserted.

    Used to seed the synthetic sample journal. Empty cells become ``None``;
    numeric columns are coerced to int/float.
    """
    with open(csv_path, newline="") as handle:
        rows = list(csv.DictReader(handle))
    created_at_ns = time.time_ns()
    placeholders = ", ".join(["?"] * (len(_INPUT_COLUMNS) + 1))
    statement = (
        f"INSERT INTO journal_entries ({', '.join(_INPUT_COLUMNS)}, created_at_ns) "
        f"VALUES ({placeholders})"
    )
    with sqlite3.connect(path) as conn:
        init_db(conn)
        for row in rows:
            values = tuple(_coerce(col, row.get(col)) for col in _INPUT_COLUMNS)
            conn.execute(statement, (*values, created_at_ns))
    return len(rows)


def _read(path: str | Path, query: str, limit: int) -> list[dict[str, Any]]:
    path = Path(path)
    if not path.exists():
        return []
    with sqlite3.connect(path) as conn:
        conn.row_factory = sqlite3.Row
        try:
            rows = conn.execute(query, (limit,)).fetchall()
        except sqlite3.OperationalError:
            return []
    return [dict(row) for row in rows]


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
