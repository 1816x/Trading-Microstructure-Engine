"use client";

/**
 * Shared chart chrome. Every chart draws on the same tokens (see globals.css),
 * the same recessive axes and the same tooltip: values lead in primary ink,
 * series names follow in secondary, keyed by a short stroke of the series
 * color — text never wears the data color.
 */

import type { ReactNode } from "react";

export const CHART_HEIGHT = 240;

export const GRID = { stroke: "var(--grid)", vertical: false } as const;

export const AXIS_TICK = { fill: "var(--muted)", fontSize: 11 } as const;

export const AXIS_LINE = { stroke: "var(--baseline)" } as const;

/** Time-of-day label for the x axis (buckets are UTC nanosecond epochs → ms). */
export function fmtMsTime(ms: number): string {
  return new Date(ms).toISOString().slice(11, 19);
}

/** Full timestamp for tooltip headers. */
export function fmtMsFull(ms: number): string {
  return `${new Date(ms).toISOString().slice(0, 19).replace("T", " ")} UTC`;
}

export function ChartCard({
  title,
  subtitle,
  children,
}: {
  title: string;
  subtitle?: string;
  children: ReactNode;
}) {
  return (
    <section className="rounded-lg border border-hairline bg-surface p-4">
      <h2 className="text-sm font-medium">{title}</h2>
      {subtitle ? <p className="mt-0.5 text-xs text-muted">{subtitle}</p> : null}
      <div className="mt-3">{children}</div>
    </section>
  );
}

interface TooltipRow {
  name?: unknown;
  value?: unknown;
  color?: string;
}

export interface ChartTooltipProps {
  /** Injected by Recharts when passed as <Tooltip content={...}>. */
  active?: boolean;
  label?: unknown;
  payload?: ReadonlyArray<TooltipRow>;
  /** Ours. */
  valueFormatter: (value: number, name: string) => string;
}

export function ChartTooltip({ active, label, payload, valueFormatter }: ChartTooltipProps) {
  if (!active || !payload || payload.length === 0) return null;
  return (
    <div className="rounded-md border border-hairline bg-page px-3 py-2 text-xs shadow-lg">
      {typeof label === "number" ? (
        <div className="mb-1 text-muted">{fmtMsFull(label)}</div>
      ) : null}
      {payload.map((row, i) => (
        <div key={i} className="flex items-center gap-2 py-0.5">
          <span
            aria-hidden
            className="h-3 w-[3px] rounded-full"
            style={{ background: row.color ?? "var(--series-1)" }}
          />
          <span className="font-semibold text-ink">
            {typeof row.value === "number"
              ? valueFormatter(row.value, String(row.name ?? ""))
              : String(row.value ?? "")}
          </span>
          <span className="text-ink-2">{String(row.name ?? "")}</span>
        </div>
      ))}
    </div>
  );
}

/** Legend chip row — only rendered for charts with two or more series. */
export function LegendRow({ items }: { items: { label: string; color: string }[] }) {
  return (
    <div className="mt-2 flex gap-4 text-xs text-ink-2">
      {items.map(({ label, color }) => (
        <span key={label} className="inline-flex items-center gap-1.5">
          <span aria-hidden className="h-2.5 w-2.5 rounded-sm" style={{ background: color }} />
          {label}
        </span>
      ))}
    </div>
  );
}
