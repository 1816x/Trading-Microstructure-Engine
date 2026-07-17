import sqlite3

import pytest
from fastapi.testclient import TestClient

from backtest import api, coach

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


# --- Journal (Phase 3) ---------------------------------------------------------


class _FakeResponse:
    def __init__(self, parsed_output):
        self.parsed_output = parsed_output


class _FakeMessages:
    def __init__(self, parsed_output):
        self._parsed_output = parsed_output

    def parse(self, **kwargs):
        return _FakeResponse(self._parsed_output)


class _FakeClient:
    def __init__(self, parsed_output):
        self.messages = _FakeMessages(parsed_output)


def _post_entry(client, entered_at_ns=1_500_000_000, **overrides):
    body = {
        "symbol": "MNQ",
        "side": "long",
        "entered_at_ns": entered_at_ns,
        "entry_price": 21_400.0,
        "size": 1,
    }
    body.update(overrides)
    return client.post("/journal", json=body)


def test_create_journal_entry(client):
    response = _post_entry(client, size=2, notes="plan", emotion="calm")
    assert response.status_code == 201
    stored = response.json()
    assert stored["id"] == 1
    assert stored["symbol"] == "MNQ"
    assert stored["size"] == 2
    assert stored["exit_price"] is None


def test_get_journal_joins_regime(client):
    # The metrics fixture has a bucket at 1e9 (window 1e9) covering 1.5e9.
    _post_entry(client, entered_at_ns=1_500_000_000)
    body = client.get("/journal").json()
    assert len(body) == 1
    assert body[0]["regime_bucket_start_ns"] == 1_000_000_000
    assert body[0]["regime_ofi"] == 0.5


def test_get_journal_empty_returns_200(client):
    assert client.get("/journal").json() == []


def test_journal_limit_is_validated(client):
    assert client.get("/journal", params={"limit": 0}).status_code == 422


def test_analyze_journal_returns_structured(client):
    _post_entry(client)
    canned = coach.BehavioralAnalysis(summary="s", observations=[], disclaimer=coach.DISCLAIMER)
    api.app.dependency_overrides[api.get_anthropic_client] = lambda: _FakeClient(canned)
    try:
        response = client.post("/journal/analyze")
    finally:
        api.app.dependency_overrides.clear()
    assert response.status_code == 200
    body = response.json()
    assert body["summary"] == "s"
    assert body["disclaimer"] == coach.DISCLAIMER


def test_analyze_without_api_key_returns_503(client, monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    api.app.dependency_overrides.clear()
    assert client.post("/journal/analyze").status_code == 503
