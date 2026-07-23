# dashboard/

Next.js (App Router, TypeScript, Tailwind) visualization layer over the
`backtest/` API — Phase 4 of the project plan.

- **Metrics** (`/`): stat tiles for the latest window plus charts for order-flow
  imbalance (diverging bars), realized volatility, buy/sell volume and VWAP.
- **Journal** (`/journal`): trades joined to the market regime at entry, a
  log-a-trade form, and the Claude behavioral-analysis panel.

## Running it

Requires Node ≥ 22. The dashboard talks to the FastAPI backend, so start that
first (see the repo root README: engine → `metrics.db` → `uvicorn
backtest.api:app`).

```bash
npm install
npm run dev        # http://localhost:3000
```

Requests to `/api/backend/*` are rewritten server-side to the backend —
`BACKEND_URL` overrides the default `http://localhost:8000`. The backend needs
no CORS configuration because the browser only ever sees this app's origin.
`ANTHROPIC_API_KEY` is only needed by the *backend*, and only for the
journal's Analyze button; everything else works without it.

## Nanosecond timestamps

The API serializes every `*_ns` field as a JSON integer, and those epochs
(~1.76e18) exceed `Number.MAX_SAFE_INTEGER`. `src/lib/nsjson.ts` therefore
parses response bodies with the ES2025 reviver source access (`context.source`)
and materializes `*_ns` fields as `BigInt`, and serializes them back as
unquoted integers via `JSON.rawJSON`. Timestamps are truncated to milliseconds
(`nsToMs`) only for chart axes, where float precision is enough.

## Checks

Same gate CI runs:

```bash
npm run lint
npm run typecheck
npm test           # Vitest + Testing Library
npm run build
```
