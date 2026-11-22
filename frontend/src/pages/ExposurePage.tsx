import { ChevronRight, Eye, Layers, PartyPopper } from "lucide-react";
import { useDeferredValue, useEffect, useMemo, useState } from "react";
import { useSearchParams } from "react-router";

import { useExposure, useFixedAssets, useRules } from "@/api/hooks";
import type { ExposureGroup, FixedAssetGroup } from "@/api/types";
import { useOpenFinding } from "@/components/AppShell";
import { Card, Empty, PageHeader, Segmented, stagger } from "@/components/okane";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { Slider } from "@/components/ui/slider";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { netMeaning } from "@/lib/labels";
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
                <div className="flex h-full w-5 min-w-0 shrink items-end justify-center">
                  <div
                    className="grow w-full max-w-2 rounded-full transition-all duration-700 ease-out"
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
                  old report {eur(g.overdue_abs)} · really open {eur(g.net_eur)}, {netMeaning(g.normal_side, g.net_eur).text}
                </div>
              </TooltipContent>
            </Tooltip>
          );
        })}
      </div>
    </div>
  );
}

/** What the net means for this account (A43), in place of a bare signed amount. */
function NetLabel({ group }: { group: ExposureGroup }) {
  const { text, wrong } = netMeaning(group.normal_side, group.net_eur);
  return <div className={cn("text-[11px] leading-tight", wrong ? "text-hot" : "text-muted-foreground")}>{text}</div>;
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
          className="rise grid w-full grid-cols-3 items-center gap-x-4 gap-y-3 border-b px-4 py-4 text-left transition hover:bg-secondary disabled:cursor-default md:grid-cols-[minmax(0,1fr)_100px_150px_190px_24px] md:gap-4"
          style={stagger(index, 50)}
        >
          <div className="col-span-3 min-w-0 md:col-span-1">
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
          <div className="text-left text-sm md:text-right">
            <div className="num">{group.lines.toLocaleString("en-GB")}</div>
            <div className="text-[11px] text-muted-foreground">
              {group.paired_lines ? `${group.paired_lines} cancel out` : "lines"}
            </div>
          </div>
          <div className="text-right text-sm">
            <div className="num text-muted-foreground line-through decoration-muted-foreground/40">{eur(group.overdue_abs)}</div>
            <div className="text-[11px] text-muted-foreground md:hidden">old report</div>
          </div>
          <div className="space-y-1.5 text-right">
            <div className={cn("num text-lg font-light md:text-xl", !group.above_materiality && "text-muted-foreground")}>
              {eur(group.net_eur)}
            </div>
            <NetLabel group={group} />
            <div className="ml-auto h-1 w-full max-w-28 overflow-hidden rounded-full bg-muted">
              <div
                className="h-full rounded-full"
                style={{ width: `${share * 100}%`, background: group.above_materiality ? "var(--forest)" : "var(--chart-3)" }}
              />
            </div>
          </div>
          <ChevronRight className={cn("hidden size-4 text-muted-foreground md:block", !group.exception_id && "opacity-0")} />
        </button>
      </div>
    </div>
  );
}

/** An amount in its own currency, without decimals: "62,456,836 JPY". */
const local = (value: number, currency: string) =>
  `${value.toLocaleString("en-GB", { maximumFractionDigits: 0 })} ${currency}`;

/** "estimated rate" next to EUR figures whose rate is not yet confirmed (A11, A47). */
function Estimated({ show }: { show: boolean }) {
  if (!show) return null;
  return (
    <span className="ml-1.5 rounded-full bg-mistake-soft px-1.5 py-0.5 text-[10px] font-medium text-mistake">
      estimated rate
    </span>
  );
}

