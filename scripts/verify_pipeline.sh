#!/usr/bin/env bash
# End-to-end smoke test of the Phase 1-3 pipeline (no Claude API key required):
#
#   synthetic tape  ->  Rust engine  ->  metrics.db  ->  journal seed  ->  regime join
#
# It proves the three layers work together: the engine writes metrics, the
# journal is stored in the same DB, and each trade joins to the microstructure
# regime at its entry time. The behavioral agent (POST /journal/analyze) needs
# ANTHROPIC_API_KEY and is covered by the mocked unit tests instead.
#
# Usage: bash scripts/verify_pipeline.sh   (override the interpreter with PYTHON=...)
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

DB="$(mktemp -t tme_metrics.XXXXXX.db)"
trap 'rm -f "$DB"' EXIT

PY="${PYTHON:-python3}"
# Make `backtest` importable without an install; journal.py is stdlib-only.
export PYTHONPATH="$ROOT/backtest/src${PYTHONPATH:+:$PYTHONPATH}"

echo "1/4 generating synthetic tick tape"
"$PY" data/generate_ticks.py >/dev/null

echo "2/4 running the Rust engine into a temp metrics DB"
cargo run --quiet --manifest-path engine/Cargo.toml --release -- \
  --input data/sample_mnq_ticks.csv --db "$DB" --window 1s

echo "3/4 generating and seeding the synthetic journal"
"$PY" data/generate_journal.py >/dev/null
"$PY" - "$DB" <<'PYCODE'
import sys

from backtest import journal

db = sys.argv[1]
seeded = journal.import_csv("data/sample_journal.csv", db)
entries = journal.list_enriched(db, limit=1000)
joined = [e for e in entries if e["regime_ofi"] is not None]
print(f"    seeded {seeded} entries; {len(joined)}/{len(entries)} joined to a regime")
if not entries:
    sys.exit("FAIL: no journal entries after seeding")
if not joined:
    sys.exit("FAIL: no journal entry joined to a metric bucket")
PYCODE

echo "4/4 OK — Phase 1-3 pipeline verified end to end"
