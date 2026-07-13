import sqlite3

import pytest
from fastapi.testclient import TestClient

from backtest import api

ROWS = [
    # (bucket_start_ns, window_ns, buy_volume, sell_volume, ofi)
    (1_000_000_000, 1_000_000_000, 30, 10, 0.5),
    (2_000_000_000, 1_000_000_000, 5, 15, -0.5),
    (3_000_000_000, 1_000_000_000, 7, 7, 0.0),
]


@pytest.fixture
def client(tmp_path, monkeypatch):
    db = tmp_path / "metrics.db"
    with sqlite3.connect(db) as conn:
        conn.execute(
            "CREATE TABLE ofi (bucket_start_ns INTEGER, window_ns INTEGER,"
            " buy_volume INTEGER, sell_volume INTEGER, ofi REAL)"
        )
        conn.executemany("INSERT INTO ofi VALUES (?, ?, ?, ?, ?)", ROWS)
    monkeypatch.setenv(api.DB_PATH_ENV, str(db))
    return TestClient(app=api.app)


def test_returns_buckets_newest_first(client):
    body = client.get("/metrics/ofi").json()
    assert [row["bucket_start_ns"] for row in body] == [3_000_000_000, 2_000_000_000, 1_000_000_000]
    assert body[1] == {
        "bucket_start_ns": 2_000_000_000,
        "window_ns": 1_000_000_000,
        "buy_volume": 5,
        "sell_volume": 15,
        "ofi": -0.5,
    }


def test_limit_caps_rows(client):
    assert len(client.get("/metrics/ofi", params={"limit": 2}).json()) == 2


def test_limit_is_validated(client):
    assert client.get("/metrics/ofi", params={"limit": 0}).status_code == 422


def test_missing_database_returns_503(monkeypatch, tmp_path):
    monkeypatch.setenv(api.DB_PATH_ENV, str(tmp_path / "nope.db"))
    response = TestClient(app=api.app).get("/metrics/ofi")
    assert response.status_code == 503
    assert "run the engine first" in response.json()["detail"]


def test_empty_database_returns_503(monkeypatch, tmp_path):
    db = tmp_path / "empty.db"
    sqlite3.connect(db).close()
    monkeypatch.setenv(api.DB_PATH_ENV, str(db))
    assert TestClient(app=api.app).get("/metrics/ofi").status_code == 503
