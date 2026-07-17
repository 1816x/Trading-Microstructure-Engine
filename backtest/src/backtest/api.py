"""API over the metrics database and the trade journal.

The metrics endpoints are read-only: the Rust engine owns that schema and this
layer only exposes it. The journal endpoints (Phase 3) are read/write — the
journal is owned by this Python layer and stored alongside the metrics in the
same database, so entries can be joined to the market regime at entry time. Point
the app at a database with the METRICS_DB environment variable (default:
metrics.db in the working directory).
"""

import os
import sqlite3
from pathlib import Path
from typing import Annotated, Any

from fastapi import Depends, FastAPI, HTTPException, Query
from pydantic import BaseModel

from backtest import coach, journal

DB_PATH_ENV = "METRICS_DB"

app = FastAPI(title="Trading Microstructure Engine API")


class JournalEntryIn(BaseModel):
    """A trade the user is logging to their journal."""

    symbol: str
    side: str
    entered_at_ns: int
    entry_price: float
    size: int
    exited_at_ns: int | None = None
    exit_price: float | None = None
    pnl: float | None = None
    notes: str | None = None
    emotion: str | None = None


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
def get_journal(limit: int = Query(default=100, ge=1, le=10_000)) -> list[dict[str, Any]]:
    """Return journal entries newest first, each joined to its market regime.

    An empty journal (or a database that does not exist yet) returns ``[]`` —
    unlike the metrics endpoints, the journal is created by this layer, so
    "no entries yet" is a normal state rather than a 503.
    """
    return journal.list_enriched(_db_path(), limit)


@app.post("/journal/analyze")
def analyze_journal(
    client: Annotated[Any, Depends(get_anthropic_client)],
    limit: int = Query(default=100, ge=1, le=10_000),
) -> coach.BehavioralAnalysis:
    """Run the Claude behavioral-analysis agent over the journal."""
    entries = journal.list_enriched(_db_path(), limit)
    return coach.analyze(entries, client=client)
