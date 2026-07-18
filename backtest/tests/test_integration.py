"""Hermetic end-to-end test of the journal HTTP flow over a seeded metrics table.

Runs in CI without cargo or an API key: it stands in a `metrics` table for the
Rust engine's output, drives the real FastAPI app, and mocks the Anthropic
client. The Rust-in-the-loop smoke test lives in scripts/verify_pipeline.sh.
"""

import sqlite3

import pytest
from fastapi.testclient import TestClient

from backtest import api, coach

METRICS_COLUMNS = (
    "bucket_start_ns, window_ns, buy_volume, sell_volume, total_volume,"
    " trade_count, ofi, vwap, realized_volatility"
)
# Two 1s buckets: [1e9, 2e9) with ofi 0.5, [2e9, 3e9) with ofi -0.5.
METRIC_ROWS = [
    (1_000_000_000, 1_000_000_000, 30, 10, 40, 5, 0.5, 21_400.0, 0.001),
    (2_000_000_000, 1_000_000_000, 5, 15, 20, 4, -0.5, 21_401.0, 0.002),
]


class _FakeResponse:
    def __init__(self, parsed_output):
        self.parsed_output = parsed_output
        self.stop_reason = "end_turn"


class _FakeMessages:
    def __init__(self, parsed_output):
        self._parsed_output = parsed_output

    def parse(self, **kwargs):
        return _FakeResponse(self._parsed_output)


class _FakeClient:
    def __init__(self, parsed_output):
        self.messages = _FakeMessages(parsed_output)


@pytest.fixture
def client(tmp_path, monkeypatch):
    db = tmp_path / "metrics.db"
    with sqlite3.connect(db) as conn:
        conn.execute(f"CREATE TABLE metrics ({METRICS_COLUMNS})")
        conn.executemany(f"INSERT INTO metrics VALUES ({', '.join(['?'] * 9)})", METRIC_ROWS)
    monkeypatch.setenv(api.DB_PATH_ENV, str(db))
    return TestClient(app=api.app)


def _entry(entered_at_ns, side="long"):
    return {
        "symbol": "MNQ",
        "side": side,
        "entered_at_ns": entered_at_ns,
        "entry_price": 21_400.0,
        "size": 1,
    }


def test_full_journal_flow_through_http(client):
    # Two trades entered in different regime windows.
    first = client.post("/journal", json=_entry(1_500_000_000, "long")).json()
    second = client.post("/journal", json=_entry(2_500_000_000, "short")).json()

    listed = client.get("/journal").json()
    by_id = {row["id"]: row for row in listed}
    assert by_id[first["id"]]["regime_ofi"] == 0.5
    assert by_id[second["id"]]["regime_ofi"] == -0.5
    assert [row["id"] for row in listed] == [second["id"], first["id"]]  # newest first

    # Analyze the whole journal via HTTP with a mocked model.
    analysis = coach.BehavioralAnalysis(
        summary="two trades across opposite regimes",
        observations=[],
        disclaimer=coach.DISCLAIMER,
    )
    api.app.dependency_overrides[api.get_anthropic_client] = lambda: _FakeClient(analysis)
    try:
        response = client.post("/journal/analyze")
    finally:
        api.app.dependency_overrides.clear()
    assert response.status_code == 200
    assert response.json()["summary"] == "two trades across opposite regimes"


def test_time_range_filter_through_http(client):
    client.post("/journal", json=_entry(1_500_000_000))
    client.post("/journal", json=_entry(2_500_000_000))

    only_first = client.get("/journal", params={"until_ns": 2_000_000_000}).json()
    assert [row["entered_at_ns"] for row in only_first] == [1_500_000_000]

    only_second = client.get("/journal", params={"since_ns": 2_000_000_000}).json()
    assert [row["entered_at_ns"] for row in only_second] == [2_500_000_000]
