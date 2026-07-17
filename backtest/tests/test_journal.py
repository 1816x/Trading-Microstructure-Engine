import sqlite3

import pytest

from backtest import journal

# Same columns the Rust engine writes; used to seed a metrics table for the join.
METRICS_COLUMNS = (
    "bucket_start_ns, window_ns, buy_volume, sell_volume, total_volume,"
    " trade_count, ofi, vwap, realized_volatility"
)


def _entry(entered_at_ns: int, side: str = "long", **overrides):
    entry = {
        "symbol": "MNQ",
        "side": side,
        "entered_at_ns": entered_at_ns,
        "entry_price": 21_400.0,
        "size": 1,
        "exited_at_ns": entered_at_ns + 1_000,
        "exit_price": 21_405.0,
        "pnl": 10.0,
        "notes": "note",
        "emotion": "calm",
    }
    entry.update(overrides)
    return entry


def _seed_metrics(db, rows):
    with sqlite3.connect(db) as conn:
        conn.execute(f"CREATE TABLE metrics ({METRICS_COLUMNS})")
        conn.executemany(f"INSERT INTO metrics VALUES ({', '.join(['?'] * 9)})", rows)


@pytest.fixture
def db(tmp_path):
    return tmp_path / "metrics.db"


def test_insert_returns_stored_row(db):
    stored = journal.insert_entry(db, _entry(1000))
    assert stored["id"] == 1
    assert stored["symbol"] == "MNQ"
    assert stored["entered_at_ns"] == 1000
    assert isinstance(stored["created_at_ns"], int)


def test_list_entries_newest_first(db):
    for entered_at_ns in (1000, 3000, 2000):
        journal.insert_entry(db, _entry(entered_at_ns))
    entries = journal.list_entries(db, limit=10)
    assert [e["entered_at_ns"] for e in entries] == [3000, 2000, 1000]


def test_list_entries_respects_limit(db):
    for entered_at_ns in (1000, 2000, 3000):
        journal.insert_entry(db, _entry(entered_at_ns))
    assert len(journal.list_entries(db, limit=2)) == 2


def test_list_entries_missing_db_returns_empty(tmp_path):
    assert journal.list_entries(tmp_path / "nope.db", limit=10) == []


def test_list_enriched_without_metrics_has_null_regime(db):
    journal.insert_entry(db, _entry(1000))
    (row,) = journal.list_enriched(db, limit=10)
    assert row["regime_ofi"] is None
    assert row["regime_vwap"] is None
    assert row["regime_bucket_start_ns"] is None


def test_list_enriched_joins_regime(db):
    journal.insert_entry(db, _entry(1_500))
    _seed_metrics(
        db,
        [
            (1000, 1000, 30, 10, 40, 5, 0.5, 21_400.0, 0.001),
            (2000, 1000, 5, 15, 20, 4, -0.5, 21_401.0, 0.002),
        ],
    )
    (row,) = journal.list_enriched(db, limit=10)
    assert row["regime_bucket_start_ns"] == 1000
    assert row["regime_window_ns"] == 1000
    assert row["regime_ofi"] == 0.5
    assert row["regime_vwap"] == 21_400.0


def test_list_enriched_prefers_finest_window(db):
    journal.insert_entry(db, _entry(1_500))
    _seed_metrics(
        db,
        [
            (0, 5000, 1, 1, 2, 2, 0.0, 1.0, 0.0),  # coarse window also contains 1500
            (1000, 1000, 1, 1, 2, 2, 0.9, 2.0, 0.0),  # finer window contains 1500
        ],
    )
    (row,) = journal.list_enriched(db, limit=10)
    assert row["regime_window_ns"] == 1000
    assert row["regime_ofi"] == 0.9


def test_list_enriched_no_bucket_covers_entry(db):
    journal.insert_entry(db, _entry(9_999))
    _seed_metrics(db, [(1000, 1000, 1, 1, 2, 2, 0.5, 1.0, 0.0)])  # covers [1000, 2000)
    (row,) = journal.list_enriched(db, limit=10)
    assert row["regime_ofi"] is None


def test_import_csv(tmp_path):
    csv_path = tmp_path / "j.csv"
    csv_path.write_text(
        "symbol,side,entered_at_ns,exited_at_ns,entry_price,exit_price,size,pnl,notes,emotion\n"
        "MNQ,long,1000,2000,21400.00,21405.00,1,10.00,ok,calm\n"
        "MNQ,short,3000,,21410.00,,2,,,\n"
    )
    db = tmp_path / "metrics.db"
    assert journal.import_csv(csv_path, db) == 2

    newest, oldest = journal.list_entries(db, limit=10)
    assert newest["side"] == "short"
    assert newest["size"] == 2
    assert newest["exited_at_ns"] is None
    assert newest["exit_price"] is None
    assert newest["pnl"] is None
    assert newest["notes"] is None
    assert oldest["entry_price"] == 21_400.0
    assert oldest["pnl"] == 10.0
