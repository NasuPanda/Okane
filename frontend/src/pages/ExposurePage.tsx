import { ChevronRight, Eye, Layers } from "lucide-react";
import { useDeferredValue, useEffect, useMemo, useState } from "react";
import { useSearchParams } from "react-router";

import { useExposure, useRules } from "@/api/hooks";
import type { ExposureGroup } from "@/api/types";
import { useOpenFinding } from "@/components/AppShell";
import { Card, Empty, PageHeader, Segmented } from "@/components/okane";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { Slider } from "@/components/ui/slider";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { cn, eur, shortEur } from "@/lib/utils";

type View = "old" | "real";
const PRESETS = [100_000, 250_000, 500_000, 1_000_000];

/** One thin bar per account: the old report's overdue amount (grey) or the real net (black). */
function AccountStrip({ groups, view }: { groups: ExposureGroup[]; view: View }) {
  // The scale is always the old report's largest account, so switching views shows bars shrinking.
  const max = Math.max(...groups.map((g) => g.overdue_abs), 1);
  return (
    <div className="relative h-44 border-b">
      <div className="hairline-bars absolute inset-0 opacity-40 [mask-image:linear-gradient(to_top,black,transparent)]" />
      <div className="relative flex h-full items-end justify-around px-2">
      {groups.map((g) => {
        const value = view === "old" ? g.overdue_abs : Math.abs(g.net_eur);
        const hot = view === "real" && g.above_materiality;
        return (
          <Tooltip key={`${g.erp}${g.entity}${g.account}`}>
            <TooltipTrigger asChild>
              <div className="flex h-full w-4 items-end justify-center">
                <div
                  className={cn(
                    "w-[5px] rounded-t-[2px] transition-all duration-700 ease-out",
                    hot ? "bg-foreground" : view === "old" ? "bg-foreground/70" : "bg-chart-2",
                  )}
                  style={{ height: `${Math.max((value / max) * 100, 1.5)}%` }}
                />
              </div>
            </TooltipTrigger>
            <TooltipContent>
              {g.entity} {g.account} · {g.account_name}
              <div className="num">
                old report {eur(g.overdue_abs)} · net {eur(g.net_eur)}
              </div>
            </TooltipContent>
          </Tooltip>
        );
      })}
      </div>
    </div>
  );
}

