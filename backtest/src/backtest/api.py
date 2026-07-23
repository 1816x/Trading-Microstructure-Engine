"""API over the metrics database and the trade journal.

The metrics endpoints are read-only: the Rust engine owns that schema and this
layer only exposes it. The journal endpoints (Phase 3) are read/write — the
journal is owned by this Python layer and stored alongside the metrics in the
same database, so entries can be joined to the market regime at entry time. Point
the app at a database with the METRICS_DB environment variable (default:
metrics.db in the working directory).

Note on timestamps: every `*_ns` field is serialized as a JSON integer, and these
nanosecond epochs (~1.76e18) exceed JavaScript's safe-integer range (2^53 ≈ 9e15).
A JS client (the Phase 4 dashboard) must read them as strings/BigInt to avoid
precision loss. This is left as a Phase 4 concern to keep the Phase 1–3 contract
unchanged.
"""

import os
import sqlite3
from pathlib import Path
from typing import Annotated, Any, Literal

from fastapi import Depends, FastAPI, HTTPException, Query
from pydantic import BaseModel, Field, model_validator

from backtest import coach, journal

DB_PATH_ENV = "METRICS_DB"

app = FastAPI(title="Trading Microstructure Engine API")


class JournalEntryIn(BaseModel):
    """A trade the user is logging to their journal."""

    symbol: str = Field(min_length=1)
    side: Literal["long", "short"]
    entered_at_ns: int = Field(gt=0)
    entry_price: float = Field(gt=0)
    size: int = Field(gt=0)
    exited_at_ns: int | None = Field(default=None, gt=0)
    exit_price: float | None = Field(default=None, gt=0)
    pnl: float | None = None
    notes: str | None = None
    emotion: str | None = None

    @model_validator(mode="after")
    def _check_exit_after_entry(self) -> "JournalEntryIn":
        if self.exited_at_ns is not None and self.exited_at_ns < self.entered_at_ns:
            raise ValueError("exited_at_ns must be >= entered_at_ns")
        return self


class JournalEntryPatch(BaseModel):
    """A partial update to a journal entry — only the provided fields change."""

    symbol: str | None = Field(default=None, min_length=1)
    side: Literal["long", "short"] | None = None
    entered_at_ns: int | None = Field(default=None, gt=0)
    entry_price: float | None = Field(default=None, gt=0)
    size: int | None = Field(default=None, gt=0)
    exited_at_ns: int | None = Field(default=None, gt=0)
    exit_price: float | None = Field(default=None, gt=0)
    pnl: float | None = None
    notes: str | None = None
    emotion: str | None = None

    @model_validator(mode="after")
    def _validate(self) -> "JournalEntryPatch":
        if not self.model_fields_set:
            raise ValueError("at least one field must be provided")
        if (
            {"entered_at_ns", "exited_at_ns"} <= self.model_fields_set
            and self.entered_at_ns is not None
            and self.exited_at_ns is not None
            and self.exited_at_ns < self.entered_at_ns
        ):
            raise ValueError("exited_at_ns must be >= entered_at_ns")
        return self


def get_anthropic_client() -> Any:
    """Provide an Anthropic client, or 503 when no API key is configured.

    Overridable in tests via ``app.dependency_overrides`` so the behavioral
    endpoint can be exercised without a real key or network access.
    """
    if not os.environ.get("ANTHROPIC_API_KEY"):
        raise HTTPException(
            status_code=503,
            detail="ANTHROPIC_API_KEY is not set — the behavioral agent is unavailable",
        )
    import anthropic

    return anthropic.Anthropic()


def _db_path() -> Path:
    return Path(os.environ.get(DB_PATH_ENV, "metrics.db"))


def _query_metrics(columns: str, limit: int) -> list[dict[str, Any]]:
    """Return `columns` from the newest metric buckets, newest first.

    Shared by every endpoint: they differ only in which columns they project
    out of the single `metrics` table the engine writes.
    """
    path = _db_path()
    if not path.exists():
        raise HTTPException(
            status_code=503,
            detail=f"metrics database not found at '{path}' — run the engine first",
        )
    with sqlite3.connect(path) as conn:
        conn.row_factory = sqlite3.Row
        try:
            rows = conn.execute(
                f"SELECT {columns} FROM metrics ORDER BY bucket_start_ns DESC LIMIT ?",
                (limit,),
            ).fetchall()
        except sqlite3.OperationalError as exc:
            raise HTTPException(
                status_code=503,
                detail=f"metrics database at '{path}' has no metrics yet: {exc}",
            ) from exc
    return [dict(row) for row in rows]


