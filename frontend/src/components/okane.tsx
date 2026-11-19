import {
  AlertTriangle,
  ArrowRightLeft,
  CalendarX2,
  Clock3,
  Coins,
  EyeOff,
  FileWarning,
  Repeat2,
  Scale,
  Sparkles,
  SpellCheck,
  TrendingUp,
  Undo2,
} from "lucide-react";
import type * as React from "react";

import type { ExceptionRecord, ExceptionType, Status } from "@/api/types";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { STATUS_LABEL, TYPE_HINT, TYPE_LABEL, WEIGHT_LABEL, toneOf } from "@/lib/labels";
import { cn, day } from "@/lib/utils";

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

/** Delay helper for the staggered fade-in (`rise` utility). */
export const stagger = (index: number, step = 45, max = 600): React.CSSProperties =>
  ({ "--d": `${Math.min(index * step, max)}ms` }) as React.CSSProperties;

/** Rounded, tinted icon tile in the finding's colour (ref1 card icons). */
export function TypeIcon({ type, size = "md" }: { type: ExceptionType; size?: "sm" | "md" | "lg" }) {
  const Icon = TYPE_ICON[type];
  const tone = toneOf(type);
  const box = { sm: "size-7 rounded-lg", md: "size-9 rounded-xl", lg: "size-12 rounded-2xl" }[size];
  const icon = { sm: "size-3.5", md: "size-[18px]", lg: "size-6" }[size];
  return (
    <span className={cn("grid shrink-0 place-items-center", box, tone.soft, tone.ink)}>
      <Icon className={icon} />
    </span>
  );
}

export function TypeLabel({ type, className }: { type: ExceptionType; className?: string }) {
  return (
    <Tooltip>
      <TooltipTrigger asChild>
        <span className={cn("eyebrow inline-flex items-center gap-1.5 !text-[10.5px]", toneOf(type).ink, className)}>
          <span className={cn("size-1.5 rounded-full", toneOf(type).solid)} />
          {TYPE_LABEL[type]}
        </span>
      </TooltipTrigger>
      <TooltipContent>{TYPE_HINT[type]}</TooltipContent>
    </Tooltip>
  );
}

/** How much earlier Okane spots it than today's process. The wording comes from the engine
 *  (A8, #16): counted from the weekly run on or after the first signal. */
export function LeadBadge({ record, size = "sm" }: { record: ExceptionRecord; size?: "sm" | "lg" }) {
  const basis = String(record.facts.today_detection_basis ?? "");
  const lead = record.lead_days;
  const badge = typeof record.facts.lead_badge === "string" ? record.facts.lead_badge : null;
  const run = typeof record.facts.okane_run_date === "string" ? record.facts.okane_run_date : null;
  const daily = record.facts.lead_days_daily;
  const weekly = record.facts.lead_view === "weekly";
  const big = size === "lg";
  const shape = cn(
    "inline-flex items-center gap-1.5 rounded-full font-medium whitespace-nowrap",
    big ? "px-3 py-1.5 text-sm" : "px-2.5 py-1 text-[11px]",
  );
  if (lead === null || lead === undefined) {
    return (
      <Tooltip>
        <TooltipTrigger asChild>
          <span className={cn(shape, "bg-hot-soft text-hot")}>
            <EyeOff className={big ? "size-4" : "size-3"} />
            {badge ?? "Today's process would miss this"}
          </span>
        </TooltipTrigger>
        <TooltipContent>
          Neither the ageing rule nor the month-end close review looks for this. Only Okane does.
        </TooltipContent>
      </Tooltip>
    );
  }
  const what = basis.includes("ageing") ? "the ageing rule" : "the month-end close review";
  const earlier = lead >= 0;
  return (
    <Tooltip>
      <TooltipTrigger asChild>
        <span className={cn(shape, earlier ? "bg-dock text-white" : "bg-muted text-muted-foreground")}>
          <Sparkles className={cn(big ? "size-4" : "size-3", earlier && "text-signal")} />
          {badge ?? `${earlier ? "Caught" : "Seen"} ${Math.abs(lead)} days ${earlier ? "earlier" : "later"}`}
        </span>
      </TooltipTrigger>
      <TooltipContent>
        {weekly && run ? (
          <>
            The first sign is on {day(record.first_signal)}; Okane's weekly run flags it on {day(run)}.{" "}
          </>
        ) : (
          <>Okane can flag it on {day(record.first_signal)}. </>
        )}
        Today it would surface through {what} on {day(record.today_detection)}.
        {weekly && typeof daily === "number" ? ` (${daily} days earlier if Okane ran every day.)` : ""}
      </TooltipContent>
    </Tooltip>
  );
}

