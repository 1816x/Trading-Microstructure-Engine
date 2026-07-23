"use client";

import {
  Bar,
  BarChart,
  CartesianGrid,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import type { VolumeRow } from "@/lib/api";
import { fmtInt } from "@/lib/format";
import { nsToMs } from "@/lib/nsjson";

import {
  AXIS_LINE,
  AXIS_TICK,
  CHART_HEIGHT,
  ChartCard,
  ChartTooltip,
  fmtMsTime,
  GRID,
  LegendRow,
} from "./common";

export function VolumeChart({ rows }: { rows: VolumeRow[] }) {
  const data = rows
    .map((row) => ({
      t: nsToMs(row.bucket_start_ns),
      buy: row.buy_volume,
      sell: row.sell_volume,
    }))
    .reverse();

  return (
    <ChartCard title="Volume" subtitle="contracts per window, by aggressor side">
      <ResponsiveContainer width="100%" height={CHART_HEIGHT}>
        <BarChart data={data} margin={{ top: 4, right: 8, bottom: 0, left: 0 }}>
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
            tickFormatter={(v: number) => fmtInt(v)}
            tick={AXIS_TICK}
            axisLine={false}
            tickLine={false}
            width={40}
          />
          <Tooltip
            cursor={{ fill: "rgba(255, 255, 255, 0.04)" }}
            content={<ChartTooltip valueFormatter={(v) => fmtInt(v)} />}
          />
          <Bar
            dataKey="buy"
            name="Buy volume"
            stackId="volume"
            fill="var(--series-buy)"
            maxBarSize={24}
            isAnimationActive={false}
          />
          <Bar
            dataKey="sell"
            name="Sell volume"
            stackId="volume"
            fill="var(--series-sell)"
            maxBarSize={24}
            isAnimationActive={false}
          />
        </BarChart>
      </ResponsiveContainer>
      <LegendRow
        items={[
          { label: "Buy volume", color: "var(--series-buy)" },
          { label: "Sell volume", color: "var(--series-sell)" },
        ]}
      />
    </ChartCard>
  );
}
