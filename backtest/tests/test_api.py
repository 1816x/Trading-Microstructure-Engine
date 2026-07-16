import sqlite3

import pytest
from fastapi.testclient import TestClient

from backtest import api

COLUMNS = (
    "bucket_start_ns, window_ns, buy_volume, sell_volume, total_volume,"
    " trade_count, ofi, vwap, realized_volatility"
)
ROWS = [
    # bucket_start_ns, window_ns, buy, sell, total, count, ofi, vwap, rvol
    (1_000_000_000, 1_000_000_000, 30, 10, 40, 5, 0.5, 21_400.0, 0.001),
    (2_000_000_000, 1_000_000_000, 5, 15, 20, 4, -0.5, 21_401.0, 0.002),
    (3_000_000_000, 1_000_000_000, 7, 7, 14, 3, 0.0, 21_402.0, 0.0),
]


@pytest.fixture
def client(tmp_path, monkeypatch):
    db = tmp_path / "metrics.db"
    with sqlite3.connect(db) as conn:
        conn.execute(f"CREATE TABLE metrics ({COLUMNS})")
        conn.executemany(f"INSERT INTO metrics VALUES ({', '.join(['?'] * len(ROWS[0]))})", ROWS)
    monkeypatch.setenv(api.DB_PATH_ENV, str(db))
    return TestClient(app=api.app)


def test_ofi_returns_buckets_newest_first(client):
    body = client.get("/metrics/ofi").json()
    assert [row["bucket_start_ns"] for row in body] == [
        3_000_000_000,
        2_000_000_000,
        1_000_000_000,
    ]
    assert body[1] == {
        "bucket_start_ns": 2_000_000_000,
        "window_ns": 1_000_000_000,
        "buy_volume": 5,
        "sell_volume": 15,
        "ofi": -0.5,
    }


def test_volatility_endpoint_projects_expected_columns(client):
    body = client.get("/metrics/volatility").json()
    assert body[0] == {
        "bucket_start_ns": 3_000_000_000,
        "window_ns": 1_000_000_000,
        "realized_volatility": 0.0,
        "trade_count": 3,
    }


def test_volume_endpoint_projects_expected_columns(client):
    body = client.get("/metrics/volume").json()
    assert body[2] == {
        "bucket_start_ns": 1_000_000_000,
        "window_ns": 1_000_000_000,
        "buy_volume": 30,
        "sell_volume": 10,
        "total_volume": 40,
        "vwap": 21_400.0,
        "trade_count": 5,
    }


@pytest.mark.parametrize("endpoint", ["ofi", "volatility", "volume"])
def test_limit_caps_rows(client, endpoint):
    assert len(client.get(f"/metrics/{endpoint}", params={"limit": 2}).json()) == 2


@pytest.mark.parametrize("endpoint", ["ofi", "volatility", "volume"])
def test_limit_is_validated(client, endpoint):
    assert client.get(f"/metrics/{endpoint}", params={"limit": 0}).status_code == 422


@pytest.mark.parametrize("endpoint", ["ofi", "volatility", "volume"])
def test_missing_database_returns_503(monkeypatch, tmp_path, endpoint):
    monkeypatch.setenv(api.DB_PATH_ENV, str(tmp_path / "nope.db"))
    response = TestClient(app=api.app).get(f"/metrics/{endpoint}")
    assert response.status_code == 503
    assert "run the engine first" in response.json()["detail"]


@pytest.mark.parametrize("endpoint", ["ofi", "volatility", "volume"])
def test_empty_database_returns_503(monkeypatch, tmp_path, endpoint):
    db = tmp_path / "empty.db"
    sqlite3.connect(db).close()
    monkeypatch.setenv(api.DB_PATH_ENV, str(db))
    assert TestClient(app=api.app).get(f"/metrics/{endpoint}").status_code == 503
