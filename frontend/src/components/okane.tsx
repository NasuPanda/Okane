import {
  AlertTriangle,
  ArrowRightLeft,
  Clock3,
  Coins,
  EyeOff,
  FileWarning,
  Repeat2,
  SpellCheck,
  TrendingUp,
  CalendarX2,
  Scale,
  Undo2,
} from "lucide-react";
import type * as React from "react";

import type { ExceptionRecord, ExceptionType, Status } from "@/api/types";
import { Badge } from "@/components/ui/badge";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { STATUS_LABEL, TYPE_LABEL, WEIGHT_LABEL } from "@/lib/labels";
import { cn } from "@/lib/utils";

const TYPE_ICON: Record<ExceptionType, React.ComponentType<{ className?: string }>> = {
  pulse_gap: Scale,
  pulse_missing_payment: Clock3,
  pulse_spike: TrendingUp,
  pulse_missing_batch: CalendarX2,
  label_mismatch: ArrowRightLeft,
  sentinel_outlier: AlertTriangle,
  sentinel_two_currencies: Coins,
  sentinel_currency_code: FileWarning,
  sentinel_reversal: Undo2,
  typo: SpellCheck,
  miner_cluster: Repeat2,
};

export function TypeLabel({ type, className }: { type: ExceptionType; className?: string }) {
  const Icon = TYPE_ICON[type];
  return (
    <span className={cn("eyebrow inline-flex items-center gap-1.5", className)}>
      <Icon className="size-3.5" />
      {TYPE_LABEL[type]}
    </span>
  );
}

/** "N days before the close review" (brief section 9), or why today's process misses it. */
export function LeadBadge({ record, size = "sm" }: { record: ExceptionRecord; size?: "sm" | "lg" }) {
  const basis = String(record.facts.today_detection_basis ?? "");
  const lead = record.lead_days;
  const big = size === "lg";
  if (lead === null || lead === undefined) {
    return (
      <Tooltip>
        <TooltipTrigger asChild>
          <span
            className={cn(
              "inline-flex items-center gap-1.5 rounded-full bg-dock font-medium whitespace-nowrap text-white",
              big ? "px-3 py-1.5 text-sm" : "px-2 py-0.5 text-[11px]",
            )}
          >
            <EyeOff className={big ? "size-4 text-signal" : "size-3 text-signal"} />
            Today's process: not detected
          </span>
        </TooltipTrigger>
        <TooltipContent>Neither the 365-day ageing rule nor the close review sees this kind of finding.</TooltipContent>
      </Tooltip>
    );
  }
  const what = basis.includes("ageing") ? "the ageing rule" : "the close review";
  const earlier = lead >= 0;
  return (
    <Tooltip>
      <TooltipTrigger asChild>
        <span
          className={cn(
            "inline-flex items-center gap-1.5 rounded-full font-medium whitespace-nowrap",
            earlier ? "bg-dock text-white" : "bg-muted text-muted-foreground",
            big ? "px-3 py-1.5 text-sm" : "px-2 py-0.5 text-[11px]",
          )}
        >
          <Clock3 className={cn(big ? "size-4" : "size-3", earlier && "text-signal")} />
          <span className="num">{Math.abs(lead)}</span> days {earlier ? "before" : "after"} {what}
        </span>
      </TooltipTrigger>
      <TooltipContent>
        Okane can flag it on {record.first_signal}; today's process would on {record.today_detection} ({basis}).
      </TooltipContent>
    </Tooltip>
  );
}

export function StatusPill({ status }: { status: Status }) {
  const variant = { new: "outline", explained: "signal", dismissed: "muted", escalated: "warn" } as const;
  return <Badge variant={variant[status]}>{STATUS_LABEL[status]}</Badge>;
}

