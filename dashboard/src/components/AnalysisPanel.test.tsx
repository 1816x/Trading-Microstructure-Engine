import { fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { AnalysisPanel } from "./AnalysisPanel";

function stubFetch(status: number, body: string) {
  vi.stubGlobal(
    "fetch",
    vi.fn(async () => ({
      ok: status >= 200 && status < 300,
      status,
      text: async () => body,
    })),
  );
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("AnalysisPanel", () => {
  it("renders the analysis with severity badges and disclaimer", async () => {
    stubFetch(
      200,
      JSON.stringify({
        summary: "You size up after losses.",
        observations: [
          {
            pattern: "Revenge sizing",
            bias: "loss aversion",
            evidence: "entries #3 and #5",
            severity: "high",
          },
          {
            pattern: "Hesitation in high vol",
            bias: "fear of volatility",
            evidence: "entry #7",
            severity: "low",
          },
        ],
        disclaimer: "This is a behavioral analysis of your own trading.",
      }),
    );
    render(<AnalysisPanel />);
    fireEvent.click(screen.getByRole("button", { name: /Analyze with Claude/ }));

    expect(await screen.findByText("You size up after losses.")).toBeInTheDocument();
    expect(screen.getByText("Revenge sizing")).toBeInTheDocument();
    expect(screen.getByText("high")).toBeInTheDocument();
    expect(screen.getByText("low")).toBeInTheDocument();
    expect(
      screen.getByText("This is a behavioral analysis of your own trading."),
    ).toBeInTheDocument();
  });

  it("explains the 503 when the backend has no API key", async () => {
    stubFetch(
      503,
      '{"detail":"ANTHROPIC_API_KEY is not set — the behavioral agent is unavailable"}',
    );
    render(<AnalysisPanel />);
    fireEvent.click(screen.getByRole("button", { name: /Analyze with Claude/ }));

    expect(
      await screen.findByText(/ANTHROPIC_API_KEY is not set/),
    ).toBeInTheDocument();
    expect(screen.getByText(/Start the backend with/)).toBeInTheDocument();
  });

  it("offers a retry hint on 502 (no structured analysis)", async () => {
    stubFetch(502, '{"detail":"the model returned no structured analysis"}');
    render(<AnalysisPanel />);
    fireEvent.click(screen.getByRole("button", { name: /Analyze with Claude/ }));

    expect(
      await screen.findByText("the model returned no structured analysis"),
    ).toBeInTheDocument();
    expect(screen.getByText(/try again, or with more entries/)).toBeInTheDocument();
  });
});
