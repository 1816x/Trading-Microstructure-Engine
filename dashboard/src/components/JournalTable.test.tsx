import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import type { JournalEntry } from "@/lib/api";

import { JournalTable } from "./JournalTable";

const NS = 1_760_000_030_000_000_000n;

function entry(overrides: Partial<JournalEntry>): JournalEntry {
  return {
    id: 1,
    symbol: "MNQ",
    side: "long",
    entered_at_ns: NS,
    exited_at_ns: null,
    entry_price: 21400,
    exit_price: null,
    size: 2,
    pnl: null,
    notes: null,
    emotion: null,
    created_at_ns: NS,
    regime_bucket_start_ns: null,
    regime_window_ns: null,
    regime_ofi: null,
    regime_realized_volatility: null,
    regime_vwap: null,
    ...overrides,
  };
}

describe("JournalTable", () => {
  it("shows an empty-state hint when there are no entries", () => {
    render(<JournalTable entries={[]} />);
    expect(screen.getByText(/No trades logged yet/)).toBeInTheDocument();
  });

  it("renders regime columns when the join found a bucket", () => {
    render(
      <JournalTable
        entries={[
          entry({
            regime_bucket_start_ns: NS,
            regime_window_ns: 1_000_000_000n,
            regime_ofi: 0.42,
            regime_realized_volatility: 0.000123,
            regime_vwap: 21401.25,
          }),
        ]}
      />,
    );
    expect(screen.getByText("+0.420")).toBeInTheDocument();
    expect(screen.getByText("0.000123")).toBeInTheDocument();
    expect(screen.getByText("21,401.25")).toBeInTheDocument();
    expect(screen.getByText("2025-10-09 08:53:50 UTC")).toBeInTheDocument();
  });

  it("dashes out regime columns when no bucket covers the entry", () => {
    render(<JournalTable entries={[entry({ pnl: -125.5, emotion: "anxious" })]} />);
    // exit, regime ofi, regime vol, regime vwap, notes — all missing.
    expect(screen.getAllByText("—").length).toBeGreaterThanOrEqual(4);
    expect(screen.getByText("-125.50")).toBeInTheDocument();
    expect(screen.getByText("anxious")).toBeInTheDocument();
    expect(screen.getByText("long")).toBeInTheDocument();
  });
});
