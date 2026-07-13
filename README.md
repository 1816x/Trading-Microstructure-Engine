# Trading Microstructure Engine + AI Coach

A tick-by-tick futures data engine (MNQ and similar) that computes market microstructure
metrics — order-flow imbalance, realized volatility, volume imbalance — with its own
backtesting layer, plus a Claude-powered agent that reads your trade journal and surfaces
behavioral patterns and emotional biases correlated with the market regime at the time.

> **Disclaimer**: this is **not** financial advice and it does not predict prices.
> It is a tool for analyzing your *own* trading behavior against microstructure context.

## Architecture

```
data-feed → [Rust: microstructure engine] → metrics (order-flow imbalance, realized volatility)
                                                       ↓
                                          [Python: backtesting + aggregation]
                                                       ↓
                                            trade journal (SQLite/Postgres)
                                                       ↓
                              [Claude API: behavioral analysis agent]
                                                       ↓
                                       [Next.js: dashboard + reports]
```

| Layer        | Language            | Why                                                                 |
| ------------ | ------------------- | ------------------------------------------------------------------- |
| `engine/`    | Rust                | Low-latency processing of high-frequency tick streams is exactly what Rust is for. |
| `backtest/`  | Python              | Statistical metrics, aggregation and the API that feeds the agent.  |
| `dashboard/` | TypeScript (Next.js)| Metric charts and the trade journal view.                            |
| Agent        | Claude API          | Behavioral observations from the journal — not price predictions.   |

## Status

Early scaffolding. Roadmap:

- [x] Phase 0 — Scaffolding: monorepo layout, linters, CI.
- [x] Phase 1 — Vertical slice: sample tick CSV → order-flow imbalance → SQLite → API endpoint.
- [ ] Phase 2 — More metrics (realized volatility, volume), tests against known data.
- [ ] Phase 3 — Trade journal model + Claude API behavioral agent.
- [ ] Phase 4 — Next.js dashboard.
- [ ] Phase 5 — v0.1.0 release with sample-data demo.

## Running locally

Requires Rust (stable) and Python ≥ 3.11. All bundled data is synthetic — never real
trades or amounts.

```bash
# 1. (Optional) regenerate the sample tape — deterministic, seeded
python3 data/generate_ticks.py

# 2. Compute order-flow imbalance per 1s window into metrics.db
cargo run --manifest-path engine/Cargo.toml --release -- \
  --input data/sample_mnq_ticks.csv --db metrics.db --window 1s

# 3. Serve the metrics
python3 -m venv .venv && .venv/bin/pip install -e "backtest[dev]"
METRICS_DB=metrics.db .venv/bin/uvicorn backtest.api:app

# 4. Query them
curl 'localhost:8000/metrics/ofi?limit=5'
```

Run the checks the same way CI does:

```bash
cd engine && cargo fmt --check && cargo clippy --all-targets -- -D warnings && cargo test
cd backtest && ruff check . && ruff format --check . && pytest
```

## Design decisions

This project is built in deliberate collaboration with Claude. This section documents
who decided what — what the AI proposed, what got corrected or rejected, and which
calls were made by me — as the project progresses.

- **Rust over Go for the engine** (mine): the reference ecosystem for high-performance
  trading in this space is Rust (e.g. `barter-rs`), and the tick-processing hot path is
  where the language choice actually matters.
- **Dashboard scaffold deferred to Phase 4** (Claude's proposal, accepted): running
  `create-next-app` during scaffolding would bury the early history under thousands of
  generated lines; a placeholder folder keeps Phase 0 reviewable.
- **Order-flow imbalance first** (mine): of the planned metrics it is the one that most
  depends on true tick data (aggressor side per trade) instead of OHLC candles, so it
  proves the pipeline earns its keep before anything else gets built.
- **OFI defined as `(buy − sell) / (buy + sell)` per epoch-aligned window** (Claude's
  proposal, accepted): the normalized form is bounded in `[-1, 1]`, which makes windows
  comparable across volume regimes. Buckets accumulate in an ordered map so an
  out-of-order tape still produces sorted output.
- **FastAPI serves the metric in Phase 1** (Claude's proposal, accepted): the endpoint
  belongs to the Python layer that will own backtesting and aggregation anyway; giving
  the Rust engine an HTTP server would couple the hot path to serving concerns.
- **Synthetic tape with a drifting buy-pressure regime** (Claude's proposal, corrected
  by me): a naive uniform-random tape makes OFI hover near zero everywhere, which hides
  bugs — sign errors produce equally plausible noise. The generator drifts its
  buy-pressure between 0.35 and 0.65 so imbalance windows show persistent, verifiable
  signal.