function GroupRow({ group, view, onOpen }: { group: ExposureGroup; view: View; onOpen: () => void }) {
  const folded = view === "real" && !group.above_materiality;
  return (
    <div
      className={cn(
        "grid overflow-hidden transition-all duration-500 ease-out",
        folded ? "grid-rows-[0fr] opacity-0" : "grid-rows-[1fr] opacity-100",
      )}
    >
      <div className="min-h-0">
        <button
          onClick={onOpen}
          disabled={!group.exception_id}
          className="grid w-full grid-cols-[minmax(0,1fr)_110px_150px_170px_24px] items-center gap-4 border-b px-4 py-4 text-left transition hover:bg-secondary/70 disabled:cursor-default"
        >
          <div className="min-w-0">
            <div className="flex items-center gap-2">
              <span className="text-[15px]">
                {group.entity} {group.account}
              </span>
              {group.above_materiality && (
                <span className="rounded-full bg-foreground px-2 py-0.5 text-[10px] tracking-wide text-white uppercase">
                  Real exposure
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
              {group.paired_lines ? `${group.paired_lines} paired` : "lines"}
            </div>
          </div>
          <div className="num text-right text-sm text-muted-foreground line-through decoration-muted-foreground/40">
            {eur(group.overdue_abs)}
          </div>
          <div className={cn("num text-right text-xl font-light", !group.above_materiality && "text-muted-foreground")}>
            {eur(group.net_eur)}
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

  return (
    <div className="space-y-8">
      <PageHeader
        title="Exposure"
        trail={["Payroll", "Open items netted per account"]}
        actions={
          view === "old" ? (
            <Button onClick={() => setView("real")} className="h-10 rounded-xl px-5">
              <Eye /> Show real exposure
            </Button>
          ) : (
            <Button variant="outline" onClick={() => setView("old")} className="h-10 rounded-xl px-5">
              <Layers /> Back to the old report
            </Button>
          )
        }
      />

      <Card className="space-y-6 p-7">
        <div className="flex flex-wrap items-start justify-between gap-6">
          <div className="space-y-3">
            <div className="eyebrow">Payroll · scaled EUR · as of the latest extract</div>
            <Segmented
              value={view}
              onChange={setView}
              options={[
                { value: "old", label: "Old report: 365-day rule" },
                { value: "real", label: "Real exposure" },
              ]}
            />
          </div>
          <div className="text-right text-xs text-muted-foreground">
            {view === "old" ? "Every line older than its allowed age counts" : "Accruals netted against what settled them"}
          </div>
        </div>

        {!data ? (
          <Skeleton className="mx-auto h-24 w-2/3" />
        ) : (
          <div className="py-2 text-center">
            <div key={view} className="num animate-in slide-in-from-bottom-2 text-[length:clamp(3rem,8vw,6.25rem)] leading-none font-light tracking-tight duration-500">
              {view === "old" ? eur(data.old_rule_overdue_abs) : eur(realTotal)}
            </div>
            <div className="mt-3 text-sm text-muted-foreground">
              {view === "old" ? (
                <>
                  "Overdue" on <span className="num text-foreground">{data.old_rule_lines.toLocaleString("en-GB")}</span>{" "}
                  lines. Too loud: most are accruals already matched by payments.
                </>
              ) : (
                <>
                  <span className="num text-foreground">{data.groups_above}</span> account
                  {data.groups_above === 1 ? "" : "s"} at or above {shortEur(data.materiality_eur)} materiality ·{" "}
                  {foldedLines.toLocaleString("en-GB")} lines fold away
                </>
              )}
            </div>
          </div>
        )}

        {data && <AccountStrip groups={data.groups} view={view} />}
      </Card>

      <div className="grid gap-6 lg:grid-cols-[320px_1fr]">
        <Card className="h-fit space-y-5">
          <div className="eyebrow">Materiality</div>
          <div className="num text-5xl font-light">{shortEur(value)}</div>
          <Slider
            min={50_000}
            max={2_000_000}
            step={25_000}
            value={[value]}
            onValueChange={([v]) => setMateriality(v)}
          />
          <div className="flex flex-wrap gap-2">
            {PRESETS.map((p) => (
              <button
                key={p}
                onClick={() => setMateriality(p)}
                className={cn(
                  "num rounded-full border px-3 py-1 text-xs",
                  p === value ? "border-foreground bg-foreground text-white" : "bg-secondary hover:bg-accent",
                )}
              >
                {shortEur(p)}
              </button>
            ))}
          </div>
          <p className="text-xs leading-relaxed text-muted-foreground">
            A what-if view. The saved rule is <span className="num text-foreground">{eur(ruleMateriality)}</span>; change
            it in Rules so the change is logged and every finding is re-ranked.
          </p>
        </Card>

        <Card className="p-0">
          <div className="grid grid-cols-[minmax(0,1fr)_110px_150px_170px_24px] gap-4 border-b px-4 py-3">
            <span className="eyebrow">Account</span>
            <span className="eyebrow text-right">Overdue lines</span>
            <span className="eyebrow text-right">Old report</span>
            <span className="eyebrow text-right">Net · real</span>
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
              <Empty title="No overdue payroll lines" />
            </div>
          ) : (
            <>
              {data.groups.map((g) => (
                <GroupRow key={`${g.erp}${g.entity}${g.account}`} group={g} view={view} onOpen={() => open(g.exception_id)} />
              ))}
              {view === "real" && (
                <div className="px-4 py-4 text-sm text-muted-foreground">
                  {data.groups.length - data.groups_above} accounts below materiality are folded away. Net {eur(data.net_eur)}{" "}
                  across all overdue lines.
                </div>
              )}
            </>
          )}
        </Card>
      </div>
    </div>
  );
}
