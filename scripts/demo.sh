#!/usr/bin/env bash
# One-command demo of the full stack on the synthetic sample data:
#
#   tape -> Rust engine -> metrics.db -> journal seed -> FastAPI -> Next.js dashboard
#
# Regenerates the deterministic sample data, computes the microstructure metrics,
# seeds the trade journal, then serves the API and the dashboard until Ctrl-C.
# The first run installs .venv and dashboard/node_modules; later runs reuse them.
# The behavioral agent (POST /journal/analyze) needs ANTHROPIC_API_KEY — see
# .env.example; everything else in the demo works without it.
#
# Usage: bash scripts/demo.sh   (or: make demo)
#   PYTHON=...      interpreter for the venv + generators (default python3)
#   METRICS_DB=...  SQLite path (default metrics.db; recreated on every run)
#   API_PORT=...    FastAPI port (default 8000)
#   DASH_PORT=...   dashboard port (default 3000)
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

# Optional; carries ANTHROPIC_API_KEY (and friends) for the behavioral agent.
if [[ -f .env ]]; then
  set -a
  # shellcheck disable=SC1091
  . ./.env
  set +a
fi

PY="${PYTHON:-python3}"
DB="${METRICS_DB:-metrics.db}"
API_PORT="${API_PORT:-8000}"
DASH_PORT="${DASH_PORT:-3000}"

for tool in "$PY" cargo npm curl; do
  command -v "$tool" >/dev/null 2>&1 || {
    echo "demo: '$tool' is required but not on PATH" >&2
    exit 1
  }
done

for port in "$API_PORT" "$DASH_PORT"; do
  if curl -s -o /dev/null --max-time 2 "http://localhost:$port"; then
    echo "demo: port $port is already in use — is another demo still running?" >&2
    exit 1
  fi
done

LOG_DIR="$(mktemp -d -t tme_demo.XXXXXX)"
API_PID=""
DASH_PID=""

cleanup() {
  trap - INT TERM EXIT
  echo
  echo "stopping the demo (server logs kept in $LOG_DIR)"
  [[ -z "$DASH_PID" ]] || kill "$DASH_PID" 2>/dev/null || true
  [[ -z "$API_PID" ]] || kill "$API_PID" 2>/dev/null || true
  wait 2>/dev/null || true
  # A kill landing while `next dev` writes its generated route types leaves
  # them half-written, and dashboard/tsconfig.json includes them — drop the
  # scratch (regenerated on every dev boot) so an interrupted demo can never
  # break `npm run typecheck`.
  rm -rf "$ROOT/dashboard/.next/dev/types"
  exit 0
}
trap cleanup INT TERM EXIT

echo "1/6 generating the synthetic tape and journal (deterministic, all synthetic)"
"$PY" data/generate_ticks.py >/dev/null
"$PY" data/generate_journal.py >/dev/null

echo "2/6 computing microstructure metrics into $DB (fresh on every run)"
rm -f "$DB"
cargo run --quiet --manifest-path engine/Cargo.toml --release -- \
  --input data/sample_mnq_ticks.csv --db "$DB" --window 1s

echo "3/6 seeding the trade journal"
PYTHONPATH="$ROOT/backtest/src${PYTHONPATH:+:$PYTHONPATH}" "$PY" - "$DB" <<'PYCODE'
import sys

from backtest import journal

seeded = journal.import_csv("data/sample_journal.csv", sys.argv[1])
print(f"    seeded {seeded} journal entries")
PYCODE

echo "4/6 preparing the Python env (.venv)"
if [[ ! -x .venv/bin/uvicorn ]]; then
  "$PY" -m venv .venv
  .venv/bin/pip install --quiet -e backtest
fi

echo "5/6 starting the API on http://localhost:$API_PORT"
METRICS_DB="$DB" .venv/bin/uvicorn backtest.api:app --port "$API_PORT" \
  >"$LOG_DIR/api.log" 2>&1 &
API_PID=$!
for _ in $(seq 1 60); do
  curl -sf "http://localhost:$API_PORT/metrics/ofi?limit=1" >/dev/null 2>&1 && break
  if ! kill -0 "$API_PID" 2>/dev/null; then
    echo "demo: the API exited during startup; last log lines:" >&2
    tail -n 20 "$LOG_DIR/api.log" >&2
    exit 1
  fi
  sleep 0.5
done
curl -sf "http://localhost:$API_PORT/metrics/ofi?limit=1" >/dev/null 2>&1 || {
  echo "demo: the API did not answer within 30s; last log lines:" >&2
  tail -n 20 "$LOG_DIR/api.log" >&2
  exit 1
}

echo "6/6 starting the dashboard on http://localhost:$DASH_PORT"
if [[ ! -d dashboard/node_modules ]]; then
  echo "    installing dashboard dependencies (first run only)"
  npm ci --prefix dashboard --no-audit --no-fund >"$LOG_DIR/npm.log" 2>&1
fi
(
  cd dashboard
  BACKEND_URL="http://localhost:$API_PORT" \
    exec node_modules/.bin/next dev --port "$DASH_PORT"
) >"$LOG_DIR/dashboard.log" 2>&1 &
DASH_PID=$!
for _ in $(seq 1 120); do
  curl -sf "http://localhost:$DASH_PORT" >/dev/null 2>&1 && break
  if ! kill -0 "$DASH_PID" 2>/dev/null; then
    echo "demo: the dashboard exited during startup; last log lines:" >&2
    tail -n 20 "$LOG_DIR/dashboard.log" >&2
    exit 1
  fi
  sleep 0.5
done
curl -sf "http://localhost:$DASH_PORT" >/dev/null 2>&1 || {
  echo "demo: the dashboard did not answer within 60s; last log lines:" >&2
  tail -n 20 "$LOG_DIR/dashboard.log" >&2
  exit 1
}

echo
echo "demo up — open http://localhost:$DASH_PORT  (API: http://localhost:$API_PORT)"
if [[ -z "${ANTHROPIC_API_KEY:-}" ]]; then
  echo "note: ANTHROPIC_API_KEY is not set — everything works except behavioral analysis"
fi
echo "Ctrl-C stops both servers."
wait
