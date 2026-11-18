import * as React from "react";
import * as RechartsPrimitive from "recharts";

import { cn } from "@/lib/utils";

/** shadcn-style chart wrapper: the config maps series keys to labels and colours. */
export type ChartConfig = Record<string, { label?: React.ReactNode; color?: string }>;

const ChartContext = React.createContext<{ config: ChartConfig } | null>(null);

function useChart() {
  const context = React.useContext(ChartContext);
  if (!context) throw new Error("useChart must be used within a <ChartContainer />");
  return context;
}

export function ChartContainer({
  config,
  className,
  children,
  ...props
}: Omit<React.ComponentProps<"div">, "children"> & {
  config: ChartConfig;
  children: React.ReactElement;
}) {
  const style = Object.fromEntries(
    Object.entries(config)
      .filter(([, v]) => v.color)
      .map(([k, v]) => [`--color-${k}`, v.color]),
  ) as React.CSSProperties;
  return (
    <ChartContext.Provider value={{ config }}>
      <div
        data-slot="chart"
        style={style}
        className={cn(
          "flex justify-center text-xs [&_.recharts-cartesian-axis-tick_text]:fill-muted-foreground [&_.recharts-cartesian-grid_line]:stroke-border [&_.recharts-surface]:outline-none",
          className,
        )}
        {...props}
      >
        <RechartsPrimitive.ResponsiveContainer>{children}</RechartsPrimitive.ResponsiveContainer>
      </div>
    </ChartContext.Provider>
  );
}

export const ChartTooltip = RechartsPrimitive.Tooltip;

type TooltipItem = { dataKey?: unknown; name?: unknown; value?: unknown; color?: string };

export function ChartTooltipContent({
  active,
  payload,
  label,
  formatter,
  labelFormatter,
}: {
  active?: boolean;
  payload?: readonly TooltipItem[];
  label?: unknown;
  formatter?: (value: number) => React.ReactNode;
  labelFormatter?: (label: string) => React.ReactNode;
}) {
  const { config } = useChart();
  if (!active || !payload?.length) return null;
  return (
    <div className="min-w-44 rounded-lg bg-dock px-3 py-2 text-xs text-white shadow-xl">
      <div className="mb-1.5 text-white/60">{labelFormatter ? labelFormatter(String(label)) : String(label)}</div>
      {payload.map((item) => {
        const key = String(item.dataKey ?? item.name);
        return (
          <div key={key} className="flex items-center justify-between gap-4 py-0.5">
            <span className="flex items-center gap-1.5 text-white/75">
              <span className="size-2 rounded-[2px]" style={{ background: config[key]?.color ?? item.color }} />
              {config[key]?.label ?? key}
            </span>
            <span className="num font-medium">
              {formatter && typeof item.value === "number" ? formatter(item.value) : String(item.value ?? "")}
            </span>
          </div>
        );
      })}
    </div>
  );
}
