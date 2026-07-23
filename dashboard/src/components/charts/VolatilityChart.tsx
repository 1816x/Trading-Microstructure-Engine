"use client";

import {
  CartesianGrid,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import type { VolatilityRow } from "@/lib/api";
import { fmtSig } from "@/lib/format";
import { nsToMs } from "@/lib/nsjson";

import {
  AXIS_LINE,
  AXIS_TICK,
  CHART_HEIGHT,
  ChartCard,
  ChartTooltip,
  fmtMsTime,
  GRID,
} from "./common";

export function VolatilityChart({ rows }: { rows: VolatilityRow[] }) {
  const data = rows
    .map((row) => ({ t: nsToMs(row.bucket_start_ns), vol: row.realized_volatility }))
    .reverse();

  return (
    <ChartCard
      title="Realized volatility"
      subtitle="per window, from tick-by-tick log returns (boundary move included)"
    >
      <ResponsiveContainer width="100%" height={CHART_HEIGHT}>
        <LineChart data={data} margin={{ top: 4, right: 8, bottom: 0, left: 0 }}>
          <CartesianGrid {...GRID} />
          <XAxis
            dataKey="t"
            type="number"
            domain={["dataMin", "dataMax"]}
            tickFormatter={fmtMsTime}
            tick={AXIS_TICK}
            axisLine={AXIS_LINE}
            tickLine={false}
            tickMargin={8}
          />
          <YAxis
            domain={[0, "auto"]}
            tickFormatter={(v: number) => fmtSig(v)}
            tick={AXIS_TICK}
            axisLine={false}
            tickLine={false}
            width={56}
          />
          <Tooltip
            cursor={{ stroke: "var(--baseline)" }}
            content={<ChartTooltip valueFormatter={(v) => fmtSig(v, 4)} />}
          />
          <Line
            dataKey="vol"
            name="Realized volatility"
            stroke="var(--series-1)"
            strokeWidth={2}
            strokeLinejoin="round"
            strokeLinecap="round"
            dot={false}
            activeDot={{ r: 4, stroke: "var(--surface)", strokeWidth: 2 }}
            isAnimationActive={false}
          />
        </LineChart>
      </ResponsiveContainer>
    </ChartCard>
  );
}