export function StatusPill({ status }: { status: Status }) {
  const tone = {
    new: "border-border bg-secondary text-foreground",
    explained: "border-transparent bg-pulse-soft text-pulse",
    dismissed: "border-transparent bg-muted text-muted-foreground",
    escalated: "border-transparent bg-mistake-soft text-mistake",
  }[status];
  return (
    <span className={cn("inline-flex items-center gap-1.5 rounded-full border px-2.5 py-1 text-[11px] font-medium", tone)}>
      {status !== "new" && <span className="size-1.5 rounded-full bg-current" />}
      {STATUS_LABEL[status]}
    </span>
  );
}

export function priorityTone(score: number) {
  if (score >= 70) return { bar: "bg-hot", text: "text-hot", label: "High" };
  if (score >= 40) return { bar: "bg-mistake", text: "text-mistake", label: "Medium" };
  return { bar: "bg-pulse", text: "text-pulse", label: "Low" };
}

export function ScoreBar({ record }: { record: ExceptionRecord }) {
  const tone = priorityTone(record.score);
  return (
    <Tooltip>
      <TooltipTrigger asChild>
        <div className="w-24 space-y-1.5">
          <div className="flex items-baseline justify-between">
            <span className="num text-sm font-medium">{record.score.toFixed(0)}</span>
            <span className={cn("text-[10px] font-medium tracking-wide uppercase", tone.text)}>{tone.label}</span>
          </div>
          <div className="h-1.5 overflow-hidden rounded-full bg-muted">
            <div className={cn("grow-x h-full rounded-full", tone.bar)} style={{ width: `${Math.min(record.score, 100)}%` }} />
          </div>
        </div>
      </TooltipTrigger>
      <TooltipContent>
        <div className="mb-1 text-white/60">Priority points, from the weights you set in Rules</div>
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
    <div className={cn("inline-flex items-center gap-1 rounded-full border bg-secondary p-1", className)} role="tablist">
      {options.map((option) => (
        <button
          key={option.value}
          role="tab"
          aria-selected={option.value === value}
          onClick={() => onChange(option.value)}
          className={cn(
            "rounded-full px-3.5 py-1.5 text-sm transition-all",
            option.value === value
              ? "bg-foreground text-background shadow-sm"
              : "text-muted-foreground hover:text-foreground",
          )}
        >
          {option.label}
        </button>
      ))}
    </div>
  );
}

/** Filter pill (ref3). The active pill turns lime; a coloured dot marks the kind of finding. */
export function Chip({
  active,
  children,
  onClick,
  count,
  dot,
}: {
  active?: boolean;
  children: React.ReactNode;
  onClick?: () => void;
  count?: number;
  dot?: string;
}) {
  return (
    <button
      onClick={onClick}
      className={cn(
        "inline-flex h-10 items-center gap-2 rounded-full border px-4 text-sm transition-all hover:-translate-y-0.5",
        active ? "border-transparent bg-signal font-medium text-[#0d0d0f] shadow-sm" : "bg-secondary hover:bg-accent",
      )}
    >
      {dot && <span className="size-2 rounded-full" style={{ background: dot }} />}
      {children}
      {count !== undefined && (
        <span
          className={cn(
            "num grid h-5 min-w-5 place-items-center rounded-full px-1.5 text-[11px]",
            active ? "bg-[#0d0d0f] text-signal" : "bg-muted text-muted-foreground",
          )}
        >
          {count}
        </span>
      )}
    </button>
  );
}

export function PageHeader({
  title,
  subtitle,
  trail,
  actions,
}: {
  title: string;
  subtitle?: React.ReactNode;
  trail?: string[];
  actions?: React.ReactNode;
}) {
  return (
    <div className="rise flex flex-wrap items-end justify-between gap-4">
      <div className="space-y-2">
        <div className="flex items-baseline gap-5">
          <h1 className="text-[2.1rem] leading-none font-light tracking-tight">{title}</h1>
          {trail && (
            <div className="hidden items-center gap-2 text-xs text-muted-foreground sm:flex">
              {trail.map((part, i) => (
                <span key={part} className="flex items-center gap-2">
                  {i > 0 && <span className="text-border">/</span>}
                  {part}
                </span>
              ))}
            </div>
          )}
        </div>
        {subtitle && <p className="max-w-2xl text-[15px] text-muted-foreground">{subtitle}</p>}
      </div>
      {actions && <div className="flex items-center gap-2">{actions}</div>}
    </div>
  );
}

/** ref3's coloured "barcode": a strip of thin bars whose density shows a quantity. */
export function Barcode({ count, color, total = 48 }: { count: number; color: string; total?: number }) {
  const lit = Math.max(0, Math.min(total, Math.round(count)));
  return (
    <div className="flex h-7 items-end gap-[3px]" aria-hidden>
      {Array.from({ length: total }).map((_, i) => (
        <span
          key={i}
          className="grow w-[2px] rounded-full"
          style={{
            height: `${45 + ((i * 37) % 55)}%`,
            background: i < lit ? color : "var(--muted)",
            ...stagger(i, 12, 500),
          }}
        />
      ))}
    </div>
  );
}

