import { describe, expect, it } from "vitest";

import { formatNs, formatNsTime, msToNs, nsToMs, parseNs, stringifyNs } from "@/lib/nsjson";

// The epoch used across the repo's docs (~2025-10-09T08:53:50Z). As a float64
// it would round to a different integer, which is the whole point.
const SAMPLE_NS = 1_760_000_030_000_000_000n;

describe("parseNs", () => {
  it("materializes *_ns integers as exact BigInts", () => {
    const parsed = parseNs(`{"entered_at_ns":${SAMPLE_NS}}`) as { entered_at_ns: bigint };
    expect(parsed.entered_at_ns).toBe(SAMPLE_NS);
  });

  it("preserves integers JSON.parse would round", () => {
    // 2^53 + 1 — Number(9007199254740993) rounds to ...992.
    const parsed = parseNs('{"bucket_start_ns":9007199254740993}') as {
      bucket_start_ns: bigint;
    };
    expect(parsed.bucket_start_ns).toBe(9_007_199_254_740_993n);
  });

  it("leaves null *_ns fields as null", () => {
    const parsed = parseNs('{"exited_at_ns":null}') as { exited_at_ns: null };
    expect(parsed.exited_at_ns).toBeNull();
  });

  it("leaves non-ns numbers as numbers", () => {
    const parsed = parseNs('{"id":7,"entry_price":21400.5,"ofi":-0.42}') as Record<
      string,
      number
    >;
    expect(parsed.id).toBe(7);
    expect(parsed.entry_price).toBe(21400.5);
    expect(parsed.ofi).toBe(-0.42);
  });

  it("never touches digits inside strings", () => {
    const parsed = parseNs(`{"notes":"exited at ${SAMPLE_NS} ns"}`) as { notes: string };
    expect(parsed.notes).toBe(`exited at ${SAMPLE_NS} ns`);
  });

  it("handles arrays of rows (the list endpoints)", () => {
    const parsed = parseNs(
      `[{"bucket_start_ns":${SAMPLE_NS},"window_ns":1000000000,"ofi":0.1},` +
        `{"bucket_start_ns":${SAMPLE_NS + 1_000_000_000n},"window_ns":1000000000,"ofi":-0.2}]`,
    ) as { bucket_start_ns: bigint; window_ns: bigint; ofi: number }[];
    expect(parsed).toHaveLength(2);
    expect(parsed[0].bucket_start_ns).toBe(SAMPLE_NS);
    expect(parsed[1].bucket_start_ns).toBe(SAMPLE_NS + 1_000_000_000n);
    expect(parsed[0].window_ns).toBe(1_000_000_000n);
  });
});

describe("stringifyNs", () => {
  it("serializes BigInt as an unquoted JSON integer", () => {
    expect(stringifyNs({ entered_at_ns: SAMPLE_NS })).toBe(`{"entered_at_ns":${SAMPLE_NS}}`);
  });

  it("round-trips a mixed body exactly", () => {
    const body = {
      symbol: "MNQ",
      side: "long",
      entered_at_ns: SAMPLE_NS,
      entry_price: 21400,
      size: 1,
      exited_at_ns: null,
      notes: "id 9007199254740993 in a string",
    };
    expect(parseNs(stringifyNs(body))).toEqual(body);
  });
});

describe("ns helpers", () => {
  it("nsToMs truncates to a safe millisecond Number", () => {
    expect(nsToMs(SAMPLE_NS)).toBe(1_760_000_030_000);
    expect(Number.isSafeInteger(nsToMs(SAMPLE_NS))).toBe(true);
  });

  it("msToNs lifts milliseconds back to nanoseconds", () => {
    expect(msToNs(1_760_000_030_000)).toBe(SAMPLE_NS);
  });

  it("formatNs renders a UTC timestamp", () => {
    expect(formatNs(SAMPLE_NS)).toBe("2025-10-09 08:53:50 UTC");
  });

  it("formatNsTime renders the time of day", () => {
    expect(formatNsTime(SAMPLE_NS)).toBe("08:53:50");
  });
});
