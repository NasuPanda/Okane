import {
  createColumnHelper,
  flexRender,
  getCoreRowModel,
  getSortedRowModel,
  useReactTable,
  type SortingState,
} from "@tanstack/react-table";
import { AlertTriangle, ArrowDownUp, BellRing, EyeOff, FileSpreadsheet, Hourglass, Sparkles } from "lucide-react";
import { useMemo, useState } from "react";

import { useExceptions, useKpis, useLatestRun, useRules } from "@/api/hooks";
import type { ExceptionRecord, InboxView, Run, Status } from "@/api/types";
import { useOpenFinding } from "@/components/AppShell";
import {
  Card,
  Chip,
  Empty,
  Gauge,
  LeadBadge,
  PageHeader,
  ScoreBar,
  Segmented,
  SplitBar,
  StatCard,
  StatusPill,
  TypeIcon,
  TypeLabel,
  priorityTone,
  stagger,
} from "@/components/okane";
import { Skeleton } from "@/components/ui/skeleton";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { GROUP_LABEL, GROUP_TONE, ROUTE_LABEL, TYPE_GROUP, greeting, weekdayName, type TypeGroup } from "@/lib/labels";
import { PeriodPicker, inPeriod, usePeriod } from "@/lib/period";
import { cn, day, dueDay, eur, shortEur, stamp } from "@/lib/utils";

const column = createColumnHelper<ExceptionRecord>();

/** Where this check's numbers come from: one line per workbook (A38). */
function DataSources({ run }: { run: Run | null | undefined }) {
  const sources = run?.sources ?? [];
  if (!run || !sources.length) return null;
  return (
    <Card data-tour="inbox-datasources" className="space-y-2 border border-signal py-3.5 text-sm">
      {sources.map((s) => (
        <div key={s.file_hash} className="flex flex-wrap items-center gap-x-2 gap-y-1 text-muted-foreground">
          <FileSpreadsheet className="size-4 text-foreground" />
          <span className="font-medium text-foreground">{s.kind}</span>
          <span className="[overflow-wrap:anywhere]">· {s.file_name}</span>
          <span>· extract taken {day(s.extract_date)}</span>
          {s.route && (
            <span>
              · {ROUTE_LABEL[s.route] ?? "received"}
              {s.route === "upload" && s.received_by ? ` by ${s.received_by}` : ""}, {stamp(s.received_at)}
            </span>
          )}
          <span>· {s.rows.toLocaleString("en-GB")} lines</span>
          {s.next_due && <span>· next extract due by {dueDay(s.next_due)}</span>}
          {s.late && (
            <span className="inline-flex items-center gap-1 rounded-full bg-hot-soft px-2 py-0.5 text-xs font-medium text-hot">
              <AlertTriangle className="size-3" /> No new extract this week; showing last week's
            </span>
          )}
        </div>
      ))}
      <div className="text-xs text-muted-foreground">
        {run.synthetic ? "Practice data (synthetic sample). " : ""}
        Amounts are scaled EUR. "Late" and "days past expected" are counted as of {day(run.as_of)}
        {sources.some((s) => s.kind === "Payroll" && s.extract_date === run.as_of) ? ", the day the Payroll extract was taken." : "."}
      </div>
    </Card>
  );
}

