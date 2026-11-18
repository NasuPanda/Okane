import { useQueryClient } from "@tanstack/react-query";
import { FolderInput, Inbox, Layers, Loader2, Moon, Play, Radar, SlidersHorizontal, Sun } from "lucide-react";
import { useEffect, useState } from "react";
import { NavLink, Outlet, useLocation, useSearchParams } from "react-router";
import { toast } from "sonner";

import { API_MODE, api } from "@/api/client";
import { useKpis, useLatestRun, useStartRun } from "@/api/hooks";
import { ExceptionDrawer } from "@/components/ExceptionDrawer";
import { Button } from "@/components/ui/button";
import { Toaster } from "@/components/ui/sonner";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { useTheme } from "@/lib/theme";
import { cn, stamp } from "@/lib/utils";

const NAV = [
  { to: "/", label: "Inbox: what needs you", icon: Inbox, end: true },
  { to: "/exposure", label: "Exposure: what's really open", icon: Layers },
  { to: "/sentinel", label: "Sentinel: posting-day checks", icon: Radar },
  { to: "/rules", label: "Rules: your settings", icon: SlidersHorizontal },
];

function Logo() {
  return (
    <div className="flex items-center gap-2.5">
      <svg viewBox="0 0 32 32" className="size-8 transition-transform hover:rotate-[-8deg]" aria-hidden>
        <rect width="32" height="32" rx="9" fill="#0d0d0f" />
        <path d="M9 21.5 16 9l7 12.5" fill="none" stroke="#b4ef4f" strokeWidth="2.6" strokeLinecap="round" strokeLinejoin="round" />
        <path d="M11.5 17h9" stroke="#fff" strokeWidth="2.2" strokeLinecap="round" />
      </svg>
      <div className="leading-none">
        <div className="text-[17px] font-medium tracking-tight">Okane</div>
        <div className="mt-0.5 text-[10.5px] text-muted-foreground">reconciliation copilot</div>
      </div>
    </div>
  );
}

function ThemeToggle() {
  const { theme, toggle } = useTheme();
  const dark = theme === "dark";
  return (
    <Tooltip>
      <TooltipTrigger asChild>
        <button
          onClick={toggle}
          aria-label={dark ? "Switch to light mode" : "Switch to dark mode"}
          className="relative grid size-10 place-items-center overflow-hidden rounded-lg border bg-secondary transition hover:bg-accent"
        >
          <Sun className={cn("absolute size-[18px] transition-all duration-500", dark ? "translate-y-6 rotate-90 opacity-0" : "text-mistake")} />
          <Moon className={cn("absolute size-[18px] transition-all duration-500", dark ? "text-sentinel" : "-translate-y-6 -rotate-90 opacity-0")} />
        </button>
      </TooltipTrigger>
      <TooltipContent side="bottom">{dark ? "Light mode" : "Dark mode"}</TooltipContent>
    </Tooltip>
  );
}

function TopBar() {
  const { pathname } = useLocation();
  return (
    <header className="flex items-center justify-between gap-6 py-6">
      <Logo />
      <nav className="flex items-center gap-2 rounded-2xl border bg-card/60 p-1.5 backdrop-blur" aria-label="Main">
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
                    "grid size-10 place-items-center rounded-xl transition-all",
                    active ? "bg-foreground text-background shadow-md" : "text-foreground hover:bg-accent",
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
      <div className="flex items-center gap-2.5">
        <span
          className={cn(
            "hidden rounded-full border px-3 py-1.5 text-[11px] lg:inline",
            API_MODE === "fixtures" ? "border-transparent bg-mistake-soft text-mistake" : "bg-secondary text-muted-foreground",
          )}
        >
          {API_MODE === "fixtures" ? "Practice data" : "Live data"} · amounts are scaled EUR
        </span>
        <ThemeToggle />
        <div className="flex items-center gap-2.5 rounded-xl border bg-secondary py-1 pr-3 pl-1">
          <span className="grid size-8 place-items-center rounded-lg bg-signal text-xs font-semibold text-[#0d0d0f]">C</span>
          <div className="leading-tight">
            <div className="text-xs font-medium">Controller</div>
            <div className="text-[11px] text-muted-foreground">Payroll · Fixed assets</div>
          </div>
        </div>
      </div>
    </header>
  );
}

