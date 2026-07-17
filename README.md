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
- [x] Phase 2 — More metrics (realized volatility, volume, VWAP), tests against known data.
- [x] Phase 3 — Trade journal model + Claude API behavioral agent.
- [ ] Phase 4 — Next.js dashboard.
- [ ] Phase 5 — v0.1.0 release with sample-data demo.

## Running locally

Requires Rust (stable) and Python ≥ 3.11. All bundled data is synthetic — never real
trades or amounts.

```bash
# 1. (Optional) regenerate the sample tape — deterministic, seeded
python3 data/generate_ticks.py

# 2. Compute microstructure metrics per 1s window into metrics.db
cargo run --manifest-path engine/Cargo.toml --release -- \
  --input data/sample_mnq_ticks.csv --db metrics.db --window 1s

# 3. Serve the metrics
python3 -m venv .venv && .venv/bin/pip install -e "backtest[dev]"
METRICS_DB=metrics.db .venv/bin/uvicorn backtest.api:app

# 4. Query them — one table, three views
curl 'localhost:8000/metrics/ofi?limit=5'         # order-flow imbalance
curl 'localhost:8000/metrics/volatility?limit=5'  # realized volatility + trade count
curl 'localhost:8000/metrics/volume?limit=5'      # buy/sell/total volume + VWAP
```

Phase 3 adds a trade journal (stored alongside the metrics) and a Claude-powered
behavioral agent that reads it. The agent needs an Anthropic API key; it produces
behavioral observations correlated with the market regime — **not** trading advice
or price predictions.

```bash
# 5. Generate a synthetic trade journal (deterministic; all synthetic)
python3 data/generate_journal.py                  # writes data/sample_journal.csv

# 6. Analyze behavior with Claude (defaults to claude-opus-4-8;
#    override with ANTHROPIC_MODEL). --load seeds the journal into the DB first.
export ANTHROPIC_API_KEY=sk-ant-...
python3 -m backtest.coach --load data/sample_journal.csv --db metrics.db

# 7. Or drive the journal over the API (shares the same METRICS_DB)
curl -X POST localhost:8000/journal -H 'content-type: application/json' \
  -d '{"symbol":"MNQ","side":"long","entered_at_ns":1760000030000000000,
       "entry_price":21400,"size":1,"notes":"followed my plan","emotion":"calm"}'
curl 'localhost:8000/journal?limit=5'             # entries joined to the market regime
curl -X POST 'localhost:8000/journal/analyze'     # Claude behavioral analysis (503 without a key)
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
- **One unified `metrics` table instead of a table per metric** (Phase 2, Claude's
  proposal, accepted): every metric shares the same `(bucket_start_ns, window_ns)` key
  and is produced in a single windowing pass, so a wide row is the natural shape. The
  Python API projects the columns each endpoint needs (`/metrics/ofi`,
  `/metrics/volatility`, `/metrics/volume`) out of that one table; the Phase 1
  `/metrics/ofi` contract is unchanged.
- **Realized volatility is continuous across window boundaries** (Phase 2, mine): a
  window's realized variance includes the log return from the previous window's last
  trade, so summing per-window variances recovers the whole tape's realized variance and
  a window with a single tick still carries the volatility of its move. The alternative —
  resetting returns at each window edge — silently discards the boundary moves and
  understates volatility.
- **VWAP folded into the same pass** (Phase 2, Claude's proposal, accepted): it needs
  only the running `Σ price·size` the engine already touches per tick, so it comes almost
  for free and gives the dashboard a price anchor alongside the volume figures.
- **The trade journal is Python-owned and lives in the same database** (Phase 3, mine):
  unlike `metrics`, the journal is written and read by the Python + agent layer, not the
  Rust hot path, so Python owns the `journal_entries` schema — a deliberate inversion of
  the Phase 1 "the engine owns the schema" rule. Keeping it in the same SQLite file lets
  each entry join to the microstructure regime at its entry time (`GET /journal` and the
  agent both use that join), which is the whole point of the feature. SQLite only, no ORM,
  to stay consistent with the rest of the stack; Postgres in the diagram stays a future
  option, not a Phase 3 dependency.
- **Behavioral agent defaults to `claude-opus-4-8`** (Phase 3, mine): overridable via the
  `ANTHROPIC_MODEL` env var. It emits behavioral observations tied to the regime — by
  design **not** trading advice and **not** price predictions. The Anthropic client is
  dependency-injected, so the analysis is unit-tested against a mock and CI needs neither
  a key nor network access.