function FixedAssetRow({ group, index }: { group: FixedAssetGroup; index: number }) {
  // A47: older unpaired lines that net to (almost) nothing offset each other without a match.
  const offset = group.older_lines > 0 && Math.abs(group.older_net_eur) < 1;
  return (
    <div
      className="rise grid grid-cols-2 gap-x-4 gap-y-3 border-b px-4 py-4 text-sm md:grid-cols-[minmax(0,1fr)_110px_170px_170px_190px] md:gap-4"
      style={stagger(index, 50)}
    >
      <div className="col-span-2 min-w-0 md:col-span-1">
        <div className="text-[15px]">
          {group.entity} {group.account}
        </div>
        <div className="truncate text-xs text-muted-foreground">
          {group.erp} · {group.account_name ?? "Fixed assets"} · {group.currency_lc}
        </div>
      </div>
      <div className="md:text-right">
        <div className="num">{group.lines.toLocaleString("en-GB")}</div>
        <div className="text-[11px] text-muted-foreground">
          {group.paired_lines.toLocaleString("en-GB")} cancel out
          {group.zero_amount_lines ? ` · ${group.zero_amount_lines} FX valuations` : ""}
        </div>
      </div>
      <div className="text-right">
        <div className="num">{group.recent_lines ? local(group.recent_net_lc, group.currency_lc) : "–"}</div>
        <div className="text-[11px] text-muted-foreground">
          {group.recent_lines} line{group.recent_lines === 1 ? "" : "s"}, timing: this month's accruals
        </div>
      </div>
      <div className="md:text-right">
        <div className="num">{group.older_lines ? local(group.older_net_lc, group.currency_lc) : "–"}</div>
        <div className="text-[11px] text-muted-foreground">
          {group.older_lines} line{group.older_lines === 1 ? "" : "s"},{" "}
          {offset ? "offset each other but never matched" : "older, never matched"}
        </div>
      </div>
      <div className="text-right">
        <div className="num text-lg font-light">{local(group.net_lc, group.currency_lc)}</div>
        <div className="text-[11px] text-muted-foreground">
          {eur(group.net_eur)} EUR
          <Estimated show={group.estimated_rate} />
        </div>
        {/* FX valuations and what exact pairs leave in local currency, so the parts add up. */}
        {Math.round(group.fx_net_lc ?? 0) !== 0 && (
          <div className="text-[11px] text-muted-foreground">
            incl. {local(group.fx_net_lc ?? 0, group.currency_lc)} exchange differences
          </div>
        )}
      </div>
    </div>
  );
}

/** What is really open in Fixed assets once exact pairs fold away (A47). */
function FixedAssetsSection() {
  const fixed = useFixedAssets();
  const data = fixed.data;
  if (!data || data.lines === 0) return null;
  const share = data.lines ? Math.round((data.paired_lines / data.lines) * 100) : 0;
  return (
    <Card data-tour="exposure-fixed-assets" className="space-y-3 p-0" style={stagger(4, 80)}>
      <div className="space-y-1 px-4 pt-4">
        <div className="eyebrow">Fixed assets · what's really still open</div>
        <p className="text-sm text-muted-foreground">
          <span className="num text-foreground">{data.paired_lines.toLocaleString("en-GB")}</span> of{" "}
          <span className="num text-foreground">{data.lines.toLocaleString("en-GB")}</span> lines ({share}%) cancel out
          in exact pairs. What is left: lines posted in the {data.recent_days} days before the extract (this
          month's accruals) and older lines that never matched.
        </p>
      </div>
      <div className="hidden grid-cols-[minmax(0,1fr)_110px_170px_170px_190px] gap-4 border-y px-4 py-3 md:grid">
        <span className="eyebrow">Entity and account</span>
        <span className="eyebrow text-right">Lines</span>
        <span className="eyebrow text-right">Recent, unpaired</span>
        <span className="eyebrow text-right">Older, unpaired</span>
        <span className="eyebrow text-right">Net</span>
      </div>
      <div>
        {data.groups.map((g, i) => (
          <FixedAssetRow key={`${g.erp}${g.entity}${g.account}${g.currency_lc}`} group={g} index={i} />
        ))}
      </div>
    </Card>
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
        trail={["Payroll", "What's really still open"]}
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

      <Card data-tour="exposure-headline" className="space-y-6 p-5 sm:p-7" style={stagger(1, 80)}>
        <div className="flex flex-wrap items-center justify-between gap-6">
          <Segmented
            value={view}
            onChange={setView}
            options={[
              { value: "old", label: <>Old report<span className="hidden sm:inline"> (365-day rule)</span></> },
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
                "num animate-in slide-in-from-bottom-3 text-[length:clamp(2rem,8vw,6.5rem)] leading-none font-light tracking-tight duration-700",
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

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-[330px_1fr]">
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
          <div className="hidden grid-cols-[minmax(0,1fr)_100px_150px_190px_24px] gap-4 border-b px-4 py-3 md:grid">
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

      <FixedAssetsSection />
    </div>
  );
}
