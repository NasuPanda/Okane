// The tutorial card with Mr. Kentaro (docs/ASSUMPTIONS.md A39), and the layer that puts the card,
// the blur and the highlights on top of the app. The card sits right next to what it explains
// and glides from one card's place to the next; the last card ends with a samurai farewell.
import { ChevronLeft, ChevronRight, X } from "lucide-react";
import { useEffect, useLayoutEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";

import { cn } from "@/lib/utils";
import { Kentaro } from "@/tutorial/Kentaro";
import { SakuraBurst } from "@/tutorial/SakuraBurst";
import { GLIDE_MS, Spotlight, reducedMotion, useTargetBoxes, useTweenedBoxes, type Box } from "@/tutorial/Spotlight";
import { PAGE_NAME } from "@/tutorial/steps";
import { useTutorial } from "@/tutorial/TutorialProvider";

const INK = "#16161d";
const GAP = 18; // between the card and what it explains
const EDGE = 16; // from the screen's edges
const DOCK = 96; // the run dock at the bottom
const DRAWER = 780; // a finding's details panel, on the right
const ARMOUR_MS = 1100; // the transformation, before Kentaro vanishes
const GLIDE = `${GLIDE_MS}ms cubic-bezier(0.22, 1, 0.36, 1)`;

const SETTLE_MS = 150; // the card moves once the highlights stop moving

type Size = { w: number; h: number };

/** The highlights once they've stopped moving (scrolling into view, a panel sliding in), so the
 *  card glides once to its final place instead of chasing them frame by frame. */
function useSettled(boxes: Box[]): Box[] {
  const [settled, setSettled] = useState<Box[]>(boxes);
  useEffect(() => {
    const timer = window.setTimeout(() => setSettled(boxes), SETTLE_MS);
    return () => window.clearTimeout(timer);
  }, [boxes]);
  return settled;
}
type Spot = { left: number; top: number };

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

/** Right next to the highlights: below, above, right or left, whichever fits first. Null while
 *  the highlights are off screen: the card then stays where it is. */
export function placeNear(boxes: Box[], card: Size, drawerOpen: boolean): Spot | null {
  const W = window.innerWidth;
  const H = window.innerHeight;
  const { w, h } = card;
  const clampX = (x: number) => Math.min(Math.max(x, EDGE), Math.max(EDGE, W - w - EDGE));
  const clampY = (y: number) => Math.min(Math.max(y, EDGE), Math.max(EDGE, H - h - DOCK));
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
        "absolute top-1/2 grid size-11 -translate-y-1/2 place-items-center rounded-full text-white shadow-lg ring-4 ring-white/70 transition hover:scale-110 disabled:pointer-events-none disabled:opacity-30",
        side === "left" ? "-left-5" : "-right-5",
      )}
      style={{ background: INK }}
    >
      <Icon className="size-5" />
    </button>
  );
}

export function TutorialLayer() {
  const tour = useTutorial();
  const { active, step, index, total, ctx, color, phase } = tour;
  const keys = active ? (typeof step.targets === "function" ? step.targets(ctx) : (step.targets ?? [])) : [];
  const targets = useTargetBoxes(keys, active ? index : -1);
  const boxes = useTweenedBoxes(targets, active ? index : -1);
  const settled = useSettled(targets);
  const card = useRef<HTMLDivElement>(null);
  const kentaro = useRef<HTMLDivElement>(null);
  const [size, setSize] = useState<Size>({ w: 600, h: 220 });
  const [vanish, setVanish] = useState<{ x: number; y: number } | null>(null);
  const lastSpot = useRef<Spot | null>(null);
  const finale = phase === "finale";

  // Keep the card's real size, so it can be placed right next to its highlights.
  useLayoutEffect(() => {
    const el = card.current;
    if (!el) return;
    const measure = () => setSize({ w: el.offsetWidth, h: el.offsetHeight });
    measure();
    const observer = new ResizeObserver(measure);
    observer.observe(el);
    return () => observer.disconnect();
  }, [active]);

  useEffect(() => {
    if (active && !finale) card.current?.focus({ preventScroll: true });
  }, [active, index, finale]);

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
  const spot = placeNear(settled, size, !!step.finding) ?? lastSpot.current ?? placeNear([], size, false)!;
  lastSpot.current = spot;
  const still = reducedMotion();
  return createPortal(
    <>
      <Spotlight boxes={boxes} leaving={!!vanish} />
      <div
        ref={card}
        data-tutorial-layer
        data-tutorial-card
        role="dialog"
        aria-modal="true"
        aria-labelledby="tour-title"
        tabIndex={-1}
        className={cn(
          "fixed z-[63] w-[min(600px,calc(100vw-48px))] rounded-3xl px-9 pt-5 pb-4 shadow-2xl outline-none",
          vanish ? "tour-card-out" : "tour-card-in",
        )}
        style={{
          left: spot.left,
          top: spot.top,
          background: color,
          color: INK,
          pointerEvents: "auto",
          transition: still ? undefined : `left ${GLIDE}, top ${GLIDE}, background-color ${GLIDE}`,
        }}
      >
        <button
          onClick={tour.stop}
          aria-label="Leave the tutorial"
          className="absolute top-3 right-3 grid size-8 place-items-center rounded-full transition hover:bg-black/10"
        >
          <X className="size-4" />
        </button>
        {!finale && (
          <>
            <Arrow side="left" label="Previous card" disabled={index === 0} onClick={tour.prev} />
            <Arrow side="right" label={last ? "Finish the tutorial" : "Next card"} onClick={tour.next} />
          </>
        )}

        <div className="grid grid-cols-[104px_1fr] items-center gap-4">
          <div ref={kentaro} className={vanish ? "kentaro-vanish" : "kentaro-bob"}>
            <Kentaro pose={step.pose ?? "point"} armoured={finale} className="h-auto w-[104px]" />
          </div>
          <div key={finale ? "finale" : index} className="tour-content-in min-w-0">
            <div className="flex items-center gap-2 text-[11px] font-semibold tracking-wide uppercase opacity-70">
              <span>{finale ? "Farewell" : PAGE_NAME[step.page]}</span>
              <span>·</span>
              <span>{finale ? "Mr. Kentaro suits up" : step.example ? "Example" : "Mr. Kentaro explains"}</span>
            </div>
            <h2 id="tour-title" className="mt-1 pr-6 text-lg leading-snug font-semibold">
              {finale ? "Sayōnara!" : step.title}
            </h2>
            <div className="mt-1.5 text-[14.5px] leading-relaxed">
              {finale ? "Your books are in good hands. Mr. Kentaro is off to guard the next close!" : step.body(ctx)}
            </div>
          </div>
        </div>

        <div className="mt-4 flex items-center gap-3 text-xs">
          <div className="h-1.5 flex-1 overflow-hidden rounded-full bg-black/15">
            <div
              className="h-full rounded-full transition-all duration-500"
              style={{ width: finale ? "100%" : `${((index + 1) / total) * 100}%`, background: INK }}
            />
          </div>
          <span className="num font-medium">
            {index + 1} / {total}
          </span>
          {!finale && <span className="hidden opacity-70 sm:inline">← → to move · Esc to leave</span>}
          {last && !finale && (
            <button onClick={tour.next} className="rounded-full px-3 py-1 font-semibold text-white" style={{ background: INK }}>
              Finish
            </button>
          )}
        </div>
      </div>
      {vanish && !still && <SakuraBurst x={vanish.x} y={vanish.y} />}
    </>,
    document.body,
  );
}
