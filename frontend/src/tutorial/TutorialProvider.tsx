// Tutorial mode state (docs/ASSUMPTIONS.md A39): the menu (which tutorial), the chosen cards, the
// card showing, its page and the finding it opens. The tour only navigates and reads; it never
// calls an API that writes.
import { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";
import { useLocation, useNavigate } from "react-router";

import { useExceptions, useExposure, useKpis, useLatestRun, useRules } from "@/api/hooks";
import { STEPS, sequence, type Choice, type Step, type TourCtx, type TourPage } from "@/tutorial/steps";

// Vibrant card colours with dark text. Each tutorial session shuffles them, one per page.
const PALETTE = ["#ff8a80", "#ffb74d", "#ffe066", "#9be15d", "#5ee6c4", "#7cc4ff", "#b69cff", "#ff8fc4", "#c6f560"];
const PAGES: TourPage[] = ["/", "/exposure", "/sentinel", "/rules"];
/** How long the farewell runs: armour (about 1.1s), then the vanish and the cherry blossoms. */
export const FINALE_MS = 3400;

/** "menu": which tutorial? "tour": a card. "finale": Mr. Kentaro's farewell. */
export type Phase = "menu" | "tour" | "finale";

type TutorialState = {
  active: boolean;
  phase: Phase;
  choice: Choice;
  /** Position within the chosen tutorial, and its number of cards. */
  index: number;
  total: number;
  /** The card's position in STEPS (stable across tutorials), or -1 in the menu. */
  stepId: number;
  step: Step;
  ctx: TourCtx;
  color: string;
  done: Set<Choice>;
  start: () => void;
  stop: () => void;
  next: () => void;
  prev: () => void;
  choose: (choice: Choice) => void;
  toMenu: () => void;
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
  const [phase, setPhase] = useState<Phase>("menu");
  const [choice, setChoice] = useState<Choice>("full");
  const [seq, setSeq] = useState<number[]>(() => sequence("full"));
  const [pos, setPos] = useState(0);
  const [done, setDone] = useState<Set<Choice>>(new Set());
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

  const menu = phase === "menu";
  const stepId = menu ? -1 : (seq[pos] ?? 0);
  const step = STEPS[Math.max(stepId, 0)];
  const wantFinding = active && !menu ? (step.finding?.(ctx) ?? null) : null;

  const start = useCallback(() => {
    const picks = shuffled(PALETTE);
    setColors(Object.fromEntries(PAGES.map((p, i) => [p, picks[i]])));
    setDone(new Set());
    setPhase("menu");
    setActive(true);
  }, []);

  const stop = useCallback(() => {
    setActive(false);
    setPhase("menu");
    // Close a finding the tour opened; leave the page where it is.
    const params = new URLSearchParams(location.search);
    if (params.has("finding")) {
      params.delete("finding");
      const search = params.toString();
      navigate({ pathname: location.pathname, search: search ? `?${search}` : "" }, { replace: true });
    }
  }, [location.pathname, location.search, navigate]);

  const choose = useCallback((picked: Choice) => {
    setChoice(picked);
    setSeq(sequence(picked));
    setPos(0);
    setPhase("tour");
  }, []);
  const toMenu = useCallback(() => setPhase("menu"), []);

  // Reaching the last card of a tutorial ticks it in the menu.
  useEffect(() => {
    if (phase === "tour" && pos === seq.length - 1) setDone((d) => (d.has(choice) ? d : new Set(d).add(choice)));
  }, [phase, pos, seq.length, choice]);

  // → past the last card plays the farewell: Mr. Kentaro suits up and vanishes in blossoms.
  const next = useCallback(() => {
    if (phase !== "tour") return;
    if (pos >= seq.length - 1) setPhase("finale");
    else setPos(pos + 1);
  }, [phase, pos, seq.length]);
  // ← on the first card goes back to the menu.
  const prev = useCallback(() => {
    if (phase !== "tour") return;
    if (pos === 0) setPhase("menu");
    else setPos(pos - 1);
  }, [phase, pos]);

  useEffect(() => {
    if (phase !== "finale") return;
    const timer = window.setTimeout(stop, FINALE_MS);
    return () => window.clearTimeout(timer);
  }, [phase, stop]);

  // Go to the card's page, with its finding open or closed (both are only URL changes). The
  // menu stays on the page in view and closes any finding the tour opened.
  useEffect(() => {
    if (!active) return;
    const params = new URLSearchParams(location.search);
    if (menu) {
      if (!params.has("finding")) return;
      params.delete("finding");
      const search = params.toString();
      navigate({ pathname: location.pathname, search: search ? `?${search}` : "" }, { replace: true });
      return;
    }
    const onPage = location.pathname === step.page;
    if (onPage && params.get("finding") === wantFinding) return;
    if (!onPage) params.delete("view");
    if (wantFinding) params.set("finding", wantFinding);
    else params.delete("finding");
    const search = params.toString();
    navigate({ pathname: step.page, search: search ? `?${search}` : "" }, { replace: true });
  }, [active, menu, step.page, wantFinding, location.pathname, location.search, navigate]);

  // Keys: arrows move, Esc leaves. While the tour runs nothing on the page can be typed into or
  // pressed from the keyboard either (only the card's own buttons, Tab and scrolling keys pass),
  // so no data can change.
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

  const page = menu ? (PAGES.find((p) => p !== "/" && location.pathname.startsWith(p)) ?? "/") : step.page;
  const value: TutorialState = {
    active,
    phase,
    choice,
    index: pos,
    total: seq.length,
    stepId,
    step,
    ctx,
    color: colors[page] ?? PALETTE[0],
    done,
    start,
    stop,
    next,
    prev,
    choose,
    toMenu,
  };
  return <TutorialContext.Provider value={value}>{children}</TutorialContext.Provider>;
}

export function useTutorial(): TutorialState {
  const state = useContext(TutorialContext);
  if (!state) throw new Error("useTutorial needs a TutorialProvider");
  return state;
}
