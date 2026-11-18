import {
  createColumnHelper,
  flexRender,
  getCoreRowModel,
  getSortedRowModel,
  useReactTable,
  type SortingState,
} from "@tanstack/react-table";
import { ArrowDownUp } from "lucide-react";
import { useMemo, useState } from "react";

import { useExceptions, useKpis } from "@/api/hooks";
import type { ExceptionRecord, Status } from "@/api/types";
import { useOpenFinding } from "@/components/AppShell";
import { Chip, Empty, Kpi, LeadBadge, PageHeader, ScoreBar, Segmented, StatusPill, TypeLabel } from "@/components/okane";
import { Skeleton } from "@/components/ui/skeleton";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { GROUP_LABEL, TYPE_GROUP, type TypeGroup } from "@/lib/labels";
import { cn, eur, shortEur } from "@/lib/utils";

const column = createColumnHelper<ExceptionRecord>();

const columns = [
  column.accessor("score", {
    header: "Rank",
    cell: (c) => <ScoreBar record={c.row.original} />,
  }),
  column.accessor("title", {
    header: "Finding",
    enableSorting: false,
    cell: ({ row: { original: r } }) => (
      <div className="min-w-0 space-y-1">
        <TypeLabel type={r.type} />
        <div className="truncate text-[15px]">{r.title}</div>
        <div className="truncate text-xs text-muted-foreground">
          {r.workgroup} · {r.erp} · {r.entity} {r.account} {r.account_name}
        </div>
      </div>
    ),
  }),
  column.accessor((r) => Math.abs(r.exposure_eur), {
    id: "exposure",
    header: "Exposure",
    cell: ({ row: { original: r } }) => (
      <div className="num text-right text-[15px]">{r.exposure_eur ? eur(r.exposure_eur) : "–"}</div>
    ),
  }),
  column.accessor((r) => r.lead_days ?? -1, {
    id: "lead",
    header: "Lead time",
    cell: ({ row: { original: r } }) => <LeadBadge record={r} />,
  }),
  column.accessor("suggested_class", {
    header: "Suggested class",
    enableSorting: false,
    cell: ({ row: { original: r } }) => (
      <span className="text-xs text-muted-foreground">{r.decided_class ?? r.suggested_class ?? "–"}</span>
    ),
  }),
  column.accessor("status", {
    header: "Status",
    enableSorting: false,
    cell: (c) => <StatusPill status={c.getValue()} />,
  }),
];

type StatusFilter = "open" | "decided" | "all";
const OPEN: Status[] = ["new", "escalated"];

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
      <PageHeader title="Inbox" trail={["Findings", "Ranked by the controller's rules"]} />

      <div className="grid grid-cols-2 divide-x border-y py-6 md:grid-cols-4">
        <Kpi label="Open findings" value={k?.open_exceptions ?? "–"} note={`${k?.exceptions ?? "–"} in this run`} />
        <Kpi
          label="Median days earlier"
          value={k?.median_days_earlier ?? "–"}
          unit="days"
          note="than the close review or ageing rule"
        />
        <Kpi label="Blind spots" value={k?.blind_spots ?? "–"} note="today's process never flags these" />
        <Kpi
          label="Old report"
          value={k ? shortEur(k.old_rule_overdue_abs) : "–"}
          note={k ? `${k.old_rule_lines.toLocaleString("en-GB")} lines "overdue" · ${k.exposure_groups_above} real exposures` : ""}
        />
      </div>

      <div className="flex flex-wrap items-center justify-between gap-4">
        <div className="flex flex-wrap items-center gap-2">
          <Chip active={group === "all"} onClick={() => setGroup("all")} count={counts.all}>
            All
          </Chip>
          {(Object.keys(GROUP_LABEL) as TypeGroup[]).map((g) => (
            <Chip key={g} active={group === g} onClick={() => setGroup(g)} count={counts[g] ?? 0}>
              {GROUP_LABEL[g]}
            </Chip>
          ))}
        </div>
        <div className="flex items-center gap-8">
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
              { value: "open", label: "Open" },
              { value: "decided", label: "Decided" },
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
        <Empty title="No run to show yet">
          {(all.error as Error).message}
        </Empty>
      ) : records.length === 0 ? (
        <Empty title="Nothing here">No finding matches these filters.</Empty>
      ) : (
        <div className="rounded-2xl bg-card px-2 py-1">
          <Table className="table-fixed">
            <colgroup>
              <col className="w-32" />
              <col />
              <col className="w-36" />
              <col className="w-60" />
              <col className="w-44" />
              <col className="w-28" />
            </colgroup>
            <TableHeader>
              {table.getHeaderGroups().map((hg) => (
                <TableRow key={hg.id} className="hover:bg-transparent">
                  {hg.headers.map((h) => (
                    <TableHead key={h.id} className={cn(h.id === "exposure" && "text-right")}>
                      {h.column.getCanSort() ? (
                        <button
                          className="inline-flex items-center gap-1 hover:text-foreground"
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
              {table.getRowModel().rows.map((row) => (
                <TableRow key={row.id} className="cursor-pointer" onClick={() => open(row.original.id)}>
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
