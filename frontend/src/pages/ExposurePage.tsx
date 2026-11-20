import { ChevronRight, Eye, Layers, PartyPopper } from "lucide-react";
import { useDeferredValue, useEffect, useMemo, useState } from "react";
import { useSearchParams } from "react-router";

import { useExposure, useRules } from "@/api/hooks";
import type { ExposureGroup } from "@/api/types";
import { useOpenFinding } from "@/components/AppShell";
import { Card, Empty, PageHeader, Segmented, stagger } from "@/components/okane";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { Slider } from "@/components/ui/slider";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { cn, eur, shortEur } from "@/lib/utils";

type View = "old" | "real";
const PRESETS = [100_000, 250_000, 500_000, 1_000_000];

/** One bar per account (ref1/ref2). Old report: forest green. Real: lime if still open, else faded. */
function AccountStrip({ groups, view }: { groups: ExposureGroup[]; view: View }) {
  // Always scaled to the old report's largest account, so switching views shows bars shrinking.
  const max = Math.max(...groups.map((g) => g.overdue_abs), 1);
  return (
    <div className="relative h-48 border-b">
      <div className="hairline-bars absolute inset-0 opacity-40 [mask-image:linear-gradient(to_top,black,transparent)]" />
      <div className="relative flex h-full items-end justify-around px-2">
        {groups.map((g, i) => {
          const value = view === "old" ? g.overdue_abs : Math.abs(g.net_eur);
          const open = view === "real" && g.above_materiality;
          return (
            <Tooltip key={`${g.erp}${g.entity}${g.account}`}>
              <TooltipTrigger asChild>
                <div className="flex h-full w-5 items-end justify-center">
                  <div
                    className="grow w-2 rounded-full transition-all duration-700 ease-out"
                    style={{
                      height: `${Math.max((value / max) * 100, 2)}%`,
                      background: view === "old" ? "var(--forest)" : open ? "var(--signal)" : "var(--chart-2)",
                      boxShadow: open ? "0 0 0 3px var(--signal-soft)" : undefined,
                      ...stagger(i, 40),
                    }}
                  />
                </div>
              </TooltipTrigger>
              <TooltipContent>
                {g.entity} {g.account} · {g.account_name}
                <div className="num">
                  old report {eur(g.overdue_abs)} · really open {eur(g.net_eur)}
                </div>
              </TooltipContent>
            </Tooltip>
          );
        })}
      </div>
    </div>
  );
}

function GroupRow({ group, view, index, onOpen }: { group: ExposureGroup; view: View; index: number; onOpen: () => void }) {
  const folded = view === "real" && !group.above_materiality;
  const share = group.overdue_abs ? Math.min(Math.abs(group.net_eur) / group.overdue_abs, 1) : 0;
  return (
    <div
      data-tour={`group-${group.erp}-${group.entity}-${group.account}`}
      className={cn(
        "grid overflow-hidden transition-all duration-500 ease-out",
        folded ? "grid-rows-[0fr] opacity-0" : "grid-rows-[1fr] opacity-100",
      )}
    >
      <div className="min-h-0">
        <button
          onClick={onOpen}
          disabled={!group.exception_id}
          className="rise grid w-full grid-cols-[minmax(0,1fr)_100px_150px_190px_24px] items-center gap-4 border-b px-4 py-4 text-left transition hover:bg-secondary disabled:cursor-default"
          style={stagger(index, 50)}
        >
          <div className="min-w-0">
            <div className="flex items-center gap-2">
              <span className="text-[15px]">
                {group.entity} {group.account}
              </span>
              {group.above_materiality && (
                <span className="rounded-full bg-signal px-2 py-0.5 text-[10px] font-medium tracking-wide text-[#0d0d0f] uppercase">
                  Really open
                </span>
              )}
            </div>
            <div className="truncate text-xs text-muted-foreground">
              {group.erp} · {group.account_name}
            </div>
          </div>
          <div className="text-right text-sm">
            <div className="num">{group.lines.toLocaleString("en-GB")}</div>
            <div className="text-[11px] text-muted-foreground">
              {group.paired_lines ? `${group.paired_lines} cancel out` : "lines"}
            </div>
          </div>
          <div className="num text-right text-sm text-muted-foreground line-through decoration-muted-foreground/40">
            {eur(group.overdue_abs)}
          </div>
          <div className="space-y-1.5 text-right">
            <div className={cn("num text-xl font-light", !group.above_materiality && "text-muted-foreground")}>
              {eur(group.net_eur)}
            </div>
            <div className="ml-auto h-1 w-28 overflow-hidden rounded-full bg-muted">
              <div
                className="h-full rounded-full"
                style={{ width: `${share * 100}%`, background: group.above_materiality ? "var(--forest)" : "var(--chart-3)" }}
              />
            </div>
          </div>
          <ChevronRight className={cn("size-4 text-muted-foreground", !group.exception_id && "opacity-0")} />
        </button>
      </div>
    </div>
  );
}

