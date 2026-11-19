// The report period shared by the Inbox and Sentinel pages: day, week, month, year or overall,
// counted back from the analysis date (the day the extract was taken, A38). Changing it on one
// page changes it on the others; the chosen grain is remembered in this browser.
import { ChevronLeft, ChevronRight } from "lucide-react";
import { createContext, useContext, useEffect, useMemo, useState } from "react";

import { useLatestRun } from "@/api/hooks";
import type { ExceptionRecord } from "@/api/types";
import { Segmented } from "@/components/okane";
import { cn } from "@/lib/utils";

export type Grain = "day" | "week" | "month" | "year" | "all";

const GRAINS: { value: Grain; label: string }[] = [
  { value: "day", label: "Daily" },
  { value: "week", label: "Weekly" },
  { value: "month", label: "Monthly" },
  { value: "year", label: "Yearly" },
  { value: "all", label: "Overall" },
];
const STORAGE_KEY = "okane.period.grain";

type PeriodState = { grain: Grain; offset: number; setGrain: (g: Grain) => void; setOffset: (n: number) => void };
const PeriodContext = createContext<PeriodState | null>(null);

function storedGrain(): Grain {
  try {
    const value = window.localStorage.getItem(STORAGE_KEY);
    if (GRAINS.some((g) => g.value === value)) return value as Grain;
  } catch {
    /* storage unavailable: use the default */
  }
  return "all";
}

export function PeriodProvider({ children }: { children: React.ReactNode }) {
  const [grain, setGrainState] = useState<Grain>(storedGrain);
  const [offset, setOffset] = useState(0);
  const setGrain = (g: Grain) => {
    setGrainState(g);
    setOffset(0);
    try {
      window.localStorage.setItem(STORAGE_KEY, g);
    } catch {
      /* not remembered: still applies for this visit */
    }
  };
  return <PeriodContext.Provider value={{ grain, offset, setGrain, setOffset }}>{children}</PeriodContext.Provider>;
}

// ----- dates (local calendar days, no time zones) ------------------------------------------
const parse = (iso: string) => {
  const [y, m, d] = iso.slice(0, 10).split("-").map(Number);
  return new Date(y, m - 1, d);
};
const iso = (d: Date) =>
  `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
const fmt = (d: Date, opts: Intl.DateTimeFormatOptions) => d.toLocaleDateString("en-GB", opts);

export type PeriodRange = { start: string; end: string; label: string } | null;

/** The calendar period ``offset`` steps before the one holding ``anchor``; null = overall. */
export function periodRange(grain: Grain, anchor: string, offset: number): PeriodRange {
  if (grain === "all") return null;
  const a = parse(anchor);
  let start: Date;
  let end: Date;
  if (grain === "day") {
    start = new Date(a.getFullYear(), a.getMonth(), a.getDate() - offset);
    end = start;
    return { start: iso(start), end: iso(end), label: fmt(start, { weekday: "short", day: "numeric", month: "short", year: "numeric" }) };
  }
  if (grain === "week") {
    const monday = new Date(a.getFullYear(), a.getMonth(), a.getDate() - ((a.getDay() + 6) % 7) - 7 * offset);
    start = monday;
    end = new Date(monday.getFullYear(), monday.getMonth(), monday.getDate() + 6);
    return {
      start: iso(start),
      end: iso(end),
      label: `${fmt(start, { day: "numeric", month: "short" })} – ${fmt(end, { day: "numeric", month: "short", year: "numeric" })}`,
    };
  }
  if (grain === "month") {
    start = new Date(a.getFullYear(), a.getMonth() - offset, 1);
    end = new Date(start.getFullYear(), start.getMonth() + 1, 0);
    return { start: iso(start), end: iso(end), label: fmt(start, { month: "long", year: "numeric" }) };
  }
  start = new Date(a.getFullYear() - offset, 0, 1);
  end = new Date(start.getFullYear(), 11, 31);
  return { start: iso(start), end: iso(end), label: String(start.getFullYear()) };
}

/** The day a finding belongs to: its posting date when it has one, else when it was first seen. */
export const findingDate = (r: ExceptionRecord) => String(r.facts.posting_date ?? r.first_signal).slice(0, 10);

export function inPeriod(r: ExceptionRecord, range: PeriodRange): boolean {
  if (!range) return true;
  const d = findingDate(r);
  return d >= range.start && d <= range.end;
}

/** The shared period for this page: its range and a filter for findings. */
export function usePeriod() {
  const state = useContext(PeriodContext);
  if (!state) throw new Error("usePeriod needs a PeriodProvider");
  const run = useLatestRun();
  const anchor = run.data?.as_of ?? iso(new Date());
  const range = useMemo(() => periodRange(state.grain, anchor, state.offset), [state.grain, anchor, state.offset]);
  return { ...state, anchor, range, filter: (records: ExceptionRecord[]) => records.filter((r) => inPeriod(r, range)) };
}

/** Daily / weekly / monthly / yearly / overall, with arrows to step back through earlier periods. */
export function PeriodPicker({ className }: { className?: string }) {
  const { grain, offset, setGrain, setOffset, range, anchor } = usePeriod();
  // A new extract moves the analysis date: start again from its period.
  useEffect(() => setOffset(0), [anchor]); // eslint-disable-line react-hooks/exhaustive-deps
  return (
    <div className={cn("flex flex-wrap items-center gap-2", className)}>
      <Segmented value={grain} onChange={setGrain} options={GRAINS} />
      {range && (
        <div className="inline-flex items-center gap-1 rounded-full border bg-secondary p-1 text-sm">
          <button
            aria-label="Earlier period"
            onClick={() => setOffset(offset + 1)}
            className="grid size-7 place-items-center rounded-full text-muted-foreground hover:bg-background hover:text-foreground"
          >
            <ChevronLeft className="size-4" />
          </button>
          <span className="num min-w-36 px-1 text-center">{range.label}</span>
          <button
            aria-label="Later period"
            disabled={offset === 0}
            onClick={() => setOffset(offset - 1)}
            className="grid size-7 place-items-center rounded-full text-muted-foreground hover:bg-background hover:text-foreground disabled:opacity-30 disabled:hover:bg-transparent"
          >
            <ChevronRight className="size-4" />
          </button>
        </div>
      )}
    </div>
  );
}
