import { afterEach, describe, expect, it, vi } from "vitest";

import { ApiError, analyzeJournal, createEntry, getJournal, getOfi } from "@/lib/api";

const SAMPLE_NS = 1_760_000_030_000_000_000n;

function fakeResponse(status: number, body: string): Response {
  return {
    ok: status >= 200 && status < 300,
    status,
    text: async () => body,
  } as unknown as Response;
}

function stubFetch(status: number, body: string) {
  const mock = vi.fn(async () => fakeResponse(status, body));
  vi.stubGlobal("fetch", mock);
  return mock;
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("api client", () => {
  it("parses *_ns fields of metric rows as BigInt", async () => {
    stubFetch(200, `[{"bucket_start_ns":${SAMPLE_NS},"window_ns":1000000000,"ofi":0.25}]`);
    const rows = await getOfi(100);
    expect(rows[0].bucket_start_ns).toBe(SAMPLE_NS);
    expect(rows[0].ofi).toBe(0.25);
  });

  it("parses journal rows including null regime columns", async () => {
    stubFetch(
      200,
      `[{"id":1,"symbol":"MNQ","side":"long","entered_at_ns":${SAMPLE_NS},` +
        `"exited_at_ns":null,"entry_price":21400,"exit_price":null,"size":1,` +
        `"pnl":null,"notes":null,"emotion":"calm","created_at_ns":${SAMPLE_NS},` +
        `"regime_bucket_start_ns":null,"regime_window_ns":null,"regime_ofi":null,` +
        `"regime_realized_volatility":null,"regime_vwap":null}]`,
    );
    const entries = await getJournal();
    expect(entries[0].entered_at_ns).toBe(SAMPLE_NS);
    expect(entries[0].regime_ofi).toBeNull();
  });

  it("POSTs journal entries with *_ns as unquoted JSON integers", async () => {
    const mock = stubFetch(201, `{"id":1,"entered_at_ns":${SAMPLE_NS}}`);
    await createEntry({
      symbol: "MNQ",
      side: "long",
      entered_at_ns: SAMPLE_NS,
      entry_price: 21400,
      size: 1,
    });
    const [url, init] = mock.mock.calls[0] as unknown as [string, RequestInit];
    expect(url).toBe("/api/backend/journal");
    expect(init.method).toBe("POST");
    expect(init.headers).toEqual({ "content-type": "application/json" });
    expect(init.body).toContain(`"entered_at_ns":${SAMPLE_NS}`);
    expect(init.body).not.toContain(`"${SAMPLE_NS}"`);
  });

  it("maps a string detail to ApiError (503 without engine DB / API key)", async () => {
    stubFetch(503, '{"detail":"metrics database not found at \'metrics.db\' — run the engine first"}');
    const error = await getOfi(100).catch((e: unknown) => e);
    expect(error).toBeInstanceOf(ApiError);
    expect((error as ApiError).status).toBe(503);
    expect((error as ApiError).detail).toContain("run the engine first");
  });

  it("joins 422 validation items into a readable detail", async () => {
    stubFetch(
      422,
      '{"detail":[{"type":"value_error","loc":["body"],"msg":"exited_at_ns must be >= entered_at_ns"}]}',
    );
    const error = await createEntry({
      symbol: "MNQ",
      side: "long",
      entered_at_ns: SAMPLE_NS,
      entry_price: 21400,
      size: 1,
    }).catch((e: unknown) => e);
    expect((error as ApiError).status).toBe(422);
    expect((error as ApiError).detail).toBe("body: exited_at_ns must be >= entered_at_ns");
  });

  it("falls back to the raw body when the error is not JSON", async () => {
    stubFetch(502, "Bad Gateway");
    const error = await analyzeJournal().catch((e: unknown) => e);
    expect((error as ApiError).status).toBe(502);
    expect((error as ApiError).detail).toBe("Bad Gateway");
  });
});
