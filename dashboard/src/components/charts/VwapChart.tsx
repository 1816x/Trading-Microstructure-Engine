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

import type { VolumeRow } from "@/lib/api";
import { fmtPrice } from "@/lib/format";
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

/** VWAP gets its own frame: it's a price while volume is contracts — two
 * measures of different scale never share one chart (no dual axes). */
export function VwapChart({ rows }: { rows: VolumeRow[] }) {
  const data = rows
    .map((row) => ({ t: nsToMs(row.bucket_start_ns), vwap: row.vwap }))
    .reverse();

  return (
    <ChartCard title="VWAP" subtitle="volume-weighted average price per window">
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
            domain={["auto", "auto"]}
            tickFormatter={(v: number) => fmtPrice(v)}
            tick={AXIS_TICK}
            axisLine={false}
            tickLine={false}
            width={72}
          />
          <Tooltip
            cursor={{ stroke: "var(--baseline)" }}
            content={<ChartTooltip valueFormatter={(v) => fmtPrice(v)} />}
          />
          <Line
            dataKey="vwap"
            name="VWAP"
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
