// The tutorial card with Mr. Kentaro (docs/ASSUMPTIONS.md A39), and the layer that puts the card,
// the blur and the highlights on top of the app. It opens on a menu (this page, a page, or the
// full tour); each card sits right next to what it explains and glides from one place to the
// next; a tutorial ends with a samurai farewell.
import { Check, ChevronLeft, ChevronRight, GraduationCap, Inbox, Layers, Radar, SlidersHorizontal, X } from "lucide-react";
import { memo, useEffect, useLayoutEffect, useMemo, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { useLocation } from "react-router";

import { cn } from "@/lib/utils";
import { Kentaro, type Pose } from "@/tutorial/Kentaro";
import { SakuraBurst } from "@/tutorial/SakuraBurst";
import { GLIDE_MS, SHEET_BELOW, Spotlight, isPinned, reducedMotion, useTargetBoxes, type Box } from "@/tutorial/Spotlight";
import {
  MODULES,
  PAGE_NAME,
  STEPS,
  moduleOf,
  moduleOfPath,
  sequence,
  type Choice,
  type ModuleId,
  type TourCtx,
} from "@/tutorial/steps";
import { useTutorial } from "@/tutorial/TutorialProvider";

const INK = "#16161d";
const GAP = 18; // between the card and what it explains
const EDGE = 16; // from the screen's edges
const DOCK = 96; // the run dock at the bottom
const DRAWER = 780; // a finding's details panel, on the right
const SHEET_EDGE = 8;
const ARMOUR_MS = 1100; // the transformation, before Kentaro vanishes
const SETTLE_MS = 120; // while the highlights keep moving (scrolling), the card waits this long
const GLIDE = `${GLIDE_MS}ms cubic-bezier(0.22, 1, 0.36, 1)`;
const MODULE_ICON: Record<ModuleId, React.ComponentType<{ className?: string }>> = {
  start: GraduationCap,
  inbox: Inbox,
  exposure: Layers,
  sentinel: Radar,
  rules: SlidersHorizontal,
};
const count = (choice: Choice) => sequence(choice).length;

type Size = { w: number; h: number };
type Spot = { left: number; top: number };

/** The highlights for placing the card. A jump (a new card) is taken at once; while they keep
 *  moving (scrolling into view, a panel sliding in) the card waits until they stop, then glides
 *  once instead of chasing them frame by frame. */
function useSettled(boxes: Box[]): Box[] {
  const [settled, setSettled] = useState<Box[]>(boxes);
  const lastChange = useRef(0);
  useEffect(() => {
    const now = performance.now();
    const moving = now - lastChange.current < SETTLE_MS;
    lastChange.current = now;
    if (!moving) {
      setSettled(boxes);
      return;
    }
    const timer = window.setTimeout(() => setSettled(boxes), SETTLE_MS);
    return () => window.clearTimeout(timer);
  }, [boxes]);
  return settled;
}

function union(boxes: Box[]): Box | null {
  if (!boxes.length) return null;
  const x = Math.min(...boxes.map((b) => b.x));
  const y = Math.min(...boxes.map((b) => b.y));
  const right = Math.max(...boxes.map((b) => b.x + b.w));
  const bottom = Math.max(...boxes.map((b) => b.y + b.h));
  // Only the part on screen counts (a long table or log may run off it).
  const top = Math.max(y, 0);
  const end = Math.min(bottom, window.innerHeight);
  if (end - top < 1) return null; // not on screen yet (still scrolling into view)
  return { x, y: top, w: right - x, h: end - top };
}

/** True when every highlighted section sits in a part of the page fixed to the screen. */
function pinnedTargets(keys: string[]): boolean {
  if (!keys.length) return false;
  return keys.every((key) => Array.from(document.querySelectorAll(`[data-tour~="${key}"]`)).some(isPinned));
}

/** Right next to the highlights: below, above, right or left, whichever fits first. Null while
 *  the highlights are off screen: the card then stays where it is. `pinned`: the highlights are
 *  fixed to the screen (the run dock), so scrolling cannot move them out from under the card. */
export function placeNear(boxes: Box[], card: Size, drawerOpen: boolean, pinned = false): Spot | null {
  const W = window.innerWidth;
  const H = window.innerHeight;
  const { w, h } = card;
  const clampX = (x: number) => Math.min(Math.max(x, EDGE), Math.max(EDGE, W - w - EDGE));
  const clampY = (y: number) => Math.min(Math.max(y, EDGE), Math.max(EDGE, H - h - DOCK));
  // Phones: docked at the bottom; the highlight is scrolled above it (Spotlight). A highlight fixed
  // to the bottom of the screen (the run dock) cannot be scrolled, so the card docks at the top.
  if (W < SHEET_BELOW) {
    const sheet = { left: SHEET_EDGE, top: Math.max(SHEET_EDGE, H - h - SHEET_EDGE) };
    const u = pinned ? union(boxes) : null;
    if (u && u.y + u.h > sheet.top && u.y >= h + 2 * SHEET_EDGE) return { left: SHEET_EDGE, top: SHEET_EDGE };
    return sheet;
  }
  if (!boxes.length) return { left: clampX((W - w) / 2), top: clampY((H - h) / 2) };
  const u = union(boxes);
  if (!u) return null;
  const middle = u.y + u.h / 2;

  if (drawerOpen) {
    const edge = W - Math.min(DRAWER, W);
    return { left: clampX(edge - w - 6), top: clampY(middle - h / 2) };
  }
  const below = u.y + u.h + GAP;
  if (below >= EDGE && below + h <= H - DOCK) return { left: clampX(u.x), top: below };
  const above = u.y - GAP - h;
  if (above >= EDGE && above + h <= H - DOCK) return { left: clampX(u.x), top: above };
  const right = u.x + u.w + GAP;
  if (right + w <= W - EDGE) return { left: right, top: clampY(middle - h / 2) };
  const left = u.x - GAP - w;
  if (left >= EDGE) return { left, top: clampY(middle - h / 2) };
  // Too big to sit beside: over its roomier side, level with its middle, clear of its heading.
  const roomRight = W - (u.x + u.w) >= u.x;
  return { left: roomRight ? clampX(W - w - EDGE) : EDGE, top: clampY(Math.max(middle - h / 2, u.y + 64)) };
}

function Arrow({ side, disabled, onClick, label }: { side: "left" | "right"; disabled?: boolean; onClick: () => void; label: string }) {
  const Icon = side === "left" ? ChevronLeft : ChevronRight;
  return (
    <button
      onClick={onClick}
      disabled={disabled}
      aria-label={label}
      className={cn(
        "absolute top-1/2 hidden size-11 -translate-y-1/2 place-items-center rounded-full text-white shadow-lg ring-4 ring-white/70 transition hover:scale-110 disabled:pointer-events-none disabled:opacity-30 sm:grid",
        side === "left" ? "-left-5" : "-right-5",
      )}
      style={{ background: INK }}
    >
      <Icon className="size-5" />
    </button>
  );
}

/** On phones the arrows sit in the card's bottom row instead of on its sides (no room there). */
function PhoneArrow({ side, onClick, label }: { side: "left" | "right"; onClick: () => void; label: string }) {
  const Icon = side === "left" ? ChevronLeft : ChevronRight;
  return (
    <button
      onClick={onClick}
      aria-label={label}
      className="grid size-10 shrink-0 place-items-center rounded-full text-white shadow-md sm:hidden"
      style={{ background: INK }}
    >
      <Icon className="size-5" />
    </button>
  );
}

/** Mr. Kentaro is only redrawn when his pose or armour changes, not while the card glides. */
const Guide = memo(function Guide({ pose, armoured }: { pose: Pose; armoured: boolean }) {
  return <Kentaro pose={pose} armoured={armoured} className="h-auto w-14 sm:w-[104px]" />;
});

/** A card's words, built once per card (not on every frame of a glide). */
const CardBody = memo(function CardBody({ stepId, ctx }: { stepId: number; ctx: TourCtx }) {
  const step = STEPS[stepId];
  const start = moduleOf(step) === "start";
  return (
    <>
      <div className="flex items-center gap-2 text-[11px] font-semibold tracking-wide uppercase opacity-70">
        <span>{start ? "Getting started" : PAGE_NAME[step.page]}</span>
        <span>·</span>
        <span>{step.example ? "Example" : "Mr. Kentaro explains"}</span>
      </div>
      <h2 id="tour-title" className="mt-1 pr-6 text-lg leading-snug font-semibold">
        {step.title}
      </h2>
      <div className="mt-1.5 text-[14.5px] leading-relaxed">{step.body(ctx)}</div>
    </>
  );
});

/** The first card: which tutorial? This page, a page of your choice, or everything. */
function TourMenu() {
  const tour = useTutorial();
  const { pathname } = useLocation();
  const here = moduleOfPath(pathname);
  const hereName = MODULES.find((m) => m.id === here)!.name;
  const tick = (choice: Choice) => (tour.done.has(choice) ? <Check className="size-3.5" aria-label="done" /> : null);
  return (
    <>
      <div className="text-[11px] font-semibold tracking-wide uppercase opacity-70">Tutorial · pick one</div>
      <h2 id="tour-title" className="mt-1 pr-6 text-lg leading-snug font-semibold">
        What would you like to learn?
      </h2>
      <div className="mt-3 space-y-2.5">
        <button
          data-autofocus
          onClick={() => tour.choose(here)}
          className="flex w-full flex-wrap items-center justify-between gap-x-3 gap-y-1 rounded-2xl px-4 py-3 text-left text-white transition hover:scale-[1.01] focus-visible:ring-4 focus-visible:ring-white/70 focus-visible:outline-none"
          style={{ background: INK }}
        >
          <span>
            <span className="block text-[15px] font-semibold">This page: {hereName}</span>
            <span className="block text-xs opacity-75">{MODULES.find((m) => m.id === here)!.about}</span>
          </span>
          <span className="flex shrink-0 items-center gap-1.5 text-xs opacity-80">
            {tick(here)}
            {count(here)} cards
          </span>
        </button>
        <div>
          <div className="mb-1.5 text-xs font-semibold">Or pick a page</div>
          <div className="flex flex-wrap gap-1.5">
            {MODULES.map((m) => {
              const Icon = MODULE_ICON[m.id];
              return (
                <button
                  key={m.id}
                  onClick={() => tour.choose(m.id)}
                  title={m.about}
                  className="flex items-center gap-1.5 rounded-full border border-black/20 bg-white/45 px-3 py-1.5 text-[13px] font-medium transition hover:bg-white/80 focus-visible:ring-2 focus-visible:ring-black/60 focus-visible:outline-none"
                >
                  <Icon className="size-3.5" />
                  {m.name}
                  <span className="opacity-60">{count(m.id)}</span>
                  {tick(m.id)}
                </button>
              );
            })}
          </div>
        </div>
        <button
          onClick={() => tour.choose("full")}
          className="flex w-full flex-wrap items-center justify-between gap-x-3 gap-y-1 rounded-2xl border-2 border-black/25 px-4 py-2.5 text-left transition hover:bg-white/40 focus-visible:ring-2 focus-visible:ring-black/60 focus-visible:outline-none"
        >
          <span>
            <span className="block text-[15px] font-semibold">The full tour</span>
            <span className="block text-xs opacity-75">Every page, one after another</span>
          </span>
          <span className="flex shrink-0 items-center gap-1.5 text-xs opacity-80">
            {tick("full")}
            {count("full")} cards · about 8 minutes
          </span>
        </button>
      </div>
    </>
  );
}

export function TutorialLayer() {
  const tour = useTutorial();
  const { active, step, index, total, ctx, color, phase, stepId, choice } = tour;
  const menu = phase === "menu";
  const finale = phase === "finale";
  const keys = active && !menu ? (typeof step.targets === "function" ? step.targets(ctx) : (step.targets ?? [])) : [];
  const stepKey = active ? stepId : -2;
  // The height the docked card covers on phones, for scrolling the highlights clear of it.
  const sheet = useRef(0);
  const targets = useTargetBoxes(keys, stepKey, sheet);
  const settled = useSettled(targets);
  // Checked again only when the highlights settle, not on every frame of a scroll.
  const pinned = useMemo(
    () => !menu && window.innerWidth < SHEET_BELOW && pinnedTargets(keys),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [menu, keys.join("|"), settled],
  );
  const card = useRef<HTMLDivElement>(null);
  const kentaro = useRef<HTMLDivElement>(null);
  const [size, setSize] = useState<Size>({ w: 600, h: 220 });
  const [vanish, setVanish] = useState<{ x: number; y: number } | null>(null);
  const lastSpot = useRef<Spot | null>(null);

  // Keep the card's real size, so it can be placed right next to its highlights. On phones the
  // page also gets that much room at its end (--tour-sheet, AppShell), so the last section on a
  // page can still scroll above the docked card.
  useLayoutEffect(() => {
    const el = card.current;
    if (!el) return;
    const root = document.documentElement;
    const measure = () => {
      setSize({ w: el.offsetWidth, h: el.offsetHeight });
      sheet.current = el.offsetHeight + SHEET_EDGE + 16;
      root.style.setProperty("--tour-sheet", `${sheet.current}px`);
    };
    measure();
    const observer = new ResizeObserver(measure);
    observer.observe(el);
    return () => {
      observer.disconnect();
      root.style.removeProperty("--tour-sheet");
    };
  }, [active]);

  // Focus the card (or, in the menu, its suggested choice) so the keys work straight away.
  useEffect(() => {
    if (!active || finale) return;
    const first = menu ? card.current?.querySelector<HTMLElement>("[data-autofocus]") : null;
    (first ?? card.current)?.focus({ preventScroll: true });
  }, [active, index, finale, menu]);

  // The farewell: armour first, then Kentaro vanishes in a burst of cherry blossoms.
  useEffect(() => {
    if (!finale) {
      setVanish(null);
      return;
    }
    const timer = window.setTimeout(() => {
      const r = kentaro.current?.getBoundingClientRect();
      if (r) setVanish({ x: r.left + r.width / 2, y: r.top + r.height / 2 });
    }, ARMOUR_MS);
    return () => window.clearTimeout(timer);
  }, [finale]);

  if (!active) return null;
  const last = index === total - 1;
  const moduleEnd = last && choice !== "full";
  const name = choice === "full" ? "Full tour" : `${MODULES.find((m) => m.id === choice)!.name} tutorial`;
  const spot = placeNear(menu ? [] : settled, size, !menu && !!step.finding, pinned) ?? lastSpot.current ?? placeNear([], size, false)!;
  lastSpot.current = spot;
  const still = reducedMotion();
  return createPortal(
    <>
      <Spotlight target={menu ? [] : targets} stepId={stepKey} leaving={!!vanish} />
      {/* The outer box only moves (a compositor-only transform); the card inside fades in and out. */}
      <div
        className="fixed top-0 left-0 z-[63]"
        style={{
          transform: `translate3d(${spot.left}px, ${spot.top}px, 0)`,
          transition: still ? undefined : `transform ${GLIDE}`,
          willChange: "transform",
          pointerEvents: "none",
        }}
      >
        <div
          ref={card}
          data-tutorial-layer
          data-tutorial-card
          role="dialog"
          aria-modal="true"
          aria-labelledby="tour-title"
          tabIndex={-1}
          className={cn(
            "relative w-[calc(100vw-16px)] rounded-3xl px-4 pt-4 pb-3 shadow-2xl outline-none sm:w-[min(600px,calc(100vw-48px))] sm:px-9 sm:pt-5 sm:pb-4",
            vanish ? "tour-card-out" : "tour-card-in",
          )}
          style={{ background: color, color: INK, pointerEvents: "auto", transition: still ? undefined : `background-color ${GLIDE}` }}
        >
          <button
            onClick={tour.stop}
            aria-label="Leave the tutorial"
            className="absolute top-3 right-3 grid size-8 place-items-center rounded-full transition hover:bg-black/10"
          >
            <X className="size-4" />
          </button>
          {phase === "tour" && (
            <>
              <Arrow side="left" label={index === 0 ? "Back to the tutorial menu" : "Previous card"} onClick={tour.prev} />
              <Arrow side="right" label={last ? "Finish the tutorial" : "Next card"} onClick={tour.next} />
            </>
          )}

          <div className="grid grid-cols-[56px_1fr] items-start gap-3 sm:grid-cols-[104px_1fr] sm:items-center sm:gap-4">
            <div ref={kentaro} className={vanish ? "kentaro-vanish" : "kentaro-bob"}>
              <Guide pose={menu ? "wave" : (step.pose ?? "point")} armoured={finale} />
            </div>
            <div
              key={menu ? "menu" : finale ? "finale" : stepId}
              className={cn(
                "tour-content-in min-w-0 overflow-y-auto overscroll-contain sm:max-h-none sm:overflow-visible",
                menu ? "max-h-[72vh]" : "max-h-[46vh]",
              )}
            >
              {menu ? (
                <TourMenu />
              ) : finale ? (
                <>
                  <div className="flex items-center gap-2 text-[11px] font-semibold tracking-wide uppercase opacity-70">
                    <span>Farewell</span>
                    <span>·</span>
                    <span>Mr. Kentaro suits up</span>
                  </div>
                  <h2 id="tour-title" className="mt-1 pr-6 text-lg leading-snug font-semibold">
                    Sayōnara!
                  </h2>
                  <div className="mt-1.5 text-[14.5px] leading-relaxed">
                    Your books are in good hands. Mr. Kentaro is off to guard the next close!
                  </div>
                </>
              ) : (
                <CardBody stepId={stepId} ctx={ctx} />
              )}
            </div>
          </div>

          <div className="mt-3 flex items-center gap-2 text-xs sm:mt-4 sm:gap-3">
            {menu ? (
              <span className="opacity-70">Tab and Enter to choose · Esc to leave</span>
            ) : (
              <>
                {phase === "tour" && (
                  <PhoneArrow side="left" label={index === 0 ? "Back to the tutorial menu" : "Previous card"} onClick={tour.prev} />
                )}
                <div className="h-1.5 min-w-0 flex-1 overflow-hidden rounded-full bg-black/15">
                  <div
                    className="h-full rounded-full transition-all duration-500"
                    style={{ width: finale ? "100%" : `${((index + 1) / total) * 100}%`, background: INK }}
                  />
                </div>
                <span className="num font-medium whitespace-nowrap">
                  {index + 1} / {total}
                  <span className="hidden sm:inline"> · {name}</span>
                </span>
                {phase === "tour" && !last && <span className="hidden opacity-70 lg:inline">← → · Esc</span>}
                {phase === "tour" && !last && <PhoneArrow side="right" label="Next card" onClick={tour.next} />}
                {phase === "tour" && moduleEnd && (
                  <button onClick={tour.toMenu} className="rounded-full border border-black/30 px-3 py-1 font-semibold whitespace-nowrap hover:bg-white/40">
                    Another tutorial
                  </button>
                )}
                {phase === "tour" && last && (
                  <button onClick={tour.next} className="rounded-full px-3 py-1 font-semibold text-white" style={{ background: INK }}>
                    Finish
                  </button>
                )}
              </>
            )}
          </div>
        </div>
      </div>
      {vanish && !still && <SakuraBurst x={vanish.x} y={vanish.y} />}
    </>,
    document.body,
  );
}