export function ScoreBar({ record }: { record: ExceptionRecord }) {
  return (
    <Tooltip>
      <TooltipTrigger asChild>
        <div className="flex w-24 items-center gap-2">
          <span className="num w-9 text-right text-sm font-medium">{record.score.toFixed(0)}</span>
          <div className="h-1 flex-1 overflow-hidden rounded-full bg-muted">
            <div className="h-full rounded-full bg-foreground" style={{ width: `${Math.min(record.score, 100)}%` }} />
          </div>
        </div>
      </TooltipTrigger>
      <TooltipContent>
        <div className="mb-1 text-white/60">Rank points from the controller's weights</div>
        {Object.entries(record.score_breakdown).map(([k, v]) => (
          <div key={k} className="flex justify-between gap-6">
            <span>{WEIGHT_LABEL[k] ?? k}</span>
            <span className="num">{v.toFixed(1)}</span>
          </div>
        ))}
      </TooltipContent>
    </Tooltip>
  );
}

export function Segmented<T extends string>({
  value,
  options,
  onChange,
  className,
}: {
  value: T;
  options: { value: T; label: React.ReactNode }[];
  onChange: (value: T) => void;
  className?: string;
}) {
  return (
    <div className={cn("inline-flex items-center gap-4", className)} role="tablist">
      {options.map((option) => (
        <button
          key={option.value}
          role="tab"
          aria-selected={option.value === value}
          onClick={() => onChange(option.value)}
          className={cn(
            "border-b pb-1 text-sm transition",
            option.value === value
              ? "border-foreground text-foreground"
              : "border-transparent text-muted-foreground hover:text-foreground",
          )}
        >
          {option.label}
        </button>
      ))}
    </div>
  );
}

export function Chip({
  active,
  children,
  onClick,
  count,
}: {
  active?: boolean;
  children: React.ReactNode;
  onClick?: () => void;
  count?: number;
}) {
  return (
    <button
      onClick={onClick}
      className={cn(
        "inline-flex h-9 items-center gap-2 rounded-full border px-4 text-sm transition",
        active ? "border-foreground bg-foreground text-white" : "border-border bg-secondary hover:bg-accent",
      )}
    >
      {children}
      {count !== undefined && (
        <span className={cn("num text-xs", active ? "text-signal" : "text-muted-foreground")}>{count}</span>
      )}
    </button>
  );
}

export function PageHeader({
  title,
  trail,
  actions,
}: {
  title: string;
  trail: string[];
  actions?: React.ReactNode;
}) {
  return (
    <div className="flex flex-wrap items-end justify-between gap-4">
      <div className="flex items-baseline gap-5">
        <h1 className="text-[2rem] leading-none font-light tracking-tight">{title}</h1>
        <div className="flex items-center gap-2 text-xs text-muted-foreground">
          {trail.map((part, i) => (
            <span key={part} className="flex items-center gap-2">
              {i > 0 && <span className="text-border">/</span>}
              {part}
            </span>
          ))}
        </div>
      </div>
      {actions && <div className="flex items-center gap-2">{actions}</div>}
    </div>
  );
}

export function Kpi({ label, value, unit, note }: { label: string; value: React.ReactNode; unit?: string; note?: string }) {
  return (
    <div className="flex min-w-0 flex-col gap-2 px-6 first:pl-0">
      <span className="eyebrow">{label}</span>
      <span className="num text-[2.1rem] leading-none font-light">
        {value}
        {unit && <span className="ml-1 text-base text-muted-foreground">{unit}</span>}
      </span>
      {note && <span className="text-xs text-muted-foreground">{note}</span>}
    </div>
  );
}

export function Card({ className, ...props }: React.ComponentProps<"section">) {
  return <section className={cn("rounded-2xl bg-card p-5", className)} {...props} />;
}

export function Empty({ title, children }: { title: string; children?: React.ReactNode }) {
  return (
    <div className="grid place-items-center rounded-2xl border border-dashed py-16 text-center">
      <div className="max-w-sm space-y-2">
        <div className="text-base">{title}</div>
        {children && <div className="text-sm text-muted-foreground">{children}</div>}
      </div>
    </div>
  );
}
