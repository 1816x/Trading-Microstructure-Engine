/**
 * BigInt-safe JSON for the backend's `*_ns` nanosecond timestamps.
 *
 * The API serializes every `*_ns` field as a JSON integer, and those epochs
 * (~1.76e18) exceed Number.MAX_SAFE_INTEGER (2^53 − 1 ≈ 9e15), so a plain
 * `JSON.parse` silently rounds them (documented in `backtest.api` as a
 * Phase 4 concern). `parseNs` instead reads the digits from the raw source
 * text via the ES2025 reviver `context.source`, and `stringifyNs` emits
 * BigInts back as unquoted integers via `JSON.rawJSON` — the pydantic models
 * expect JSON integers, not strings. Both require Node ≥ 22 or an evergreen
 * browser; `ensureSupported` fails loudly rather than corrupt a timestamp.
 */

type ReviverContext = { source?: string };
type SourceReviver = (this: unknown, key: string, value: unknown, context?: ReviverContext) => unknown;
type PlainReviver = Parameters<typeof JSON.parse>[1];

const rawJSON: ((text: string) => unknown) | undefined = (
  JSON as { rawJSON?: (text: string) => unknown }
).rawJSON;

const INTEGER_SOURCE = /^-?\d+$/;

let supportChecked = false;

function ensureSupported(): void {
  if (supportChecked) return;
  const probe: unknown = JSON.parse("9007199254740993", ((
    _key: string,
    value: unknown,
    context?: ReviverContext,
  ) => context?.source ?? value) as PlainReviver);
  if (probe !== "9007199254740993" || typeof rawJSON !== "function") {
    throw new Error(
      "this runtime lacks JSON.parse source access / JSON.rawJSON — " +
        "*_ns timestamps cannot round-trip without precision loss",
    );
  }
  supportChecked = true;
}

/** Parse `text`, materializing every integer-valued `*_ns` field as a BigInt. */
export function parseNs(text: string): unknown {
  ensureSupported();
  const reviver: SourceReviver = (key, value, context) => {
    if (
      key.endsWith("_ns") &&
      typeof value === "number" &&
      context?.source !== undefined &&
      INTEGER_SOURCE.test(context.source)
    ) {
      return BigInt(context.source);
    }
    return value;
  };
  return JSON.parse(text, reviver as PlainReviver);
}

/** Stringify `value`, serializing BigInts as unquoted JSON integers. */
export function stringifyNs(value: unknown): string {
  ensureSupported();
  return JSON.stringify(value, (_key, v: unknown) =>
    typeof v === "bigint" ? rawJSON!(v.toString()) : v,
  );
}

/** Truncate a nanosecond epoch to milliseconds — safe as a Number (~1.76e12). */
export function nsToMs(ns: bigint): number {
  return Number(ns / 1_000_000n);
}

/** Lift a millisecond epoch (e.g. from a date input) to nanoseconds. */
export function msToNs(ms: number): bigint {
  return BigInt(Math.round(ms)) * 1_000_000n;
}

/** "YYYY-MM-DD HH:MM:SS UTC" — full timestamp for tables. */
export function formatNs(ns: bigint): string {
  return `${new Date(nsToMs(ns)).toISOString().slice(0, 19).replace("T", " ")} UTC`;
}

/** "HH:MM:SS" (UTC) — compact time-of-day for chart axes. */
export function formatNsTime(ns: bigint): string {
  return new Date(nsToMs(ns)).toISOString().slice(11, 19);
}