export function StatCard({
  label,
  value,
  unit,
  note,
  icon: Icon,
  color,
  soft,
  bars,
  index = 0,
  dark,
}: {
  label: string;
  value: React.ReactNode;
  unit?: string;
  note?: React.ReactNode;
  icon: React.ComponentType<{ className?: string }>;
  color: string;
  soft: string;
  bars: number;
  index?: number;
  dark?: boolean;
}) {
  return (
    <div
      className={cn(
        "rise group flex flex-col justify-between gap-4 rounded-2xl p-5 transition-transform hover:-translate-y-0.5",
        dark ? "bg-dock text-white" : "bg-card",
      )}
      style={stagger(index, 70)}
    >
      <div className="flex items-start justify-between gap-3">
        <span className={cn("eyebrow", dark && "!text-white/60")}>{label}</span>
        <span className="grid size-9 place-items-center rounded-xl transition-transform group-hover:rotate-6" style={{ background: soft, color }}>
          <Icon className="size-[18px]" />
        </span>
      </div>
      <div className="space-y-1">
        <div className="num text-[2.4rem] leading-none font-light">
          {value}
          {unit && <span className={cn("ml-1.5 text-base", dark ? "text-white/50" : "text-muted-foreground")}>{unit}</span>}
        </div>
        {note && <div className={cn("text-xs", dark ? "text-white/55" : "text-muted-foreground")}>{note}</div>}
      </div>
      <Barcode count={bars} color={color} />
    </div>
  );
}

/** ref3 "budget usage" bar: coloured segments with a legend. */
export function SplitBar({ parts }: { parts: { label: string; value: number; color: string }[] }) {
  const total = parts.reduce((s, p) => s + p.value, 0) || 1;
  return (
    <div className="space-y-3">
      <div className="flex h-3 gap-1">
        {parts
          .filter((p) => p.value > 0)
          .map((p, i) => (
            <div
              key={p.label}
              className="grow-x rounded-full"
              style={{ width: `${(p.value / total) * 100}%`, background: p.color, ...stagger(i, 120) }}
            />
          ))}
      </div>
      <div className="flex flex-wrap gap-x-5 gap-y-1.5 text-xs text-muted-foreground">
        {parts.map((p) => (
          <span key={p.label} className="inline-flex items-center gap-1.5">
            <span className="size-2 rounded-full" style={{ background: p.color }} />
            {p.label}
            <span className="num text-foreground">{Math.round((p.value / total) * 100)}%</span>
          </span>
        ))}
      </div>
    </div>
  );
}

/** Half-circle progress gauge (ref2 insight card), used for "reviewed so far". */
export function Gauge({ value, total, label }: { value: number; total: number; label: string }) {
  const share = total ? value / total : 0;
  const r = 52;
  const length = Math.PI * r;
  return (
    <div className="relative mx-auto w-40">
      <svg viewBox="0 0 128 72" className="w-full overflow-visible">
        <path d="M12 64a52 52 0 0 1 104 0" fill="none" stroke="var(--muted)" strokeWidth="10" strokeLinecap="round" />
        <path
          d="M12 64a52 52 0 0 1 104 0"
          fill="none"
          stroke="var(--signal)"
          strokeWidth="10"
          strokeLinecap="round"
          strokeDasharray={length}
          strokeDashoffset={length * (1 - share)}
          style={{ transition: "stroke-dashoffset 1.2s cubic-bezier(.2,.7,.2,1)" }}
        />
      </svg>
      <div className="absolute inset-x-0 bottom-0 text-center">
        <div className="num text-2xl leading-none font-light">
          {value}
          <span className="text-sm text-muted-foreground">/{total}</span>
        </div>
        <div className="mt-1 text-[11px] text-muted-foreground">{label}</div>
      </div>
    </div>
  );
}

export function Card({ className, ...props }: React.ComponentProps<"section">) {
  return <section className={cn("rise rounded-2xl bg-card p-5", className)} {...props} />;
}

export function Empty({ title, children }: { title: string; children?: React.ReactNode }) {
  return (
    <div className="rise grid place-items-center rounded-2xl border border-dashed py-16 text-center">
      <div className="max-w-sm space-y-3">
        <div className="float mx-auto grid size-12 place-items-center rounded-2xl bg-signal-soft text-signal-ink">
          <Sparkles className="size-6" />
        </div>
        <div className="text-base">{title}</div>
        {children && <div className="text-sm text-muted-foreground">{children}</div>}
      </div>
    </div>
  );
}
