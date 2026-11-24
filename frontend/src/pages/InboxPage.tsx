import {
  createColumnHelper,
  flexRender,
  getCoreRowModel,
  getSortedRowModel,
  useReactTable,
  type SortingState,
} from "@tanstack/react-table";
import { AlertTriangle, ArrowDownUp, BellRing, EyeOff, FileSpreadsheet, Hourglass, Sparkles } from "lucide-react";
import { useMemo, useState, useSyncExternalStore } from "react";

import { useExceptions, useFixedAssets, useKpis, useLatestRun, useRules } from "@/api/hooks";
import type { ExceptionRecord, InboxView, Run, Status } from "@/api/types";
import { useOpenFinding } from "@/components/AppShell";
import {
  Card,
  Chip,
  Empty,
  Gauge,
  LeadBadge,
  NewTag,
  PageHeader,
  ScoreBar,
  Segmented,
  SplitBar,
  StatCard,
  StatusPill,
  TypeIcon,
  TypeLabel,
  stagger,
} from "@/components/okane";
import { Skeleton } from "@/components/ui/skeleton";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { GROUP_LABEL, GROUP_TONE, ROUTE_LABEL, TYPE_GROUP, greeting, weekdayName, type TypeGroup } from "@/lib/labels";
import { PeriodPicker, inPeriod, useIsNew, usePeriod } from "@/lib/period";
import { cn, day, dueDay, eur, shortEur, stamp } from "@/lib/utils";

const column = createColumnHelper<ExceptionRecord>();

/** At `lg` (1024px) and wider the Inbox shows every column; narrower, they fold under the title. */
const WIDE = "(min-width: 1024px)";
function useWide(): boolean {
  return useSyncExternalStore(
    (onChange) => {
      const query = window.matchMedia(WIDE);
      query.addEventListener("change", onChange);
      return () => query.removeEventListener("change", onChange);
    },
    () => window.matchMedia(WIDE).matches,
  );
}

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

function NewFlag({ record }: { record: ExceptionRecord }) {
  const isNew = useIsNew();
  return <NewTag show={isNew(record)} />;
}