@app.get("/metrics/ofi")
def get_ofi(limit: int = Query(default=100, ge=1, le=10_000)) -> list[dict[str, Any]]:
    """Return the most recent order-flow-imbalance buckets, newest first."""
    return _query_metrics("bucket_start_ns, window_ns, buy_volume, sell_volume, ofi", limit)


@app.get("/metrics/volatility")
def get_volatility(limit: int = Query(default=100, ge=1, le=10_000)) -> list[dict[str, Any]]:
    """Return the most recent realized-volatility buckets, newest first."""
    return _query_metrics("bucket_start_ns, window_ns, realized_volatility, trade_count", limit)


@app.get("/metrics/volume")
def get_volume(limit: int = Query(default=100, ge=1, le=10_000)) -> list[dict[str, Any]]:
    """Return the most recent volume buckets (with VWAP), newest first."""
    return _query_metrics(
        "bucket_start_ns, window_ns, buy_volume, sell_volume, total_volume, vwap, trade_count",
        limit,
    )


@app.post("/journal", status_code=201)
def create_journal_entry(entry: JournalEntryIn) -> dict[str, Any]:
    """Log a trade to the journal, returning the stored row (with its id)."""
    return journal.insert_entry(_db_path(), entry.model_dump())


@app.get("/journal")
def get_journal(
    limit: int = Query(default=100, ge=1, le=10_000),
    since_ns: int | None = Query(default=None),
    until_ns: int | None = Query(default=None),
) -> list[dict[str, Any]]:
    """Return journal entries newest first, each joined to its market regime.

    ``since_ns`` (inclusive) and ``until_ns`` (exclusive) bound the entry time.
    An empty journal (or a database that does not exist yet) returns ``[]`` —
    unlike the metrics endpoints, the journal is created by this layer, so
    "no entries yet" is a normal state rather than a 503.
    """
    return journal.list_enriched(_db_path(), limit, since_ns=since_ns, until_ns=until_ns)


@app.get("/journal/{entry_id}")
def get_journal_entry(entry_id: int) -> dict[str, Any]:
    """Return one journal entry (joined to its market regime), or 404."""
    entry = journal.get_entry(_db_path(), entry_id)
    if entry is None:
        raise HTTPException(status_code=404, detail=f"journal entry {entry_id} not found")
    return entry


@app.patch("/journal/{entry_id}")
def patch_journal_entry(entry_id: int, patch: JournalEntryPatch) -> dict[str, Any]:
    """Apply a partial update to a journal entry, returning the updated row.

    Returns 422 when the update would put the exit before the entry once applied
    to the stored row (checked even if only one timestamp is in the body).
    """
    try:
        updated = journal.update_entry(_db_path(), entry_id, patch.model_dump(exclude_unset=True))
    except journal.InvalidEntryUpdate as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    if updated is None:
        raise HTTPException(status_code=404, detail=f"journal entry {entry_id} not found")
    return updated


@app.delete("/journal/{entry_id}", status_code=204)
def delete_journal_entry(entry_id: int) -> None:
    """Delete a journal entry by id (204 on success, 404 if absent)."""
    if not journal.delete_entry(_db_path(), entry_id):
        raise HTTPException(status_code=404, detail=f"journal entry {entry_id} not found")


@app.post("/journal/analyze")
def analyze_journal(
    client: Annotated[Any, Depends(get_anthropic_client)],
    limit: int = Query(default=100, ge=1, le=10_000),
    since_ns: int | None = Query(default=None),
    until_ns: int | None = Query(default=None),
) -> coach.BehavioralAnalysis:
    """Run the Claude behavioral-analysis agent over the journal.

    Returns 502 when the model declines or yields no structured analysis.
    """
    entries = journal.list_enriched(_db_path(), limit, since_ns=since_ns, until_ns=until_ns)
    try:
        return coach.analyze(entries, client=client)
    except coach.AnalysisUnavailable as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