const columns = [
  column.accessor("score", {
    header: "Priority",
    cell: (c) => <ScoreBar record={c.row.original} />,
  }),
  column.accessor("title", {
    header: "What we found",
    enableSorting: false,
    cell: ({ row: { original: r } }) => (
      <div className="flex min-w-0 items-center gap-3">
        <TypeIcon type={r.type} />
        <div className="min-w-0 space-y-1">
          <TypeLabel type={r.type} />
          <div className="line-clamp-2 text-[15px] lg:truncate">{r.title}</div>
          <div className="truncate text-xs text-muted-foreground">
            {r.workgroup} · {r.entity} {r.account} {r.account_name}
          </div>
          {/* Below the full table width, the other columns fold into this line. */}
          <div className="flex flex-wrap items-center gap-x-3 gap-y-1.5 pt-1 lg:hidden">
            <span className={cn("text-[11px] font-medium tracking-wide uppercase", priorityTone(r.score).text)}>
              {priorityTone(r.score).label} · {r.score.toFixed(0)}
            </span>
            {r.exposure_eur ? <span className="num text-sm">{eur(r.exposure_eur)}</span> : null}
            <LeadBadge record={r} />
            <StatusPill status={r.status} />
          </div>
        </div>
      </div>
    ),
  }),
  column.accessor((r) => Math.abs(r.exposure_eur), {
    id: "exposure",
    header: "Amount",
    cell: ({ row: { original: r } }) => (
      <div className="num text-right text-[15px]">{r.exposure_eur ? eur(r.exposure_eur) : "–"}</div>
    ),
  }),
  column.accessor((r) => r.lead_days ?? -1, {
    id: "lead",
    header: "Spotted",
    cell: ({ row: { original: r } }) => <LeadBadge record={r} />,
  }),
  column.accessor("status", {
    header: "Status",
    enableSorting: false,
    cell: (c) => <StatusPill status={c.getValue()} />,
  }),
];

/** Columns folded into the "What we found" cell below the `lg` width (phones and tablets). */
const WIDE_ONLY = new Set(["score", "exposure", "lead", "status"]);
const wideOnly = (id: string) => (WIDE_ONLY.has(id) ? "hidden lg:table-cell" : undefined);

type StatusFilter = "open" | "decided" | "all";
const OPEN: Status[] = ["new", "escalated"];
const GROUPS = Object.keys(GROUP_LABEL) as TypeGroup[];
// Inbox tabs (docs/ASSUMPTIONS.md A25): the default view holds findings at or above materiality
// and missing batches; everything else is one tap away.
type ViewFilter = InboxView | "all";
const VIEWS: { value: ViewFilter; label: string; dot?: string }[] = [
  { value: "attention", label: "Above materiality", dot: "var(--hot)" },
  { value: "prompts", label: "Mistake prompts", dot: GROUP_TONE.mistakes.bar },
  { value: "repeats", label: "Repeated postings", dot: GROUP_TONE.miner.bar },
  { value: "all", label: "Everything" },
];

