import { useQueryClient } from "@tanstack/react-query";
import { FileUp, FolderInput, GraduationCap, Inbox, Layers, Loader2, Moon, Play, Radar, SlidersHorizontal, Sparkles, Sun } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { NavLink, Outlet, useLocation, useSearchParams } from "react-router";
import { toast } from "sonner";

import { API_MODE, api } from "@/api/client";
import { useAssistant, useKpis, useLatestRun, useStartRun, useUploadExtract } from "@/api/hooks";
import { ExceptionDrawer } from "@/components/ExceptionDrawer";
import { Button } from "@/components/ui/button";
import { Toaster } from "@/components/ui/sonner";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { useTheme } from "@/lib/theme";
import { cn, stamp } from "@/lib/utils";
import { TutorialLayer } from "@/tutorial/TutorialCard";
import { TutorialProvider, useTutorial } from "@/tutorial/TutorialProvider";

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
        <div className="mt-0.5 hidden text-[10.5px] text-muted-foreground sm:block">reconciliation copilot</div>
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
          data-tour="tour-theme"
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

/** "Tutorial": Mr. Kentaro's guided tour of every page (A39). */
function TutorialButton() {
  const tour = useTutorial();
  return (
    <button
      data-tour="tour-tutorial"
      onClick={tour.start}
      className="flex h-10 items-center gap-2 rounded-lg border bg-secondary px-3 text-sm font-medium transition hover:bg-accent"
    >
      <GraduationCap className="size-[18px] text-sentinel" />
      Tutorial
    </button>
  );
}

function TopBar() {
  const { pathname } = useLocation();
  return (
    <header className="flex flex-wrap items-center justify-between gap-x-6 gap-y-3 py-4 sm:py-6">
      <Logo />
      <nav
        data-tour="tour-nav"
        className="order-last flex w-full items-center justify-around gap-2 rounded-2xl border bg-card/60 p-1.5 backdrop-blur md:order-none md:w-auto md:justify-start"
        aria-label="Main"
      >
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
      <div className="flex items-center gap-2 sm:gap-2.5">
        <span
          className={cn(
            "hidden rounded-full border px-3 py-1.5 text-[11px] lg:inline",
            API_MODE === "fixtures" ? "border-transparent bg-mistake-soft text-mistake" : "bg-secondary text-muted-foreground",
          )}
        >
          {API_MODE === "fixtures" ? "Practice data" : "Live data"} · amounts are scaled EUR
        </span>
        <TutorialButton />
        <ThemeToggle />
        <div className="flex items-center gap-2.5 rounded-xl border bg-secondary py-1 pr-1 pl-1 lg:pr-3">
          <span className="grid size-8 place-items-center rounded-lg bg-signal text-xs font-semibold text-[#0d0d0f]">C</span>
          <div className="hidden leading-tight lg:block">
            <div className="text-xs font-medium">Controller</div>
            <div className="text-[11px] text-muted-foreground">Payroll · Fixed assets</div>
          </div>
        </div>
      </div>
    </header>
  );
}

/** Whether the assistant drafts notes (A45). Without it, notes use the standard wording. */
function AssistantStatus() {
  const assistant = useAssistant();
  const state = assistant.data;
  if (!state) return null;
  const on = state.assistant === "on";
  return (
    <div className={cn("flex min-w-0 items-center gap-1.5 truncate text-xs", on ? "text-signal" : "text-mistake")}>
      <Sparkles className="size-3 shrink-0" />
      <span className="truncate" title={state.reason ?? undefined}>
        {on ? `Assistant on (${state.model})` : "Assistant offline: notes use standard wording"}
      </span>
    </div>
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
            upload: "A new extract was uploaded",
            watcher: "A new workbook just landed in the watched folder",
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
    <div className="pointer-events-none fixed inset-x-0 bottom-3 z-40 flex justify-center px-3 sm:bottom-5">
      <div data-tour="tour-dock" className="rise pointer-events-auto flex w-full flex-wrap items-center gap-2 rounded-2xl border border-white/5 bg-dock/95 p-2 pr-2.5 text-white shadow-2xl backdrop-blur sm:w-auto sm:max-w-full sm:flex-nowrap sm:gap-3" style={{ "--d": "400ms" } as React.CSSProperties}>
        <span className={cn("grid size-10 place-items-center rounded-xl", busy ? "bg-dock-raised" : "bg-signal text-[#0d0d0f]")}>
          {busy ? <Loader2 className="size-5 animate-spin text-signal" /> : <FolderInput className="size-5" />}
        </span>
        <div className="min-w-0 flex-1 px-1 text-sm leading-tight sm:flex-initial">
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
              <AssistantStatus />
              <div className="hidden truncate text-xs text-white/50 sm:block">
                {latest.source_files.join(", ") || "no workbook"} · Upload the weekly extract or drop it in the watched folder; I re-check every Monday at 06:00
                {latest.synthetic && " · practice data"}
              </div>
            </>
          ) : (
            <div className="text-white/70">Nothing checked yet. Upload this week's extract, or press Check now.</div>
          )}
        </div>
        <div className="flex w-full gap-2 sm:contents">
          <UploadButton busy={busy} />
          <Button
            size="sm"
            variant="signal"
            className="h-10 flex-1 rounded-xl px-4 text-[#0d0d0f] sm:flex-none"
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
    </div>
  );
}

