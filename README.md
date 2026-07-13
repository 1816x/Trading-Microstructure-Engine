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
- [ ] Phase 1 — Vertical slice: sample tick CSV → order-flow imbalance → SQLite → API endpoint.
- [ ] Phase 2 — More metrics (realized volatility, volume), tests against known data.
- [ ] Phase 3 — Trade journal model + Claude API behavioral agent.
- [ ] Phase 4 — Next.js dashboard.
- [ ] Phase 5 — v0.1.0 release with sample-data demo.

## Running locally

Coming with Phase 1 — the vertical slice will be runnable end-to-end with the bundled
sample data (synthetic, never real trades or amounts).

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
