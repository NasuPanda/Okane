import { Bar, Cell, ComposedChart, Line, ReferenceLine, XAxis, YAxis } from "recharts";

import type { TimelinePoint } from "@/api/types";
import { ChartContainer, ChartTooltip, ChartTooltipContent, type ChartConfig } from "@/components/ui/chart";
import { eur, monthLabel, shortEur } from "@/lib/utils";

const config: ChartConfig = {
  gap: { label: "Gap", color: "var(--hot)" },
  balance: { label: "Month-end balance", color: "var(--chart-1)" },
  expected: { label: "What we'd expect", color: "var(--sentinel)" },
};

/** Month-end balance, expected balance and gap (brief section 8, gap timeline).
 *  Bars are the gap: coral where it is over the materiality limit, green where it is fine. */
export function GapChart({ points, materiality }: { points: TimelinePoint[]; materiality: number }) {
  const data = points.slice(-30);
  return (
    <ChartContainer config={config} className="h-64 w-full">
      <ComposedChart data={data} margin={{ top: 8, right: 4, left: 4, bottom: 0 }} barCategoryGap={2}>
        <XAxis
          dataKey="month"
          tickLine={false}
          axisLine={false}
          tickFormatter={monthLabel}
          interval="preserveStartEnd"
          minTickGap={28}
        />
        <YAxis
          orientation="right"
          tickLine={false}
          axisLine={false}
          width={52}
          tickFormatter={(v: number) => shortEur(v)}
        />
        <ReferenceLine y={materiality} stroke="var(--chart-3)" strokeDasharray="3 4" />
        <ReferenceLine y={-materiality} stroke="var(--chart-3)" strokeDasharray="3 4" />
        <ReferenceLine y={0} stroke="var(--border)" />
        <ChartTooltip
          cursor={{ fill: "var(--muted)", opacity: 0.6 }}
          content={({ active, payload, label }) => (
            <ChartTooltipContent
              active={active}
              payload={payload}
              label={label}
              labelFormatter={(l) => monthLabel(l)}
              formatter={(v) => eur(v)}
            />
          )}
        />
        <Bar dataKey="gap" maxBarSize={7} radius={[2, 2, 2, 2]} isAnimationActive={false}>
          {data.map((p) => (
            <Cell key={p.month} fill={Math.abs(p.gap) >= materiality ? "var(--hot)" : "var(--pulse)"} />
          ))}
        </Bar>
        <Line
          dataKey="balance"
          type="monotone"
          stroke="var(--color-balance)"
          strokeWidth={1.5}
          dot={false}
          isAnimationActive={false}
        />
        <Line
          dataKey="expected"
          type="stepAfter"
          stroke="var(--color-expected)"
          strokeWidth={1.25}
          strokeDasharray="4 3"
          dot={false}
          isAnimationActive={false}
        />
      </ComposedChart>
    </ChartContainer>
  );
}