export function ExposurePage() {
  const rules = useRules();
  const ruleMateriality = rules.data?.materiality_eur ?? 500_000;
  const [materiality, setMateriality] = useState<number | null>(null);
  const [params] = useSearchParams();
  const [view, setView] = useState<View>(params.get("view") === "real" ? "real" : "old");
  const value = materiality ?? ruleMateriality;
  const deferred = useDeferredValue(value);
  const exposure = useExposure(deferred);
  const open = useOpenFinding();

  useEffect(() => setMateriality(null), [ruleMateriality]);

  const data = exposure.data;
  const above = useMemo(() => (data?.groups ?? []).filter((g) => g.above_materiality), [data]);
  const realTotal = above.reduce((sum, g) => sum + Math.abs(g.net_eur), 0);
  const foldedLines = (data?.groups ?? []).filter((g) => !g.above_materiality).reduce((s, g) => s + g.lines, 0);
  const calmer = data && data.old_rule_overdue_abs ? Math.round((1 - realTotal / data.old_rule_overdue_abs) * 100) : 0;

  return (
    <div className="space-y-8">
      <PageHeader
        title="Exposure"
        trail={["Payroll", "What's really still owed"]}
        tour="exposure-header"
        subtitle="The old report counts every line older than a year as overdue. Okane first matches each accrual to the payment that settled it, so you only see what's really still open."
        actions={
          view === "old" ? (
            <Button onClick={() => setView("real")} className="h-11 rounded-xl px-5 shadow-lg transition hover:-translate-y-0.5">
              <Eye /> Show what's really open
            </Button>
          ) : (
            <Button variant="outline" onClick={() => setView("old")} className="h-11 rounded-xl px-5">
              <Layers /> Back to the old report
            </Button>
          )
        }
      />

      <Card data-tour="exposure-headline" className="space-y-6 p-7" style={stagger(1, 80)}>
        <div className="flex flex-wrap items-center justify-between gap-6">
          <Segmented
            value={view}
            onChange={setView}
            options={[
              { value: "old", label: "Old report (365-day rule)" },
              { value: "real", label: "What's really open" },
            ]}
          />
          <span className="eyebrow">Payroll · scaled EUR · latest extract</span>
        </div>

        {!data ? (
          <Skeleton className="mx-auto h-24 w-2/3" />
        ) : (
          <div className="py-2 text-center">
            <div
              key={view}
              className={cn(
                "num animate-in slide-in-from-bottom-3 text-[length:clamp(3rem,8vw,6.5rem)] leading-none font-light tracking-tight duration-700",
                view === "real" && "text-forest",
              )}
            >
              {view === "old" ? eur(data.old_rule_overdue_abs) : eur(realTotal)}
            </div>
            <div className="mt-4 text-[15px] text-muted-foreground">
              {view === "old" ? (
                <>
                  Flagged as "overdue" on{" "}
                  <span className="num text-foreground">{data.old_rule_lines.toLocaleString("en-GB")}</span> lines. Loud, but
                  most of it was already paid.
                </>
              ) : (
                <span className="inline-flex flex-wrap items-center justify-center gap-2">
                  <PartyPopper className="size-4 text-mistake" />
                  <span>
                    Only <span className="num text-foreground">{data.groups_above}</span> account
                    {data.groups_above === 1 ? "" : "s"} above {shortEur(data.materiality_eur)} really need attention.{" "}
                    {foldedLines.toLocaleString("en-GB")} lines fold away
                    {calmer > 0 && <> and the headline shrinks by {calmer}%</>}.
                  </span>
                </span>
              )}
            </div>
          </div>
        )}

        {data && <AccountStrip groups={data.groups} view={view} />}
      </Card>

      <div className="grid gap-6 lg:grid-cols-[330px_1fr]">
        <section
          data-tour="exposure-materiality"
          className="rise h-fit space-y-5 rounded-2xl bg-forest p-6 text-white dark:bg-forest-soft"
          style={stagger(2, 80)}
        >
          <div className="eyebrow !text-white/70">How big is "big"?</div>
          <div className="num text-6xl leading-none font-light">{shortEur(value)}</div>
          <p className="text-sm text-white/80">Accounts that net to less than this fold away. Slide to try it out.</p>
          <Slider
            min={50_000}
            max={2_000_000}
            step={25_000}
            value={[value]}
            onValueChange={([v]) => setMateriality(v)}
            tone="signal"
          />
          <div className="flex flex-wrap gap-2">
            {PRESETS.map((p) => (
              <button
                key={p}
                onClick={() => setMateriality(p)}
                className={cn(
                  "num rounded-full px-3 py-1 text-xs transition",
                  p === value ? "bg-signal font-medium text-[#0d0d0f]" : "bg-white/10 hover:bg-white/20",
                )}
              >
                {shortEur(p)}
              </button>
            ))}
          </div>
          <p className="text-xs leading-relaxed text-white/65">
            Just trying things out. The saved limit stays at <span className="num text-white">{eur(ruleMateriality)}</span>;
            change it in Rules so it's logged and everything is re-ranked.
          </p>
        </section>

        <Card data-tour="exposure-accounts" className="p-0" style={stagger(3, 80)}>
          <div className="grid grid-cols-[minmax(0,1fr)_100px_150px_190px_24px] gap-4 border-b px-4 py-3">
            <span className="eyebrow">Account</span>
            <span className="eyebrow text-right">Overdue lines</span>
            <span className="eyebrow text-right">Old report</span>
            <span className="eyebrow text-right">Really open</span>
            <span />
          </div>
          {!data ? (
            <div className="space-y-2 p-4">
              {Array.from({ length: 5 }).map((_, i) => (
                <Skeleton key={i} className="h-12" />
              ))}
            </div>
          ) : data.groups.length === 0 ? (
            <div className="p-6">
              <Empty title="Nothing overdue on payroll 🎉" />
            </div>
          ) : (
            <>
              {data.groups.map((g, i) => (
                <GroupRow
                  key={`${g.erp}${g.entity}${g.account}`}
                  group={g}
                  index={i}
                  view={view}
                  onOpen={() => open(g.exception_id)}
                />
              ))}
              {view === "real" && (
                <div className="flex items-center gap-2 px-4 py-4 text-sm text-muted-foreground">
                  <span className="size-2 rounded-full bg-signal" />
                  {data.groups.length - data.groups_above} smaller accounts are tucked away. All overdue lines together net to{" "}
                  {eur(data.net_eur)}.
                </div>
              )}
            </>
          )}
        </Card>
      </div>
    </div>
  );
}
