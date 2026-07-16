"""Read-only API over the metrics database produced by the Rust engine.

The engine owns the schema; this layer only exposes it. Point it at a
database with the METRICS_DB environment variable (default: metrics.db
in the working directory).
"""

import os
import sqlite3
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, Query

DB_PATH_ENV = "METRICS_DB"

app = FastAPI(title="Trading Microstructure Engine API")


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
