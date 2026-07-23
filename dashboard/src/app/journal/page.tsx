"use client";

import { useCallback } from "react";

import { getJournal } from "@/lib/api";
import { useApi } from "@/lib/useApi";
import { AnalysisPanel } from "@/components/AnalysisPanel";
import { EntryForm } from "@/components/EntryForm";
import { JournalTable } from "@/components/JournalTable";
import { ErrorState } from "@/components/states";

export default function JournalPage() {
  const journal = useApi(useCallback(() => getJournal(100), []));

  return (
    <div className="flex flex-col gap-4">
      {journal.error && !journal.data ? (
        <ErrorState error={journal.error} />
      ) : (
        <div className="grid gap-4 lg:grid-cols-3">
          <section className="rounded-lg border border-hairline bg-surface p-4 lg:col-span-2">
            <div className="flex items-baseline justify-between">
              <h2 className="text-sm font-medium">Trade journal</h2>
              <span className="text-xs text-muted">
                {journal.data ? `${journal.data.length} entries · joined to regime at entry` : ""}
              </span>
            </div>
            <div
              className={`mt-3 transition-opacity ${journal.loading ? "opacity-60" : ""}`}
            >
              {journal.data ? <JournalTable entries={journal.data} /> : null}
            </div>
            {journal.error && journal.data ? (
              <p className="mt-2 text-xs text-sell">
                Refresh failed ({journal.error.detail}) — showing the last good data.
              </p>
            ) : null}
          </section>

          <div className="flex flex-col gap-4">
            <section className="rounded-lg border border-hairline bg-surface p-4">
              <h2 className="text-sm font-medium">Log a trade</h2>
              <div className="mt-3">
                <EntryForm onCreated={journal.refetch} />
              </div>
            </section>
          </div>

          <section className="rounded-lg border border-hairline bg-surface p-4 lg:col-span-3">
            <h2 className="text-sm font-medium">Behavioral analysis</h2>
            <p className="mt-0.5 text-xs text-muted">
              Recurring patterns and biases in your own trading, correlated with the regime at
              entry. Not financial advice; no price predictions.
            </p>
            <div className="mt-3">
              <AnalysisPanel />
            </div>
          </section>
        </div>
      )}
    </div>
  );
}
