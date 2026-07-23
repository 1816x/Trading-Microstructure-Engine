# Changelog

All notable changes to this project are documented in this file.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the
project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.1.0] — 2026-07-23

First tagged release: the complete vertical slice — synthetic tape → Rust engine →
SQLite metrics → FastAPI → trade journal + Claude behavioral agent → Next.js
dashboard — runnable end to end with one command (`make demo`). All bundled data is
synthetic; the agent produces behavioral observations, never trading advice or price
predictions.

### Added

- **Phase 0 — scaffolding**: monorepo layout (`engine/` Rust, `backtest/` Python,
  `dashboard/` placeholder), rustfmt/clippy/ruff configuration, CI pipeline.
- **Phase 1 — vertical slice**: deterministic synthetic MNQ tick generator
  (drifting buy-pressure regime); the engine parses the CSV tape and computes
  normalized order-flow imbalance per epoch-aligned 1s window into SQLite;
  FastAPI serves it at `GET /metrics/ofi`.
- **Phase 2 — more metrics**: realized volatility (continuous across window
  boundaries), buy/sell/total volume and VWAP computed in the same windowing pass
  into one unified `metrics` table; `GET /metrics/volatility` and
  `GET /metrics/volume`.
- **Phase 3 — trade journal + coach**: `journal_entries` lives in the same SQLite
  file so every entry joins to the microstructure regime at its entry time; full
  journal CRUD over the API (422-validated, `since_ns`/`until_ns` filters); Claude
  behavioral agent (`python -m backtest.coach`, `POST /journal/analyze`) with a
  dependency-injected client so tests and CI need no API key. Hardening review on
  top: engine rejects non-positive tick sizes at parse (a zero-size window made OFI
  and VWAP `NaN`), `PATCH /journal/{id}` re-validates exit-after-entry against the
  stored row, `anthropic` capped below the next major.
- **Phase 4 — dashboard**: Next.js 16 app with the four metric charts (OFI,
  realized volatility, volume, VWAP; Recharts, no dual axes) and the journal +
  behavioral-analysis views; `*_ns` nanosecond timestamps handled as exact `BigInt`
  end to end; same-origin proxy to the API instead of CORS.
- **Phase 5 — release**: `scripts/demo.sh` boots the whole stack (engine → metrics
  DB → journal seed → API → dashboard) on the sample data with one command; root
  `Makefile` (`setup`/`demo`/`verify`/`build`/`test`/`lint`/`clean`); README quick
  start with dashboard screenshots; this changelog; versions aligned at 0.1.0
  across engine, backtest and dashboard.

[Unreleased]: https://github.com/1816x/Trading-Microstructure-Engine/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/1816x/Trading-Microstructure-Engine/releases/tag/v0.1.0
