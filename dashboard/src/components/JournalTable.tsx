import type { JournalEntry } from "@/lib/api";
import { fmtInt, fmtPrice, fmtSig, fmtSigned } from "@/lib/format";
import { formatNs } from "@/lib/nsjson";

const DASH = "—";

/** The column header already says (UTC); repeating it per row costs width the
 * regime columns need. */
function enteredCell(ns: bigint): string {
  return formatNs(ns).replace(" UTC", "");
}

function SideBadge({ side }: { side: JournalEntry["side"] }) {
  return (
    <span className="inline-flex items-center gap-1.5">
      <span
        aria-hidden
        className="h-2 w-2 rounded-full"
        style={{ background: side === "long" ? "var(--series-buy)" : "var(--series-sell)" }}
      />
      {side}
    </span>
  );
}

/** Journal entries joined to their market regime. Regime columns are — when no
 * metric bucket covers the entry time. */
export function JournalTable({ entries }: { entries: JournalEntry[] }) {
  if (entries.length === 0) {
    return (
      <p className="text-sm text-ink-2">
        No trades logged yet — add one with the form, or seed the sample journal:{" "}
        <code className="font-mono text-xs">
          python3 -m backtest.coach --load data/sample_journal.csv --db metrics.db
        </code>
      </p>
    );
  }
  return (
    <div className="overflow-x-auto">
      <table className="w-full whitespace-nowrap text-xs">
        <thead>
          <tr className="border-b border-hairline text-left text-muted">
            <th className="py-2 pr-4 font-normal">Entered (UTC)</th>
            <th className="py-2 pr-4 font-normal">Symbol</th>
            <th className="py-2 pr-4 font-normal">Side</th>
            <th className="py-2 pr-4 text-right font-normal">Size</th>
            <th className="py-2 pr-4 text-right font-normal">Entry</th>
            <th className="py-2 pr-4 text-right font-normal">Exit</th>
            <th className="py-2 pr-4 text-right font-normal">PnL</th>
            <th className="py-2 pr-4 text-right font-normal">Regime OFI</th>
            <th className="py-2 pr-4 text-right font-normal">Regime vol</th>
            <th className="py-2 pr-4 text-right font-normal">Regime VWAP</th>
            <th className="py-2 pr-4 font-normal">Emotion</th>
            <th className="py-2 font-normal">Notes</th>
          </tr>
        </thead>
        <tbody className="tabular-nums">
          {entries.map((entry) => (
            <tr key={entry.id} className="border-b border-hairline/50">
              <td className="py-2 pr-4 font-mono">{enteredCell(entry.entered_at_ns)}</td>
              <td className="py-2 pr-4">{entry.symbol}</td>
              <td className="py-2 pr-4">
                <SideBadge side={entry.side} />
              </td>
              <td className="py-2 pr-4 text-right">{fmtInt(entry.size)}</td>
              <td className="py-2 pr-4 text-right">{fmtPrice(entry.entry_price)}</td>
              <td className="py-2 pr-4 text-right">
                {entry.exit_price === null ? DASH : fmtPrice(entry.exit_price)}
              </td>
              <td className="py-2 pr-4 text-right">
                {entry.pnl === null ? DASH : fmtSigned(entry.pnl, 2)}
              </td>
              <td className="py-2 pr-4 text-right">
                {entry.regime_ofi === null ? DASH : fmtSigned(entry.regime_ofi, 3)}
              </td>
              <td className="py-2 pr-4 text-right">
                {entry.regime_realized_volatility === null
                  ? DASH
                  : fmtSig(entry.regime_realized_volatility, 4)}
              </td>
              <td className="py-2 pr-4 text-right">
                {entry.regime_vwap === null ? DASH : fmtPrice(entry.regime_vwap)}
              </td>
              <td className="py-2 pr-4 text-ink-2">{entry.emotion ?? DASH}</td>
              <td className="max-w-64 truncate py-2 text-ink-2" title={entry.notes ?? undefined}>
                {entry.notes ?? DASH}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
