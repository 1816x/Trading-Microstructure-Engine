"use client";

import { useState } from "react";

import { ApiError, createEntry, type NewJournalEntry, type Side } from "@/lib/api";
import { msToNs } from "@/lib/nsjson";

const INPUT =
  "w-full rounded-md border border-hairline bg-page px-2.5 py-1.5 text-sm " +
  "placeholder:text-muted focus:border-ink-2 focus:outline-none";
const LABEL = "flex flex-col gap-1 text-xs text-ink-2";

/** A datetime-local value is the user's local wall time; the journal stores
 * the absolute instant as epoch nanoseconds. */
function localToNs(value: string): bigint {
  return msToNs(new Date(value).getTime());
}

export function EntryForm({ onCreated }: { onCreated: () => void }) {
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = event.currentTarget;
    const fields = new FormData(form);

    const enteredAt = String(fields.get("entered_at") ?? "");
    const exitedAt = String(fields.get("exited_at") ?? "");
    // Mirror of the server rule (422): catch it before spending the request.
    if (exitedAt && enteredAt && localToNs(exitedAt) < localToNs(enteredAt)) {
      setError("exit time must be at or after entry time");
      return;
    }

    const exitPrice = String(fields.get("exit_price") ?? "");
    const pnl = String(fields.get("pnl") ?? "");
    const notes = String(fields.get("notes") ?? "");
    const emotion = String(fields.get("emotion") ?? "");
    const entry: NewJournalEntry = {
      symbol: String(fields.get("symbol") ?? ""),
      side: fields.get("side") as Side,
      entered_at_ns: localToNs(enteredAt),
      entry_price: Number(fields.get("entry_price")),
      size: Number(fields.get("size")),
      exited_at_ns: exitedAt ? localToNs(exitedAt) : null,
      exit_price: exitPrice ? Number(exitPrice) : null,
      pnl: pnl ? Number(pnl) : null,
      notes: notes || null,
      emotion: emotion || null,
    };

    setSubmitting(true);
    setError(null);
    try {
      await createEntry(entry);
      form.reset();
      onCreated();
    } catch (err) {
      setError(err instanceof ApiError ? err.detail : String(err));
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <form onSubmit={handleSubmit} className="flex flex-col gap-3">
      <div className="grid grid-cols-2 gap-3">
        <label className={LABEL}>
          Symbol
          <input name="symbol" required placeholder="MNQ" className={INPUT} />
        </label>
        <label className={LABEL}>
          Side
          <select name="side" required className={INPUT} defaultValue="long">
            <option value="long">long</option>
            <option value="short">short</option>
          </select>
        </label>
        <label className={LABEL}>
          Entered at (local time)
          <input name="entered_at" type="datetime-local" step="1" required className={INPUT} />
        </label>
        <label className={LABEL}>
          Exited at (optional)
          <input name="exited_at" type="datetime-local" step="1" className={INPUT} />
        </label>
        <label className={LABEL}>
          Entry price
          <input
            name="entry_price"
            type="number"
            step="any"
            min="0.01"
            required
            className={INPUT}
          />
        </label>
        <label className={LABEL}>
          Exit price (optional)
          <input name="exit_price" type="number" step="any" min="0.01" className={INPUT} />
        </label>
        <label className={LABEL}>
          Size (contracts)
          <input name="size" type="number" step="1" min="1" required className={INPUT} />
        </label>
        <label className={LABEL}>
          PnL (optional)
          <input name="pnl" type="number" step="any" className={INPUT} />
        </label>
      </div>
      <label className={LABEL}>
        Emotion (optional)
        <input name="emotion" placeholder="calm, anxious, revenge…" className={INPUT} />
      </label>
      <label className={LABEL}>
        Notes (optional)
        <textarea name="notes" rows={2} placeholder="what was the plan?" className={INPUT} />
      </label>
      {error ? (
        <p role="alert" className="text-xs text-sell">
          {error}
        </p>
      ) : null}
      <button
        type="submit"
        disabled={submitting}
        className="self-start rounded-md border border-hairline bg-page px-3 py-1.5 text-sm text-ink hover:border-ink-2 disabled:opacity-50"
      >
        {submitting ? "Logging…" : "Log trade"}
      </button>
    </form>
  );
}
