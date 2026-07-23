/**
 * Typed client for the backtest FastAPI backend.
 *
 * Every call goes through the same-origin `/api/backend` prefix, which
 * `next.config.ts` rewrites to the backend (`BACKEND_URL`, default
 * `http://localhost:8000`) — the backend serves no CORS headers, and the
 * rewrite proxy means it doesn't need any. Bodies are parsed with
 * `parseNs`/`stringifyNs` so `*_ns` timestamps round-trip as BigInt.
 */

import { parseNs, stringifyNs } from "@/lib/nsjson";

export const API_BASE = "/api/backend";

/** A non-2xx backend response, carrying FastAPI's `detail` message. */
export class ApiError extends Error {
  constructor(
    readonly status: number,
    readonly detail: string,
  ) {
    super(`${status}: ${detail}`);
    this.name = "ApiError";
  }
}

export interface OfiRow {
  bucket_start_ns: bigint;
  window_ns: bigint;
  buy_volume: number;
  sell_volume: number;
  ofi: number;
}

export interface VolatilityRow {
  bucket_start_ns: bigint;
  window_ns: bigint;
  realized_volatility: number;
  trade_count: number;
}

export interface VolumeRow {
  bucket_start_ns: bigint;
  window_ns: bigint;
  buy_volume: number;
  sell_volume: number;
  total_volume: number;
  vwap: number;
  trade_count: number;
}

export type Side = "long" | "short";

/** A journal row as returned by GET /journal — regime columns are null when
 * no metric bucket covers the entry time. */
export interface JournalEntry {
  id: number;
  symbol: string;
  side: Side;
  entered_at_ns: bigint;
  exited_at_ns: bigint | null;
  entry_price: number;
  exit_price: number | null;
  size: number;
  pnl: number | null;
  notes: string | null;
  emotion: string | null;
  created_at_ns: bigint;
  regime_bucket_start_ns: bigint | null;
  regime_window_ns: bigint | null;
  regime_ofi: number | null;
  regime_realized_volatility: number | null;
  regime_vwap: number | null;
}

/** POST /journal body. Matches the `JournalEntryIn` pydantic model. */
export interface NewJournalEntry {
  symbol: string;
  side: Side;
  entered_at_ns: bigint;
  entry_price: number;
  size: number;
  exited_at_ns?: bigint | null;
  exit_price?: number | null;
  pnl?: number | null;
  notes?: string | null;
  emotion?: string | null;
}

/** POST /journal response: the stored row, without the regime join. */
export type StoredJournalEntry = Omit<
  JournalEntry,
  | "regime_bucket_start_ns"
  | "regime_window_ns"
  | "regime_ofi"
  | "regime_realized_volatility"
  | "regime_vwap"
>;

export type Severity = "low" | "medium" | "high";

export interface BehavioralObservation {
  pattern: string;
  bias: string;
  evidence: string;
  severity: Severity;
}

export interface BehavioralAnalysis {
  summary: string;
  observations: BehavioralObservation[];
  disclaimer: string;
}

interface FastApiValidationItem {
  loc?: unknown;
  msg?: unknown;
}

/** FastAPI errors carry `{detail}` — a string, or a list of field errors on 422. */
function extractDetail(text: string): string {
  try {
    const detail: unknown = (JSON.parse(text) as { detail?: unknown }).detail;
    if (typeof detail === "string") return detail;
    if (Array.isArray(detail)) {
      return detail
        .map((item: FastApiValidationItem) => {
          const loc = Array.isArray(item?.loc) ? `${item.loc.join(".")}: ` : "";
          return item?.msg !== undefined ? `${loc}${String(item.msg)}` : JSON.stringify(item);
        })
        .join("; ");
    }
  } catch {
    // not JSON — fall through to the raw body
  }
  return text || "request failed";
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, init);
  const text = await res.text();
  if (!res.ok) throw new ApiError(res.status, extractDetail(text));
  return parseNs(text) as T;
}

export function getOfi(limit: number): Promise<OfiRow[]> {
  return request(`/metrics/ofi?limit=${limit}`);
}

export function getVolatility(limit: number): Promise<VolatilityRow[]> {
  return request(`/metrics/volatility?limit=${limit}`);
}

export function getVolume(limit: number): Promise<VolumeRow[]> {
  return request(`/metrics/volume?limit=${limit}`);
}

export function getJournal(limit = 100): Promise<JournalEntry[]> {
  return request(`/journal?limit=${limit}`);
}

export function createEntry(entry: NewJournalEntry): Promise<StoredJournalEntry> {
  return request("/journal", {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: stringifyNs(entry),
  });
}

export function analyzeJournal(): Promise<BehavioralAnalysis> {
  return request("/journal/analyze", { method: "POST" });
}
