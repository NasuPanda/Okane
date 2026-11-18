import { useQueryClient } from "@tanstack/react-query";
import { Inbox, Layers, Loader2, Play, Radar, SlidersHorizontal, FolderInput } from "lucide-react";
import { useEffect, useState } from "react";
import { NavLink, Outlet, useLocation, useSearchParams } from "react-router";
import { toast } from "sonner";

import { API_MODE, api } from "@/api/client";
import { useKpis, useLatestRun, useStartRun } from "@/api/hooks";
import { ExceptionDrawer } from "@/components/ExceptionDrawer";
import { Button } from "@/components/ui/button";
import { Toaster } from "@/components/ui/sonner";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { cn, stamp } from "@/lib/utils";

const NAV = [
  { to: "/", label: "Inbox", icon: Inbox, end: true },
  { to: "/exposure", label: "Exposure", icon: Layers },
  { to: "/sentinel", label: "Sentinel", icon: Radar },
  { to: "/rules", label: "Rules", icon: SlidersHorizontal },
];

function Logo() {
  return (
    <div className="flex items-center gap-2.5">
      <svg viewBox="0 0 32 32" className="size-7" aria-hidden>
        <rect width="32" height="32" rx="8" fill="var(--foreground)" />
        <path d="M9 21.5 16 9l7 12.5" fill="none" stroke="var(--signal)" strokeWidth="2.6" strokeLinecap="round" strokeLinejoin="round" />
        <path d="M11.5 17h9" stroke="#fff" strokeWidth="2.2" strokeLinecap="round" />
      </svg>
      <span className="text-[17px] font-medium tracking-tight">Okane</span>
    </div>
  );
}

function TopBar() {
  const { pathname } = useLocation();
  return (
    <header className="flex items-center justify-between gap-6 py-6">
      <Logo />
      <nav className="flex items-center gap-2" aria-label="Main">
        {NAV.map(({ to, label, icon: Icon, end }) => {
          // Radix asChild merges className as a string, so the active state is computed here.
          const active = end ? pathname === to : pathname.startsWith(to);
          return (
          <Tooltip key={to}>
            <TooltipTrigger asChild>
              <NavLink
                to={to}
                end={end}
                aria-label={label}
                aria-current={active ? "page" : undefined}
                className={cn(
                  "grid size-10 place-items-center rounded-lg border transition",
                  active
                    ? "border-foreground bg-foreground text-white"
                    : "border-border bg-secondary text-foreground hover:bg-accent",
                )}
              >
                <Icon className="size-[18px]" />
              </NavLink>
            </TooltipTrigger>
            <TooltipContent side="bottom">{label}</TooltipContent>
          </Tooltip>
          );
        })}
      </nav>
      <div className="flex items-center gap-3">
        <span
          className={cn(
            "rounded-full border px-2.5 py-1 text-[11px]",
            API_MODE === "fixtures" ? "border-warn/40 bg-warn-soft text-warn" : "bg-secondary text-muted-foreground",
          )}
        >
          {API_MODE === "fixtures" ? "Synthetic fixtures" : "Live"} · amounts scaled EUR
        </span>
        <div className="flex items-center gap-2.5 rounded-lg border bg-secondary py-1 pr-3 pl-1">
          <span className="grid size-8 place-items-center rounded-md bg-foreground text-xs font-medium text-white">C</span>
          <div className="leading-tight">
            <div className="text-xs font-medium">Controller</div>
            <div className="text-[11px] text-muted-foreground">Payroll · Fixed assets</div>
          </div>
        </div>
      </div>
    </header>
  );
}

/** Floating run dock (bottom): last run, live run state, "Run now". Toasts come from SSE. */
function RunDock() {
  const run = useLatestRun();
  const kpis = useKpis();
  const start = useStartRun();
  const client = useQueryClient();
  const [running, setRunning] = useState(false);

  useEffect(
    () =>
      api.subscribe(({ event, data }) => {
        if (event === "run_started") {
          setRunning(true);
          const why = { watcher: "New workbook in the inbox", schedule: "Weekly Monday run", rules_change: "Rules changed" }[
            String(data.trigger)
          ];
          toast.loading("Run started", { id: "run", description: why ?? "Reading the newest workbooks" });
        } else {
          setRunning(false);
          void client.invalidateQueries();
          if (data.status === "failed") {
            toast.error("Run failed", { id: "run", description: String(data.error ?? "") });
          } else {
            const found = data.counts?.exceptions;
            toast.success("Run finished", {
              id: "run",
              description: found !== undefined ? `${found} findings ranked · ${data.source_files?.join(", ")}` : undefined,
            });
          }
        }
      }),
    [client],
  );

  const latest = run.data;
  const busy = running || latest?.status === "running" || start.isPending;
  return (
    <div className="pointer-events-none fixed inset-x-0 bottom-5 z-40 flex justify-center">
      <div className="pointer-events-auto flex items-center gap-3 rounded-2xl bg-dock/95 p-2 pr-2.5 text-white shadow-2xl backdrop-blur">
        <span className={cn("grid size-10 place-items-center rounded-xl", busy ? "bg-dock-raised" : "bg-signal text-foreground")}>
          {busy ? <Loader2 className="size-5 animate-spin text-signal" /> : <FolderInput className="size-5" />}
        </span>
        <div className="min-w-0 px-1 text-sm leading-tight">
          {busy ? (
            <div>Reading the extract and ranking findings…</div>
          ) : latest ? (
            <>
              <div className="truncate">
                Last run {stamp(latest.finished_at ?? latest.started_at)} ·{" "}
                <span className="text-white/60">{latest.source_files.join(", ") || "no workbook"}</span>
              </div>
              <div className="text-xs text-white/50">
                Watching data/inbox · next run Monday 06:00 · {kpis.data?.open_exceptions ?? "–"} open findings
                {latest.synthetic && " · synthetic sample"}
              </div>
            </>
          ) : (
            <div className="text-white/70">No run yet. Drop a workbook into data/inbox or run now.</div>
          )}
        </div>
        <Button
          size="sm"
          variant="signal"
          className="ml-2 h-10 rounded-xl px-4"
          disabled={busy}
          onClick={() =>
            start.mutate(undefined, {
              onError: (e) => toast.error("Could not start a run", { description: String((e as Error).message) }),
            })
          }
        >
          <Play className="size-3.5" /> Run now
        </Button>
      </div>
    </div>
  );
}

export function AppShell() {
  const [params, setParams] = useSearchParams();
  const finding = params.get("finding");
  return (
    <div className="mx-auto min-h-screen max-w-[1320px] px-8 pb-32">
      <TopBar />
      <main>
        <Outlet />
      </main>
      <RunDock />
      <ExceptionDrawer
        id={finding}
        onClose={() => {
          params.delete("finding");
          setParams(params, { replace: true });
        }}
      />
      <Toaster />
    </div>
  );
}

/** Open the drawer for one finding from anywhere (keeps the current page and filters). */
export function useOpenFinding() {
  const [params, setParams] = useSearchParams();
  return (id: string | null | undefined) => {
    if (!id) return;
    params.set("finding", id);
    setParams(params);
  };
}
