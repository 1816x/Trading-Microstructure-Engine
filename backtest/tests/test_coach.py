from backtest import coach
from backtest.coach import BehavioralAnalysis, BehavioralObservation


class _FakeMessages:
    def __init__(self, parsed_output):
        self._parsed_output = parsed_output
        self.calls = []

    def parse(self, **kwargs):
        self.calls.append(kwargs)
        return _FakeResponse(self._parsed_output)


class _FakeResponse:
    def __init__(self, parsed_output):
        self.parsed_output = parsed_output


class FakeClient:
    def __init__(self, parsed_output):
        self.messages = _FakeMessages(parsed_output)


def _canned() -> BehavioralAnalysis:
    return BehavioralAnalysis(
        summary="Revenge trading after losses.",
        observations=[
            BehavioralObservation(
                pattern="Revenge sizing",
                bias="loss aversion",
                evidence="#4, #5",
                severity="high",
            )
        ],
        disclaimer=coach.DISCLAIMER,
    )


def _enriched(**overrides):
    entry = {
        "id": 1,
        "symbol": "MNQ",
        "side": "long",
        "entered_at_ns": 1000,
        "entry_price": 21_400.0,
        "exit_price": 21_405.0,
        "size": 1,
        "pnl": 10.0,
        "notes": "followed my plan",
        "emotion": "calm",
        "regime_ofi": 0.5,
        "regime_realized_volatility": 0.001,
        "regime_vwap": 21_400.0,
    }
    entry.update(overrides)
    return entry


def test_analyze_returns_parsed_output():
    canned = _canned()
    client = FakeClient(canned)
    result = coach.analyze([_enriched()], client=client)
    assert result is canned
    (call,) = client.messages.calls
    assert call["output_format"] is BehavioralAnalysis
    assert call["model"] == "claude-opus-4-8"
    assert call["thinking"] == {"type": "adaptive"}


def test_analyze_uses_model_env(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_MODEL", "claude-haiku-4-5")
    client = FakeClient(_canned())
    coach.analyze([_enriched()], client=client)
    assert client.messages.calls[0]["model"] == "claude-haiku-4-5"


def test_analyze_empty_journal_short_circuits():
    client = FakeClient(_canned())
    result = coach.analyze([], client=client)
    assert result.observations == []
    assert result.disclaimer == coach.DISCLAIMER
    assert client.messages.calls == []  # no API call for an empty journal


def test_build_messages_includes_regime_and_notes():
    system, messages = coach.build_messages(
        [_enriched(notes="chased the move", emotion="fomo", regime_ofi=-0.5)]
    )
    assert "not financial advice" in system.lower()
    user = messages[0]["content"]
    assert "chased the move" in user
    assert "fomo" in user
    assert "ofi=-0.5" in user


def test_build_messages_marks_unknown_regime():
    _system, messages = coach.build_messages([_enriched(regime_ofi=None)])
    assert "unknown" in messages[0]["content"]
