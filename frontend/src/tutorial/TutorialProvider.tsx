// Tutorial mode state (docs/ASSUMPTIONS.md A39): which card is showing, the page it belongs to,
// and the finding it opens. The tour only navigates and reads; it never calls an API that writes.
import { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";
import { useLocation, useNavigate } from "react-router";

import { useExceptions, useExposure, useKpis, useLatestRun, useRules } from "@/api/hooks";
import { STEPS, type Step, type TourCtx, type TourPage } from "@/tutorial/steps";

// Vibrant card colours with dark text. Each tour shuffles them, one per page.
const PALETTE = ["#ff8a80", "#ffb74d", "#ffe066", "#9be15d", "#5ee6c4", "#7cc4ff", "#b69cff", "#ff8fc4", "#c6f560"];
const PAGES: TourPage[] = ["/", "/exposure", "/sentinel", "/rules"];
/** How long the farewell runs: armour (about 1.1s), then the vanish and the cherry blossoms. */
export const FINALE_MS = 3400;

export type Phase = "tour" | "finale";

type TutorialState = {
  active: boolean;
  phase: Phase;
  index: number;
  total: number;
  step: Step;
  ctx: TourCtx;
  color: string;
  start: () => void;
  stop: () => void;
  next: () => void;
  prev: () => void;
};

const TutorialContext = createContext<TutorialState | null>(null);

function shuffled<T>(items: T[]): T[] {
  const out = [...items];
  for (let i = out.length - 1; i > 0; i--) {
    const j = Math.floor(Math.random() * (i + 1));
    [out[i], out[j]] = [out[j], out[i]];
  }
  return out;
}

export function TutorialProvider({ children }: { children: React.ReactNode }) {
  const [active, setActive] = useState(false);
  const [index, setIndex] = useState(0);
  const [phase, setPhase] = useState<Phase>("tour");
  const [colors, setColors] = useState<Record<string, string>>({});
  const navigate = useNavigate();
  const location = useLocation();

  const exceptions = useExceptions();
  const kpis = useKpis();
  const rules = useRules();
  const exposure = useExposure();
  const run = useLatestRun();
  const ctx = useMemo<TourCtx>(
    () => ({ records: exceptions.data ?? [], kpis: kpis.data, rules: rules.data, exposure: exposure.data, run: run.data }),
    [exceptions.data, kpis.data, rules.data, exposure.data, run.data],
  );

  const step = STEPS[index];
  const wantFinding = active ? (step.finding?.(ctx) ?? null) : null;

  const start = useCallback(() => {
    const picks = shuffled(PALETTE);
    setColors(Object.fromEntries(PAGES.map((p, i) => [p, picks[i]])));
    setIndex(0);
    setPhase("tour");
    setActive(true);
  }, []);

  const stop = useCallback(() => {
    setActive(false);
    setPhase("tour");
    // Close a finding the tour opened; leave the page where it is.
    const params = new URLSearchParams(location.search);
    if (params.has("finding")) {
      params.delete("finding");
      const search = params.toString();
      navigate({ pathname: location.pathname, search: search ? `?${search}` : "" }, { replace: true });
    }
  }, [location.pathname, location.search, navigate]);

  // The last card's "next" plays the farewell: Mr. Kentaro suits up and vanishes in blossoms.
  const next = useCallback(() => {
    if (phase === "finale") return;
    if (index >= STEPS.length - 1) setPhase("finale");
    else setIndex(index + 1);
  }, [index, phase]);
  const prev = useCallback(() => {
    if (phase !== "finale") setIndex((i) => Math.max(0, i - 1));
  }, [phase]);

  useEffect(() => {
    if (phase !== "finale") return;
    const timer = window.setTimeout(stop, FINALE_MS);
    return () => window.clearTimeout(timer);
  }, [phase, stop]);

  // Go to the card's page, with its finding open or closed (both are only URL changes).
  useEffect(() => {
    if (!active) return;
    const params = new URLSearchParams(location.search);
    const onPage = location.pathname === step.page;
    if (onPage && params.get("finding") === wantFinding) return;
    if (!onPage) params.delete("view");
    if (wantFinding) params.set("finding", wantFinding);
    else params.delete("finding");
    const search = params.toString();
    navigate({ pathname: step.page, search: search ? `?${search}` : "" }, { replace: true });
  }, [active, step.page, wantFinding, location.pathname, location.search, navigate]);

  // Keys: arrows move, Esc leaves. While the tour runs nothing on the page can be typed into or
  // pressed from the keyboard either (only Tab and scrolling keys pass), so no data can change.
  useEffect(() => {
    if (!active) return;
    const onKey = (e: KeyboardEvent) => {
      const target = e.target as HTMLElement | null;
      const inCard = !!target?.closest?.("[data-tutorial-card]");
      const own = { ArrowRight: next, ArrowLeft: prev, Escape: stop }[e.key];
      if (own) {
        e.preventDefault();
        e.stopPropagation();
        own();
        return;
      }
      if (inCard || e.key === "Tab" || ["PageUp", "PageDown", "Home", "End"].includes(e.key)) return;
      const onBody = !target || target === document.body || target === document.documentElement;
      if (onBody && (e.key === "ArrowUp" || e.key === "ArrowDown")) return;
      e.preventDefault();
      e.stopPropagation();
    };
    window.addEventListener("keydown", onKey, true);
    return () => window.removeEventListener("keydown", onKey, true);
  }, [active, next, prev, stop]);

  const value: TutorialState = {
    active,
    phase,
    index,
    total: STEPS.length,
    step,
    ctx,
    color: colors[step.page] ?? PALETTE[0],
    start,
    stop,
    next,
    prev,
  };
  return <TutorialContext.Provider value={value}>{children}</TutorialContext.Provider>;
}

export function useTutorial(): TutorialState {
  const state = useContext(TutorialContext);
  if (!state) throw new Error("useTutorial needs a TutorialProvider");
  return state;
}