/** Floating run dock (bottom): last check, live state, "Check now". Toasts come from SSE. */
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
          const why = {
            watcher: "A new workbook just landed in the inbox folder",
            schedule: "It's Monday: the weekly check is running",
            rules_change: "Your rules changed, so everything is being re-ranked",
          }[String(data.trigger)];
          toast.loading("Checking the books…", { id: "run", description: why ?? "Reading the newest workbooks" });
        } else {
          setRunning(false);
          void client.invalidateQueries();
          if (data.status === "failed") {
            toast.error("That check didn't finish", { id: "run", description: String(data.error ?? "") });
          } else {
            const found = data.counts?.exceptions;
            toast.success("All done", {
              id: "run",
              description: found !== undefined ? `${found} findings sorted by priority.` : undefined,
            });
          }
        }
      }),
    [client],
  );

  const latest = run.data;
  const busy = running || latest?.status === "running" || start.isPending;
  const open = kpis.data?.open_exceptions;
  return (
    <div className="pointer-events-none fixed inset-x-0 bottom-5 z-40 flex justify-center">
      <div className="rise pointer-events-auto flex items-center gap-3 rounded-2xl border border-white/5 bg-dock/95 p-2 pr-2.5 text-white shadow-2xl backdrop-blur" style={{ "--d": "400ms" } as React.CSSProperties}>
        <span className={cn("grid size-10 place-items-center rounded-xl", busy ? "bg-dock-raised" : "bg-signal text-[#0d0d0f]")}>
          {busy ? <Loader2 className="size-5 animate-spin text-signal" /> : <FolderInput className="size-5" />}
        </span>
        <div className="min-w-0 px-1 text-sm leading-tight">
          {busy ? (
            <div>Reading the extract and sorting findings…</div>
          ) : latest ? (
            <>
              <div className="truncate">
                Last checked {stamp(latest.finished_at ?? latest.started_at)}
                {open !== undefined && (
                  <>
                    {" · "}
                    <span className="text-signal">{open} waiting for you</span>
                  </>
                )}
              </div>
              <div className="truncate text-xs text-white/50">
                {latest.source_files.join(", ") || "no workbook"} · I watch the inbox folder and re-check every Monday at 06:00
                {latest.synthetic && " · practice data"}
              </div>
            </>
          ) : (
            <div className="text-white/70">Nothing checked yet. Drop a workbook into data/inbox, or press the button.</div>
          )}
        </div>
        <Button
          size="sm"
          variant="signal"
          className="ml-2 h-10 rounded-xl px-4 text-[#0d0d0f]"
          disabled={busy}
          onClick={() =>
            start.mutate(undefined, {
              onError: (e) => toast.error("Couldn't start a check", { description: String((e as Error).message) }),
            })
          }
        >
          <Play className="size-3.5" /> Check now
        </Button>
      </div>
    </div>
  );
}

export function AppShell() {
  const [params, setParams] = useSearchParams();
  const { pathname } = useLocation();
  const finding = params.get("finding");
  return (
    <div className="relative min-h-screen">
      <div
        aria-hidden
        className="pointer-events-none absolute inset-x-0 top-0 h-[420px] opacity-70 dark:opacity-40"
        style={{
          background:
            "radial-gradient(600px 220px at 12% 0%, var(--signal-soft), transparent 70%), radial-gradient(520px 200px at 88% 0%, var(--sentinel-soft), transparent 70%)",
        }}
      />
      <div className="relative mx-auto max-w-[1320px] px-8 pb-32">
        <TopBar />
        <main key={pathname} className="rise">
          <Outlet />
        </main>
      </div>
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
