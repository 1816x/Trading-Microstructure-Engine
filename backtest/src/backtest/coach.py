"""Claude-powered behavioral-analysis agent (the "coach").

Reads the trade journal joined to the market microstructure regime at each entry
(see :mod:`backtest.journal`) and asks Claude to surface recurring behavioral
patterns and emotional biases. It produces *behavioral observations about the
trader's own decisions* — never trading advice and never price predictions.

The Anthropic client is injected into :func:`analyze` so the analysis logic is
unit-testable with a fake client and no network access. The SDK is imported
lazily in :func:`main` (the CLI) so importing this module does not require the
``anthropic`` package.

CLI:
    python -m backtest.coach [--db PATH] [--limit N] [--load CSV]
"""

import argparse
import os
from typing import Any, Literal

from pydantic import BaseModel, Field

from backtest import journal

MODEL_ENV = "ANTHROPIC_MODEL"
DEFAULT_MODEL = "claude-opus-4-8"
# Same env var the read API uses (backtest.api.DB_PATH_ENV); duplicated here to
# avoid a circular import, since api imports coach.
DB_PATH_ENV = "METRICS_DB"

DISCLAIMER = (
    "This is a behavioral analysis of your own trading. It is not financial "
    "advice and does not predict prices or market direction."
)

SYSTEM_PROMPT = f"""\
You are a trading-behavior analyst. You read a trader's own journal — the trades
they chose to take, their written notes and stated emotions — alongside the
market microstructure regime (order-flow imbalance, realized volatility, VWAP)
that was in force at the moment of entry.

Your job is to surface recurring behavioral patterns and emotional or cognitive
biases, and to relate them to the regime the trader was acting in — for example
entering into strongly one-sided order flow, sizing up right after a loss, or
hesitating during high-volatility windows. Ground every observation in specific
journal entries.

You do NOT give trading advice, you do NOT tell the trader what to do next, and
you do NOT predict prices or market direction. You describe behavior, not
markets.

Populate the 'disclaimer' field with exactly this text: "{DISCLAIMER}"
"""


class AnalysisUnavailable(Exception):
    """Raised when Claude returns no usable structured analysis.

    Happens on a safety ``refusal`` or when structured parsing yields nothing.
    The API maps this to a 502 and the CLI reports it, rather than surfacing a
    bare ``None``.
    """


class BehavioralObservation(BaseModel):
    """One recurring behavioral pattern found in the journal."""

    pattern: str = Field(description="Short name for the behavioral pattern.")
    bias: str = Field(description="The emotional or cognitive bias involved.")
    evidence: str = Field(description="Specific journal entries that support it.")
    severity: Literal["low", "medium", "high"] = Field(
        description="How strongly the pattern shows up in the journal."
    )


class BehavioralAnalysis(BaseModel):
    """The agent's structured read of the whole journal."""

    summary: str = Field(description="One-paragraph overview of the trader's behavior.")
    observations: list[BehavioralObservation] = Field(
        description="Distinct behavioral patterns, most notable first."
    )
    disclaimer: str = Field(description="Verbatim behavioral-analysis disclaimer.")


def _model() -> str:
    return os.environ.get(MODEL_ENV, DEFAULT_MODEL)


def build_messages(entries: list[dict[str, Any]]) -> tuple[str, list[dict[str, Any]]]:
    """Build the (system, messages) pair sent to Claude for ``entries``."""
    lines = [
        "Here is the trader's own journal. Each entry pairs a trade they took "
        "with the market microstructure regime at the moment they entered it.",
        "",
    ]
    lines.extend(_format_entry(entry) for entry in entries)
    lines.extend(
        [
            "",
            "Analyze this journal for recurring behavioral patterns and "
            "emotional biases, and how they relate to the regime at entry. Cite "
            "specific entries as evidence. Do not give trading advice or predict "
            "prices.",
        ]
    )
    return SYSTEM_PROMPT, [{"role": "user", "content": "\n".join(lines)}]


def analyze(
    entries: list[dict[str, Any]],
    *,
    client: Any,
    model: str | None = None,
) -> BehavioralAnalysis:
    """Return Claude's structured behavioral analysis of ``entries``.

    ``client`` is an Anthropic client (or any object exposing the same
    ``messages.parse`` surface), injected so this is testable without network
    access. An empty journal short-circuits to an empty analysis rather than
    spending an API call.
    """
    if not entries:
        return BehavioralAnalysis(
            summary="No journal entries to analyze yet.",
            observations=[],
            disclaimer=DISCLAIMER,
        )
    system, messages = build_messages(entries)
    response = client.messages.parse(
        model=model or _model(),
        max_tokens=16000,
        thinking={"type": "adaptive"},
        system=system,
        messages=messages,
        output_format=BehavioralAnalysis,
    )
    analysis = response.parsed_output
    if analysis is None:
        stop_reason = getattr(response, "stop_reason", None)
        raise AnalysisUnavailable(
            f"the model returned no structured analysis (stop_reason={stop_reason!r})"
        )
    return analysis


def _format_entry(entry: dict[str, Any]) -> str:
    return (
        f"#{entry.get('id', '?')} {entry.get('symbol')} {entry.get('side')} "
        f"size={entry.get('size')} entry={entry.get('entry_price')} "
        f"exit={entry.get('exit_price')} pnl={entry.get('pnl')} "
        f"entered_at_ns={entry.get('entered_at_ns')} | "
        f"regime: {_format_regime(entry)} | "
        f"emotion={entry.get('emotion')!r} notes={entry.get('notes')!r}"
    )


def _format_regime(entry: dict[str, Any]) -> str:
    if entry.get("regime_ofi") is None:
        return "unknown (no metrics for this window)"
    return (
        f"ofi={entry.get('regime_ofi')} "
        f"realized_volatility={entry.get('regime_realized_volatility')} "
        f"vwap={entry.get('regime_vwap')}"
    )


def _render(analysis: BehavioralAnalysis) -> str:
    lines = [analysis.summary, ""]
    for obs in analysis.observations:
        lines.append(f"- [{obs.severity}] {obs.pattern} ({obs.bias})")
        lines.append(f"    {obs.evidence}")
    lines.extend(["", analysis.disclaimer])
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Analyze a trade journal with Claude.")
    parser.add_argument("--db", default=os.environ.get(DB_PATH_ENV, "metrics.db"))
    parser.add_argument("--limit", type=int, default=100)
    parser.add_argument(
        "--load",
        metavar="CSV",
        help="seed the journal from a CSV before analyzing",
    )
    args = parser.parse_args(argv)

    if args.load:
        count = journal.import_csv(args.load, args.db)
        print(f"loaded {count} journal entries from {args.load}")

    entries = journal.list_enriched(args.db, args.limit)
    if not entries:
        print("no journal entries found; add trades or pass --load <csv>")
        return

    import anthropic  # lazy: keeps the SDK out of the library import path

    try:
        analysis = analyze(entries, client=anthropic.Anthropic())
    except AnalysisUnavailable as exc:
        print(f"analysis unavailable: {exc}")
        return
    print(_render(analysis))


if __name__ == "__main__":
    main()
