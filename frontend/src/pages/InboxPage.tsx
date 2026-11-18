import {
  createColumnHelper,
  flexRender,
  getCoreRowModel,
  getSortedRowModel,
  useReactTable,
  type SortingState,
} from "@tanstack/react-table";
import { ArrowDownUp, BellRing, EyeOff, Hourglass, Sparkles } from "lucide-react";
import { useMemo, useState } from "react";

import { useExceptions, useKpis } from "@/api/hooks";
import type { ExceptionRecord, Status } from "@/api/types";
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
  stagger,
} from "@/components/okane";
import { Skeleton } from "@/components/ui/skeleton";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { GROUP_LABEL, GROUP_TONE, TYPE_GROUP, greeting, type TypeGroup } from "@/lib/labels";
import { cn, eur, shortEur } from "@/lib/utils";

const column = createColumnHelper<ExceptionRecord>();

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
          <div className="truncate text-[15px]">{r.title}</div>
          <div className="truncate text-xs text-muted-foreground">
            {r.workgroup} · {r.entity} {r.account} {r.account_name}
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

type StatusFilter = "open" | "decided" | "all";
const OPEN: Status[] = ["new", "escalated"];
const GROUPS = Object.keys(GROUP_LABEL) as TypeGroup[];

export function InboxPage() {
  const kpis = useKpis();
  const all = useExceptions();
  const open = useOpenFinding();
  const [group, setGroup] = useState<TypeGroup | "all">("all");
  const [workgroup, setWorkgroup] = useState<"all" | "Payroll" | "Fixed assets">("all");
  const [status, setStatus] = useState<StatusFilter>("open");
  const [sorting, setSorting] = useState<SortingState>([{ id: "score", desc: true }]);

  const records = useMemo(
    () =>
      (all.data ?? []).filter(
        (r) =>
          (group === "all" || TYPE_GROUP[r.type] === group) &&
          (workgroup === "all" || r.workgroup === workgroup) &&
          (status === "all" || (status === "open" ? OPEN.includes(r.status) : !OPEN.includes(r.status))),
      ),
    [all.data, group, workgroup, status],
  );
  const counts = useMemo(() => {
    const out: Record<string, number> = { all: 0 };
    for (const r of all.data ?? []) {
      if (!OPEN.includes(r.status)) continue;
      out.all += 1;
      out[TYPE_GROUP[r.type]] = (out[TYPE_GROUP[r.type]] ?? 0) + 1;
    }
    return out;
  }, [all.data]);
  const urgent = (all.data ?? []).filter((r) => OPEN.includes(r.status) && r.score >= 70).length;
  const decided = (all.data ?? []).filter((r) => !OPEN.includes(r.status)).length;

  const table = useReactTable({
    data: records,
    columns,
    state: { sorting },
    onSortingChange: setSorting,
    getCoreRowModel: getCoreRowModel(),
    getSortedRowModel: getSortedRowModel(),
  });

  const k = kpis.data;
  return (
    <div className="space-y-8">
      <PageHeader
        title={`${greeting()} 👋`}
        trail={["Inbox", "Sorted by your priorities"]}
        subtitle={
          k ? (
            <>
              Today's report calls <b className="num font-medium text-foreground">{k.old_rule_lines.toLocaleString("en-GB")}</b>{" "}
              lines "overdue". After matching what was paid, only{" "}
              <b className="num font-medium text-foreground">{k.exposure_groups_above}</b>{" "}
              {k.exposure_groups_above === 1 ? "account is" : "accounts are"} really open, and{" "}
              <b className="num font-medium text-hot">{urgent}</b> {urgent === 1 ? "finding deserves" : "findings deserve"} a look first.
            </>
          ) : (
            "Getting your findings ready…"
          )
        }
      />

      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-4">
        <StatCard
          dark
          index={0}
          label="Waiting for you"
          value={k?.open_exceptions ?? "–"}
          note={`out of ${k?.exceptions ?? "–"} found in the latest check`}
          icon={BellRing}
          color="var(--signal)"
          soft="var(--dock-raised)"
          bars={k ? (k.open_exceptions / Math.max(k.exceptions, 1)) * 48 : 0}
        />
        <StatCard
          index={1}
          label="Spotted earlier by"
          value={k?.median_days_earlier ?? "–"}
          unit="days"
          note="median, counted from the weekly Monday run"
          icon={Sparkles}
          color="var(--pulse)"
          soft="var(--pulse-soft)"
          bars={Math.min(k?.median_days_earlier ?? 0, 48)}
        />
        <StatCard
          index={2}
          label="Today's report misses"
          value={k?.blind_spots ?? "–"}
          note="findings no current check would ever catch"
          icon={EyeOff}
          color="var(--hot)"
          soft="var(--hot-soft)"
          bars={k ? (k.blind_spots / Math.max(k.exceptions, 1)) * 48 : 0}
        />
        <StatCard
          index={3}
          label="Old report says overdue"
          value={k ? shortEur(k.old_rule_overdue_abs) : "–"}
          note={k ? `${k.old_rule_lines.toLocaleString("en-GB")} lines, mostly already paid` : ""}
          icon={Hourglass}
          color="var(--forest)"
          soft="var(--forest-soft)"
          bars={40}
        />
      </div>

      <div className="grid gap-4 lg:grid-cols-[1fr_300px]">
        <Card className="space-y-4" style={stagger(4, 70)}>
          <div className="flex items-center justify-between">
            <span className="eyebrow">Where today's findings come from</span>
            <span className="text-xs text-muted-foreground">open findings only</span>
          </div>
          <SplitBar parts={GROUPS.map((g) => ({ label: GROUP_LABEL[g], value: counts[g] ?? 0, color: GROUP_TONE[g].bar }))} />
          <p className="rounded-xl bg-secondary px-4 py-3 text-sm text-muted-foreground">
            💡 Tip: tap a coloured pill below to see just one kind of finding. Click any row to see the evidence and
            make your call.
          </p>
        </Card>
        <Card className="flex flex-col items-center justify-center gap-2" style={stagger(5, 70)}>
          <Gauge value={decided} total={(all.data ?? []).length} label="reviewed so far" />
          <span className="text-xs text-muted-foreground">
            {decided === 0 ? "Open a finding to get started" : "Nice progress, keep going"}
          </span>
        </Card>
      </div>

      <div className="rise flex flex-wrap items-center justify-between gap-4" style={stagger(6, 70)}>
        <div className="flex flex-wrap items-center gap-2">
          <Chip active={group === "all"} onClick={() => setGroup("all")} count={counts.all}>
            Everything
          </Chip>
          {GROUPS.map((g) => (
            <Chip key={g} active={group === g} onClick={() => setGroup(g)} count={counts[g] ?? 0} dot={GROUP_TONE[g].bar}>
              {GROUP_LABEL[g]}
            </Chip>
          ))}
        </div>
        <div className="flex flex-wrap items-center gap-3">
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
          Press <b>Check now</b> at the bottom, or drop a workbook into data/inbox. ({(all.error as Error).message})
        </Empty>
      ) : records.length === 0 ? (
        <Empty title={status === "open" ? "All clear here 🎉" : "Nothing here"}>
          {status === "open" ? "No open finding matches these filters. Enjoy the quiet." : "No finding matches these filters."}
        </Empty>
      ) : (
        <div className="rise rounded-2xl bg-card px-2 py-1" style={stagger(7, 70)}>
          <Table className="table-fixed">
            <colgroup>
              <col className="w-32" />
              <col />
              <col className="w-36" />
              <col className="w-56" />
              <col className="w-32" />
            </colgroup>
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
                  className="rise group cursor-pointer transition-colors hover:bg-secondary"
                  style={stagger(i, 35, 700)}
                  onClick={() => open(row.original.id)}
                >
                  {row.getVisibleCells().map((cell) => (
                    <TableCell key={cell.id}>{flexRender(cell.column.columnDef.cell, cell.getContext())}</TableCell>
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