const columns = [
  column.accessor("score", {
    header: "Priority",
    cell: (c) => <ScoreBar record={c.row.original} />,
  }),
  column.accessor("title", {
    header: "What we found",
    enableSorting: false,
    cell: ({ row: { original: r }, table }) => {
      const wide = (table.options.meta as { wide?: boolean } | undefined)?.wide ?? true;
      return (
        <div className="flex min-w-0 items-center gap-3">
          <TypeIcon type={r.type} />
          <div className="min-w-0 space-y-1">
            <div className="flex flex-wrap items-center gap-2">
              <TypeLabel type={r.type} />
              <NewFlag record={r} />
            </div>
            <div className={cn("text-[15px]", wide ? "truncate" : "line-clamp-2")}>{r.title}</div>
            <div className="truncate text-xs text-muted-foreground">
              {r.workgroup} · {r.entity} {r.account} {r.account_name}
            </div>
            {/* Below the full table width, the other columns fold into this line. */}
            {!wide && (
              <div className="flex flex-wrap items-center gap-x-3 gap-y-1.5 pt-1">
                <ScoreBar record={r} compact />
                {r.exposure_eur ? <span className="num text-sm">{eur(r.exposure_eur)}</span> : null}
                <LeadBadge record={r} tip={false} />
                <StatusPill status={r.status} />
              </div>
            )}
          </div>
        </div>
      );
    },
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
const NARROW_HIDDEN = { score: false, exposure: false, lead: false, status: false };
/** Below `lg` the sortable headers are hidden, so a "Sort by" control takes their place. */
const SORTS: { value: string; label: string }[] = [
  { value: "score", label: "Priority" },
  { value: "exposure", label: "Amount" },
  { value: "lead", label: "Spotted" },
];

type StatusFilter = "open" | "decided" | "all";
const OPEN: Status[] = ["new", "escalated"];
const GROUPS = Object.keys(GROUP_LABEL) as TypeGroup[];
// Inbox tabs (docs/ASSUMPTIONS.md A25): the default view holds findings at or above materiality
// and missing batches; everything else is one tap away. Every finding sits on exactly one of the
// four tabs (the server's inbox_view), so their counts always add up to "Everything". Tabs can
// be combined: the list shows every finding on any selected tab (A48).
const VIEWS: { value: InboxView; label: string; dot?: string }[] = [
  { value: "attention", label: "Above materiality", dot: "var(--hot)" },
  { value: "other", label: "Below materiality", dot: "var(--muted-foreground)" },
  { value: "prompts", label: "Mistake prompts", dot: GROUP_TONE.mistakes.bar },
  { value: "repeats", label: "Repeated postings", dot: GROUP_TONE.miner.bar },
];
const ALL_VIEWS = VIEWS.map((v) => v.value);
const viewOf = (r: ExceptionRecord): InboxView => r.inbox_view ?? "other";

// The book the page reads (A48): Payroll or Fixed assets, or both together.
type PrimaryBook = "Payroll" | "Fixed assets";

/** Toggle switch between the two books, with "Both books" for the combined view. */
function BookSwitch({
  primary,
  both,
  onPrimary,
  onBoth,
}: {
  primary: PrimaryBook;
  both: boolean;
  onPrimary: (b: PrimaryBook) => void;
  onBoth: (b: boolean) => void;
}) {
  const fixed = primary === "Fixed assets";
  const side = (active: boolean) =>
    cn("transition-colors", !both && active ? "font-medium text-foreground" : "text-muted-foreground");
  return (
    <div className="inline-flex h-10 items-center gap-3 rounded-full border bg-secondary px-4 text-sm">
      <button type="button" className={side(!fixed)} onClick={() => onPrimary("Payroll")} disabled={both}>
        Payroll
      </button>
      <button
        type="button"
        role="switch"
        aria-checked={fixed}
        aria-label="Read the Fixed assets book instead of Payroll"
        disabled={both}
        onClick={() => onPrimary(fixed ? "Payroll" : "Fixed assets")}
        className={cn(
          "relative h-6 w-11 shrink-0 rounded-full transition-colors disabled:opacity-40",
          fixed ? "bg-signal" : "bg-foreground/25",
        )}
      >
        <span
          className={cn(
            "absolute top-0.5 left-0.5 size-5 rounded-full bg-background shadow transition-transform",
            fixed && "translate-x-5",
          )}
        />
      </button>
      <button type="button" className={side(fixed)} onClick={() => onPrimary("Fixed assets")} disabled={both}>
        Fixed assets
      </button>
      <span className="h-5 w-px bg-border" />
      <label className="flex cursor-pointer items-center gap-2 text-muted-foreground">
        <input type="checkbox" className="accent-[var(--signal)]" checked={both} onChange={(e) => onBoth(e.target.checked)} />
        Both books
      </label>
    </div>
  );
}

export function InboxPage() {
  const kpis = useKpis();
  const run = useLatestRun();
  const rules = useRules();
  const all = useExceptions();
  const open = useOpenFinding();
  // Selected tabs (combined as a union); "New this week" adds its findings to them.
  const [views, setViews] = useState<InboxView[]>(["attention"]);
  const [newOnly, setNewOnly] = useState(false);
  const [primary, setPrimary] = useState<PrimaryBook>("Payroll");
  const [both, setBoth] = useState(false);
  const [status, setStatus] = useState<StatusFilter>("open");
  const isNew = useIsNew();
  const [sorting, setSorting] = useState<SortingState>([{ id: "score", desc: true }]);
  const wide = useWide();
  const period = usePeriod();
  const fixedAssets = useFixedAssets();
  const book = both ? null : primary;
  // Every figure on this page reads the chosen book only ...
  const booked = useMemo(() => (all.data ?? []).filter((r) => !book || r.workgroup === book), [all.data, book]);
  // ... and, except the header, only the findings in the chosen period (the shared report period).
  const scoped = useMemo(() => booked.filter((r) => inPeriod(r, period.range)), [booked, period.range]);
  // The tab counts are the findings the list would show for that tab alone (same book, period
  // and status), so the four tabs add up to "Everything" and the list to what is selected.
  const listed = useMemo(
    () =>
      scoped.filter(
        (r) => status === "all" || (status === "open" ? OPEN.includes(r.status) : !OPEN.includes(r.status)),
      ),
    [scoped, status],
  );
  const records = useMemo(
    () => listed.filter((r) => views.includes(viewOf(r)) || (newOnly && isNew(r))),
    [listed, views, newOnly, isNew],
  );
  const tabCounts = useMemo(() => {
    const out: Record<string, number> = { all: listed.length, new: 0 };
    for (const r of listed) {
      out[viewOf(r)] = (out[viewOf(r)] ?? 0) + 1;
      if (isNew(r)) out.new += 1;
    }
    return out;
  }, [listed, isNew]);
  const everything = ALL_VIEWS.every((v) => views.includes(v));
  const toggleView = (v: InboxView) => {
    if (views.includes(v)) {
      // never leave the list with nothing selected
      if (views.length > 1 || newOnly) setViews(views.filter((x) => x !== v));
    } else {
      setViews([...views, v]);
    }
  };
  const toggleNew = () => {
    if (newOnly && views.length === 0) setViews(["attention"]);
    setNewOnly(!newOnly);
  };
  // "Where today's findings come from" counts open findings by kind, in the same book and period.
  const counts = useMemo(() => {
    const out: Record<string, number> = { all: 0 };
    for (const r of scoped) {
      if (!OPEN.includes(r.status)) continue;
      out.all += 1;
      out[TYPE_GROUP[r.type]] = (out[TYPE_GROUP[r.type]] ?? 0) + 1;
    }
    return out;
  }, [scoped]);
  // The header and "Waiting for you" speak for the whole check (any period) in the chosen book:
  // the open findings the server counts in /api/kpis inbox_views (A25), narrowed to the book.
  const k = kpis.data;
  const bookOpen = booked.filter((r) => OPEN.includes(r.status));
  const attention = all.data ? bookOpen.filter((r) => viewOf(r) === "attention").length : (k?.inbox_views?.attention ?? 0);
  const toReview = all.data ? bookOpen.length : (k?.inbox_views?.all ?? 0);
  const fa = fixedAssets.data;
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
    state: { sorting, columnVisibility: wide ? {} : NARROW_HIDDEN },
    meta: { wide },
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
          book === "Fixed assets" && fa ? (
            <>
              The Fixed assets extract has <b className="num font-medium text-foreground">{fa.lines.toLocaleString("en-GB")}</b>{" "}
              lines. After matching, <b className="num font-medium text-foreground">{fa.paired_lines.toLocaleString("en-GB")}</b>{" "}
              cancel in exact pairs, <b className="num font-medium text-foreground">{(fa.recent_lines + fa.older_lines).toLocaleString("en-GB")}</b>{" "}
              are still open, and <b className="num font-medium text-hot">{attention}</b>{" "}
              {attention === 1 ? "finding" : "findings"} at or above {limit} {attention === 1 ? "needs" : "need"} a look first.
            </>
          ) : k ? (
            <>
              Today's report calls <b className="num font-medium text-foreground">{k.old_rule_lines.toLocaleString("en-GB")}</b>{" "}
              lines "overdue". After matching what was paid, only{" "}
              <b className="num font-medium text-foreground">{k.exposure_groups_above}</b>{" "}
              {k.exposure_groups_above === 1 ? "account is" : "accounts are"} really open, and{" "}
              <b className="num font-medium text-hot">{attention}</b> {attention === 1 ? "finding" : "findings"}
              {book ? ` in ${book}` : ""} at or above {limit} {attention === 1 ? "needs" : "need"} a look first.
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
          note={`at or above ${limit}; ${toReview} to review in ${book ?? "both books"}, whole check`}
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
          note={`median ${scope}, counted from the weekly ${weekdayName(rules.data?.weekly_run_weekday)} run, replayed over the extract's history`}
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
        {book === "Fixed assets" ? (
          // The ageing report's "overdue" is a Payroll column; Fixed assets has none (A47).
          <StatCard
            index={3}
            tour="inbox-card-old"
            label="Still open after matching"
            value={fa ? (fa.recent_lines + fa.older_lines).toLocaleString("en-GB") : "–"}
            note={fa ? `of ${fa.lines.toLocaleString("en-GB")} Fixed assets lines; ${fa.paired_lines.toLocaleString("en-GB")} cancel in exact pairs` : ""}
            icon={Hourglass}
            color="var(--forest)"
            soft="var(--forest-soft)"
            bars={40}
          />
        ) : (
          <StatCard
            index={3}
            tour="inbox-card-old"
            label="Old report says overdue"
            value={k ? shortEur(k.old_rule_overdue_abs) : "–"}
            note={k ? `${k.old_rule_lines.toLocaleString("en-GB")} Payroll lines, mostly already paid` : ""}
            icon={Hourglass}
            color="var(--forest)"
            soft="var(--forest-soft)"
            bars={40}
          />
        )}
      </div>

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-[1fr_300px]">
        <Card data-tour="inbox-mix" className="space-y-4" style={stagger(4, 70)}>
          <div className="flex items-center justify-between">
            <span className="eyebrow">Where today's findings come from</span>
            <span className="text-xs text-muted-foreground">open findings only</span>
          </div>
          <SplitBar parts={GROUPS.map((g) => ({ label: GROUP_LABEL[g], value: counts[g] ?? 0, color: GROUP_TONE[g].bar }))} />
          <p className="rounded-xl bg-secondary px-4 py-3 text-sm text-muted-foreground">
            💡 Tip: the list starts with findings at or above {limit}. Tap more tabs below to add them to the
            list. Click any row to see the evidence and make your call.
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

      <div className="rise space-y-3" style={stagger(6, 70)}>
        {/* Row 1, filters: which book, which status. Every count in row 2 follows them. */}
        <div data-tour="inbox-filters" className="flex flex-wrap items-center gap-3">
          <BookSwitch primary={primary} both={both} onPrimary={setPrimary} onBoth={setBoth} />
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
        {/* Row 2, tabs: tap several to combine them; the four tabs add up to Everything. */}
        <div data-tour="inbox-tabs" className="flex flex-wrap items-center gap-2">
          {VIEWS.map((v) => (
            <Chip
              key={v.value}
              active={views.includes(v.value)}
              onClick={() => toggleView(v.value)}
              count={tabCounts[v.value] ?? 0}
              dot={v.dot}
            >
              {v.value === "attention" ? `Above ${limit}` : v.value === "other" ? `Below ${limit}` : v.label}
            </Chip>
          ))}
          <Chip
            active={everything}
            onClick={() => setViews(everything ? ["attention"] : [...ALL_VIEWS])}
            count={tabCounts.all}
          >
            Everything
          </Chip>
          <Chip active={newOnly} onClick={toggleNew} count={tabCounts.new} dot="var(--signal)">
            New this week
          </Chip>
          <span className="ml-1 text-xs text-muted-foreground">
            Showing <b className="num font-medium text-foreground">{records.length}</b> of {tabCounts.all}
          </span>
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
          {status === "open"
            ? "No open finding sits on the selected tabs. Tap another tab to add it, or Everything. Enjoy the quiet."
            : "No finding sits on the selected tabs."}
        </Empty>
      ) : (
        <div data-tour="inbox-table" className="rise rounded-2xl bg-card px-2 py-1" style={stagger(7, 70)}>
          {!wide && (
            <div className="flex flex-wrap items-center gap-2 px-2 pt-2 pb-1 text-xs text-muted-foreground">
              Sort by
              <Segmented
                value={sorting[0]?.id ?? "score"}
                onChange={(id) => setSorting([{ id, desc: true }])}
                options={SORTS}
              />
            </div>
          )}
          <Table className="table-fixed">
            {wide && (
              <colgroup>
                <col className="w-32" />
                <col />
                <col className="w-36" />
                <col className="w-56" />
                <col className="w-32" />
              </colgroup>
            )}
            <TableHeader>
              {table.getHeaderGroups().map((hg) => (
                <TableRow key={hg.id} className="hover:bg-transparent">
                  {hg.headers.map((h) => (
                    <TableHead key={h.id} className={cn(h.id === "exposure" && "text-right")}>
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
                    <TableCell key={cell.id}>
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
