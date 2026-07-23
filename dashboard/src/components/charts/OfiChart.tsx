"use client";

import {
  Bar,
  BarChart,
  CartesianGrid,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import type { OfiRow } from "@/lib/api";
import { fmtSigned } from "@/lib/format";
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

interface Datum {
  t: number;
  ofi: number;
}

interface BarShapeProps {
  x?: number;
  y?: number;
  width?: number;
  height?: number;
  payload?: Datum;
}

/** Sign-aware bar: 4px rounded data-end, square at the zero baseline, colored
 * by which side of the book dominated (the buy↔sell diverging pair). */
function DivergingBar({ x = 0, y = 0, width = 0, height = 0, payload }: BarShapeProps) {
  const top = Math.min(y, y + height);
  const h = Math.abs(height);
  if (h <= 0 || width <= 0) return null;
  const up = (payload?.ofi ?? 0) >= 0;
  const r = Math.min(4, width / 2, h);
  const fill = up ? "var(--series-buy)" : "var(--series-sell)";
  const d = up
    ? `M${x},${top + h} V${top + r} Q${x},${top} ${x + r},${top} H${x + width - r} ` +
      `Q${x + width},${top} ${x + width},${top + r} V${top + h} Z`
    : `M${x},${top} H${x + width} V${top + h - r} Q${x + width},${top + h} ${x + width - r},${top + h} ` +
      `H${x + r} Q${x},${top + h} ${x},${top + h - r} Z`;
  return <path d={d} fill={fill} />;
}

export function OfiChart({ rows }: { rows: OfiRow[] }) {
  // API returns newest first; time axes read left → right.
  const data: Datum[] = rows
    .map((row) => ({ t: nsToMs(row.bucket_start_ns), ofi: row.ofi }))
    .reverse();

  return (
    <ChartCard
      title="Order-flow imbalance"
      subtitle="(buy − sell) / (buy + sell) per window · +1 all buyers, −1 all sellers"
    >
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
            domain={[-1, 1]}
            ticks={[-1, -0.5, 0, 0.5, 1]}
            tick={AXIS_TICK}
            axisLine={false}
            tickLine={false}
            width={40}
          />
          <ReferenceLine y={0} stroke="var(--baseline)" />
          <Tooltip
            cursor={{ fill: "rgba(255, 255, 255, 0.04)" }}
            content={<ChartTooltip valueFormatter={(v) => fmtSigned(v, 3)} />}
          />
          <Bar dataKey="ofi" name="OFI" maxBarSize={24} shape={<DivergingBar />} isAnimationActive={false} />
        </BarChart>
      </ResponsiveContainer>
    </ChartCard>
  );
}
