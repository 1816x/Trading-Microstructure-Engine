"use client";

import { useState } from "react";

import { analyzeJournal, ApiError, type BehavioralAnalysis, type Severity } from "@/lib/api";

/** Status steps (fixed palette, never categorical) — the word is the label,
 * the dot is the icon, so severity never rides on color alone. */
const SEVERITY_DOT: Record<Severity, string> = {
  low: "var(--muted)",
  medium: "#fab219",
  high: "#ec835a",
};

function SeverityBadge({ severity }: { severity: Severity }) {
  return (
    <span className="inline-flex items-center gap-1.5 text-xs text-ink-2">
      <span
        aria-hidden
        className="h-2 w-2 rounded-full"
        style={{ background: SEVERITY_DOT[severity] }}
      />
      {severity}
    </span>
  );
}

export function AnalysisPanel() {
  const [analysis, setAnalysis] = useState<BehavioralAnalysis | null>(null);
  const [error, setError] = useState<ApiError | null>(null);
  const [loading, setLoading] = useState(false);

  async function run() {
    setLoading(true);
    setError(null);
    try {
      setAnalysis(await analyzeJournal());
    } catch (err) {
      setError(err instanceof ApiError ? err : new ApiError(0, String(err)));
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="flex flex-col gap-3">
      <div className="flex items-center gap-3">
        <button
          type="button"
          onClick={run}
          disabled={loading}
          className="rounded-md border border-hairline bg-page px-3 py-1.5 text-sm hover:border-ink-2 disabled:opacity-50"
        >
          {loading ? "Analyzing…" : "Analyze with Claude"}
        </button>
        <span className="text-xs text-muted">runs the behavioral agent — one API call</span>
      </div>

      {error ? (
        <div className="rounded-md border border-hairline bg-page p-3 text-xs">
          <p className="text-ink-2">{error.detail}</p>
          {error.status === 503 ? (
            <p className="mt-1 text-muted">
              Start the backend with <code className="font-mono">ANTHROPIC_API_KEY</code> set to
              enable the agent.
            </p>
          ) : null}
          {error.status === 502 ? (
            <p className="mt-1 text-muted">
              The model returned no structured analysis — try again, or with more entries.
            </p>
          ) : null}
        </div>
      ) : null}

      {analysis ? (
        <div className="flex flex-col gap-3">
          <p className="text-sm text-ink-2">{analysis.summary}</p>
          {analysis.observations.length > 0 ? (
            <ul className="flex flex-col gap-3">
              {analysis.observations.map((obs, i) => (
                <li key={i} className="rounded-md border border-hairline bg-page p-3">
                  <div className="flex items-baseline justify-between gap-2">
                    <span className="text-sm font-medium">{obs.pattern}</span>
                    <SeverityBadge severity={obs.severity} />
                  </div>
                  <p className="mt-1 text-xs text-ink-2">{obs.bias}</p>
                  <p className="mt-2 text-xs text-muted">{obs.evidence}</p>
                </li>
              ))}
            </ul>
          ) : null}
          <p className="text-xs text-muted">{analysis.disclaimer}</p>
        </div>
      ) : null}
    </div>
  );
}