const WORKBOOK = /\.(xlsx|xlsm|xls)$/i;

/** Send one extract; refusals (wrong file, already loaded) come back as a plain message. */
function useSendExtract() {
  const upload = useUploadExtract();
  const send = (file: File) =>
    upload.mutate(file, {
      onSuccess: (result) => toast.success("Extract received", { description: result.message }),
      onError: (e) => toast.error("That file wasn't loaded", { description: String((e as Error).message) }),
    });
  return { send, pending: upload.isPending };
}

/** "Upload extract": a file picker for this week's Payroll or Fixed assets workbook (A38). */
function UploadButton({ busy }: { busy: boolean }) {
  const input = useRef<HTMLInputElement>(null);
  const { send, pending } = useSendExtract();
  return (
    <>
      <input
        ref={input}
        type="file"
        accept=".xlsx,.xlsm,.xls"
        className="hidden"
        onChange={(e) => {
          const file = e.target.files?.[0];
          e.target.value = "";
          if (file) send(file);
        }}
      />
      <Button
        size="sm"
        variant="ghost"
        className="h-10 flex-1 rounded-xl bg-dock-raised px-4 text-white hover:bg-dock-raised hover:text-white sm:ml-2 sm:flex-none sm:bg-transparent"
        disabled={busy || pending}
        onClick={() => input.current?.click()}
      >
        <FileUp className="size-3.5" /> Upload extract
      </Button>
    </>
  );
}

/** Drop a workbook anywhere on the page to upload it. */
function DropZone() {
  const [over, setOver] = useState(false);
  const { send } = useSendExtract();
  const sendRef = useRef(send);
  sendRef.current = send; // the window listeners below are added once
  useEffect(() => {
    let depth = 0;
    const hasFiles = (e: DragEvent) => Array.from(e.dataTransfer?.types ?? []).includes("Files");
    const enter = (e: DragEvent) => {
      if (!hasFiles(e)) return;
      depth += 1;
      setOver(true);
    };
    const leave = (e: DragEvent) => {
      if (!hasFiles(e)) return;
      depth = Math.max(0, depth - 1);
      if (depth === 0) setOver(false);
    };
    const overHandler = (e: DragEvent) => {
      if (hasFiles(e)) e.preventDefault();
    };
    const drop = (e: DragEvent) => {
      if (!hasFiles(e)) return;
      e.preventDefault();
      depth = 0;
      setOver(false);
      const files = Array.from(e.dataTransfer?.files ?? []);
      const workbooks = files.filter((f) => WORKBOOK.test(f.name));
      if (!workbooks.length) {
        toast.error("That file wasn't loaded", { description: "Drop a Payroll or Fixed assets workbook (.xlsx, .xlsm or .xls)." });
        return;
      }
      workbooks.forEach((file) => sendRef.current(file));
    };
    window.addEventListener("dragenter", enter);
    window.addEventListener("dragleave", leave);
    window.addEventListener("dragover", overHandler);
    window.addEventListener("drop", drop);
    return () => {
      window.removeEventListener("dragenter", enter);
      window.removeEventListener("dragleave", leave);
      window.removeEventListener("dragover", overHandler);
      window.removeEventListener("drop", drop);
    };
  }, []);
  if (!over) return null;
  return (
    <div className="pointer-events-none fixed inset-0 z-50 grid place-items-center bg-background/70 backdrop-blur-sm">
      <div className="mx-4 rounded-3xl border-2 border-dashed border-signal bg-card px-6 py-8 text-center shadow-2xl sm:px-10">
        <FileUp className="mx-auto mb-3 size-8 text-signal" />
        <div className="text-lg font-medium">Drop this week's extract to check it</div>
        <div className="mt-1 text-sm text-muted-foreground">Payroll or Fixed assets workbook. Okane keeps a copy; your file is not changed.</div>
      </div>
    </div>
  );
}

export function AppShell() {
  return (
    <TutorialProvider>
      <Shell />
    </TutorialProvider>
  );
}

function Shell() {
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
      {/* On phones the tutorial card docks at the bottom; --tour-sheet (its height) leaves room so
          the last section on a page can still scroll above it. */}
      <div className="relative mx-auto max-w-[1320px] px-4 pb-[max(10rem,var(--tour-sheet,0px))] sm:px-6 sm:pb-32 lg:px-8">
        <TopBar />
        <main key={pathname} className="rise">
          <Outlet />
        </main>
      </div>
      <RunDock />
      <DropZone />
      <ExceptionDrawer
        id={finding}
        onClose={() => {
          params.delete("finding");
          setParams(params, { replace: true });
        }}
      />
      <Toaster />
      <TutorialLayer />
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