export function InboxPage() {
  const kpis = useKpis();
  const run = useLatestRun();
  const rules = useRules();
  const all = useExceptions();
  const open = useOpenFinding();
  const [view, setView] = useState<ViewFilter>("attention");
  const [workgroup, setWorkgroup] = useState<"all" | "Payroll" | "Fixed assets">("all");
  const [status, setStatus] = useState<StatusFilter>("open");
  const [sorting, setSorting] = useState<SortingState>([{ id: "score", desc: true }]);
  const period = usePeriod();
  // Every figure below counts only the findings in the chosen period (the shared report period).
  const scoped = useMemo(() => (all.data ?? []).filter((r) => inPeriod(r, period.range)), [all.data, period.range]);

  const records = useMemo(
    () =>
      scoped.filter(
        (r) =>
          (view === "all" || r.inbox_view === view) &&
          (workgroup === "all" || r.workgroup === workgroup) &&
          (status === "all" || (status === "open" ? OPEN.includes(r.status) : !OPEN.includes(r.status))),
      ),
    [scoped, view, workgroup, status],
  );
  const counts = useMemo(() => {
    const out: Record<string, number> = { all: 0 };
    for (const r of scoped) {
      if (!OPEN.includes(r.status)) continue;
      out.all += 1;
      out[TYPE_GROUP[r.type]] = (out[TYPE_GROUP[r.type]] ?? 0) + 1;
      if (r.inbox_view) out[r.inbox_view] = (out[r.inbox_view] ?? 0) + 1;
    }
    return out;
  }, [scoped]);
  // The header and "Waiting for you" speak for the whole check, like "accounts really open",
  // so they read the server's counts (/api/kpis inbox_views, A25); the tabs follow the period.
  const k = kpis.data;
  const attention = k?.inbox_views?.attention ?? 0;
  const toReview = k?.inbox_views?.all ?? 0;
  const limit = rules.data ? shortEur(rules.data.materiality_eur) : "materiality";
  const decided = scoped.filter((r) => !OPEN.includes(r.status)).length;
  const leads = scoped.flatMap((r) => (r.lead_days === null ? [] : [r.lead_days])).sort((a, b) => a - b);
  const median = leads.length
    ? leads.length % 2
      ? leads[(leads.length - 1) / 2]
      : (leads[leads.length / 2 - 1] + leads[leads.length / 2]) / 2
    : null;
  const blind = scoped.filter((r) => r.today_detection === null).length;
  const scope = period.range ? `${period.grain === "day" ? "on" : "in"} ${period.range.label}` : "overall";

  const table = useReactTable({
    data: records,
    columns,
    state: { sorting },
    onSortingChange: setSorting,
    getCoreRowModel: getCoreRowModel(),
    getSortedRowModel: getSortedRowModel(),
  });

  return (
    <div className="space-y-8">
      <PageHeader
        title={`${greeting()} 👋`}
        trail={["Inbox", "Sorted by your priorities"]}
        tour="inbox-header"
        subtitle={
          k ? (
            <>
              Today's report calls <b className="num font-medium text-foreground">{k.old_rule_lines.toLocaleString("en-GB")}</b>{" "}
              lines "overdue". After matching what was paid, only{" "}
              <b className="num font-medium text-foreground">{k.exposure_groups_above}</b>{" "}
              {k.exposure_groups_above === 1 ? "account is" : "accounts are"} really open, and{" "}
              <b className="num font-medium text-hot">{attention}</b> {attention === 1 ? "finding" : "findings"} at or
              above {limit} {attention === 1 ? "needs" : "need"} a look first.
            </>
          ) : (
            "Getting your findings ready…"
          )
        }
      />

      <div data-tour="inbox-period" className="rise flex flex-wrap items-center justify-between gap-3">
        <PeriodPicker />
        <span className="text-xs text-muted-foreground">
          {period.range
            ? `Findings posted or first seen ${period.grain === "day" ? "on" : "in"} ${period.range.label}, plus every balance still open`
            : "Every finding in the latest check"}
        </span>
      </div>

      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-4">
        <StatCard
          dark
          index={0}
          tour="inbox-card-waiting"
          label="Waiting for you"
          value={k ? attention : "–"}
          note={`at or above ${limit}; ${toReview} to review in the whole check`}
          icon={BellRing}
          color="var(--signal)"
          soft="var(--dock-raised)"
          bars={(attention / Math.max(toReview, 1)) * 48}
        />
        <StatCard
          index={1}
          tour="inbox-card-earlier"
          label="Spotted earlier by"
          value={all.data ? (median ?? "–") : "–"}
          unit="days"
          note={`median ${scope}, counted from the weekly ${weekdayName(rules.data?.weekly_run_weekday)} run`}
          icon={Sparkles}
          color="var(--pulse)"
          soft="var(--pulse-soft)"
          bars={Math.min(median ?? 0, 48)}
        />
        <StatCard
          index={2}
          tour="inbox-card-misses"
          label="Today's report misses"
          value={all.data ? blind : "–"}
          note={`findings ${scope} no current check would ever catch`}
          icon={EyeOff}
          color="var(--hot)"
          soft="var(--hot-soft)"
          bars={(blind / Math.max(scoped.length, 1)) * 48}
        />
        <StatCard
          index={3}
          tour="inbox-card-old"
          label="Old report says overdue"
          value={k ? shortEur(k.old_rule_overdue_abs) : "–"}
          note={k ? `${k.old_rule_lines.toLocaleString("en-GB")} lines, mostly already paid` : ""}
          icon={Hourglass}
          color="var(--forest)"
          soft="var(--forest-soft)"
          bars={40}
        />
      </div>

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-[1fr_300px]">
        <Card data-tour="inbox-mix" className="space-y-4" style={stagger(4, 70)}>
          <div className="flex items-center justify-between">
            <span className="eyebrow">Where today's findings come from</span>
            <span className="text-xs text-muted-foreground">open findings only</span>
          </div>
          <SplitBar parts={GROUPS.map((g) => ({ label: GROUP_LABEL[g], value: counts[g] ?? 0, color: GROUP_TONE[g].bar }))} />
          <p className="rounded-xl bg-secondary px-4 py-3 text-sm text-muted-foreground">
            💡 Tip: the list starts with findings at or above {limit}. Mistake prompts, repeated postings and
            everything else are one tap away below. Click any row to see the evidence and make your call.
          </p>
        </Card>
        <Card data-tour="inbox-gauge" className="flex flex-col items-center justify-center gap-2" style={stagger(5, 70)}>
          <Gauge value={decided} total={scoped.length} label="reviewed so far" />
          <span className="text-xs text-muted-foreground">
            {decided === 0 ? "Open a finding to get started" : "Nice progress, keep going"}
          </span>
        </Card>
      </div>

      <DataSources run={run.data} />

      <div className="rise flex flex-wrap items-center justify-between gap-4" style={stagger(6, 70)}>
        <div data-tour="inbox-tabs" className="flex flex-wrap items-center gap-2">
          {VIEWS.map((v) => (
            <Chip key={v.value} active={view === v.value} onClick={() => setView(v.value)} count={counts[v.value] ?? 0} dot={v.dot}>
              {v.value === "attention" ? `Above ${limit}` : v.label}
            </Chip>
          ))}
        </div>
        <div data-tour="inbox-filters" className="flex flex-wrap items-center gap-3">
          <Segmented
            value={workgroup}
            onChange={setWorkgroup}
            options={[
              { value: "all", label: "All books" },
              { value: "Payroll", label: "Payroll" },
              { value: "Fixed assets", label: "Fixed assets" },
            ]}
          />
          <Segmented
            value={status}
            onChange={setStatus}
            options={[
              { value: "open", label: "To review" },
              { value: "decided", label: "Done" },
              { value: "all", label: "All" },
            ]}
          />
        </div>
      </div>

      {all.isLoading ? (
        <div className="space-y-2">
          {Array.from({ length: 6 }).map((_, i) => (
            <Skeleton key={i} className="h-16 w-full" />
          ))}
        </div>
      ) : all.isError ? (
        <Empty title="Nothing to show yet">
          Press <b>Upload extract</b> or <b>Check now</b> at the bottom, or drop a workbook on this page. ({(all.error as Error).message})
        </Empty>
      ) : records.length === 0 ? (
        <Empty title={status === "open" ? "All clear here 🎉" : "Nothing here"}>
          {status === "open" ? "No open finding matches these filters. Enjoy the quiet." : "No finding matches these filters."}
        </Empty>
      ) : (
        <div data-tour="inbox-table" className="rise rounded-2xl bg-card px-2 py-1" style={stagger(7, 70)}>
          <Table className="table-fixed">
            <colgroup>
              <col className="hidden w-32 lg:table-column" />
              <col />
              <col className="hidden w-36 lg:table-column" />
              <col className="hidden w-56 lg:table-column" />
              <col className="hidden w-32 lg:table-column" />
            </colgroup>
            <TableHeader>
              {table.getHeaderGroups().map((hg) => (
                <TableRow key={hg.id} className="hover:bg-transparent">
                  {hg.headers.map((h) => (
                    <TableHead key={h.id} className={cn(h.id === "exposure" && "text-right", wideOnly(h.id))}>
                      {h.column.getCanSort() ? (
                        <button
                          className="inline-flex items-center gap-1 uppercase hover:text-foreground"
                          onClick={h.column.getToggleSortingHandler()}
                        >
                          {flexRender(h.column.columnDef.header, h.getContext())}
                          <ArrowDownUp className="size-3" />
                        </button>
                      ) : (
                        flexRender(h.column.columnDef.header, h.getContext())
                      )}
                    </TableHead>
                  ))}
                </TableRow>
              ))}
            </TableHeader>
            <TableBody>
              {table.getRowModel().rows.map((row, i) => (
                <TableRow
                  key={row.id}
                  data-tour={`finding-${row.original.id}`}
                  className="rise group cursor-pointer transition-colors hover:bg-secondary"
                  style={stagger(i, 35, 700)}
                  onClick={() => open(row.original.id)}
                >
                  {row.getVisibleCells().map((cell) => (
                    <TableCell key={cell.id} className={wideOnly(cell.column.id)}>
                      {flexRender(cell.column.columnDef.cell, cell.getContext())}
                    </TableCell>
                  ))}
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </div>
      )}
    </div>
  );
}
