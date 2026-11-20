// The focus effect (docs/ASSUMPTIONS.md A39): the page is softly blurred except for the sections a
// card explains, which get a glowing ring. A transparent layer on top takes every click, so
// nothing on the page can be pressed during the tour; the mouse wheel still scrolls.
import { useEffect, useRef, useState } from "react";

export type Box = { x: number; y: number; w: number; h: number };

const PAD = 8;
const RADIUS = 14;

export const reducedMotion = () => window.matchMedia?.("(prefers-reduced-motion: reduce)").matches ?? false;
/** The glide between cards: a soft ease-out, shared with the card's CSS transition. */
export const GLIDE_MS = 350;
/** Narrower than this (phones), the card docks at the top or bottom of the screen like a sheet. */
export const SHEET_BELOW = 640;
/** Rings drawn at most (a card highlights a few sections; touching ones merge into one). */
const RING_POOL = 8;
const easeOut = (t: number) => 1 - Math.pow(1 - t, 3);

const overlaps = (a: Box, b: Box) => a.x < b.x + b.w && b.x < a.x + a.w && a.y < b.y + b.h && b.y < a.y + a.h;

/** Merge boxes that touch or overlap (fields side by side, a section inside another), so the
 *  holes never cross each other, which would blur the overlap again, and a group gets one ring. */
function merge(input: Box[]): Box[] {
  const boxes = [...input];
  for (let i = 0; i < boxes.length; i++) {
    for (let j = i + 1; j < boxes.length; j++) {
      if (!overlaps(boxes[i], boxes[j])) continue;
      const a = boxes[i];
      const b = boxes[j];
      const x = Math.min(a.x, b.x);
      const y = Math.min(a.y, b.y);
      boxes[i] = { x, y, w: Math.max(a.x + a.w, b.x + b.w) - x, h: Math.max(a.y + a.h, b.y + b.h) - y };
      boxes.splice(j, 1);
      j = i; // the grown box may now overlap one checked before
    }
  }
  return boxes;
}

/** True when the element sits in a part of the page fixed to the screen (the run dock), which
 *  scrolling cannot move. */
export function isPinned(el: Element): boolean {
  for (let node: Element | null = el; node && node !== document.body; node = node.parentElement) {
    if (getComputedStyle(node).position === "fixed") return true;
  }
  return false;
}

/** Where the highlighted sections are, kept up to date while the page scrolls and animates.
 *  On a new card the previous boxes stay until the new sections are found (another page may
 *  still be loading), so the highlight glides instead of blinking out. On phones `sheet` holds
 *  the height the docked card covers at the bottom of the screen, so the sections are scrolled
 *  clear of it. */
export function useTargetBoxes(keys: string[], stepId: number, sheet?: { current: number }): Box[] {
  const [boxes, setBoxes] = useState<Box[]>([]);
  const signature = keys.join("|");
  useEffect(() => {
    if (!keys.length) {
      setBoxes([]);
      return;
    }
    let frame = 0;
    let scrolled = false;
    let last = "";
    const started = performance.now();
    const loop = () => {
      const elements: HTMLElement[] = [];
      for (const key of keys) document.querySelectorAll<HTMLElement>(`[data-tour~="${key}"]`).forEach((el) => elements.push(el));
      const shown = elements.filter((el) => {
        const r = el.getBoundingClientRect();
        return r.width > 1 && r.height > 1;
      });
      if (!shown.length) {
        // Not on screen yet; give up on the old highlight after a while (a section that isn't there).
        if (performance.now() - started > 1500 && last !== "none") {
          last = "none";
          setBoxes([]);
        }
        frame = requestAnimationFrame(loop);
        return;
      }
      if (!scrolled && shown.length && performance.now() - started > 180) {
        scrolled = true;
        const behavior = reducedMotion() ? "auto" : "smooth";
        if (window.innerWidth < SHEET_BELOW) {
          // Phones: the card covers the bottom of the screen, so every highlighted section goes
          // above it: the topmost one is scrolled to the top of the screen.
          const H = window.innerHeight;
          const clear = H - (sheet?.current || H * 0.55);
          const rects = shown.map((el) => el.getBoundingClientRect());
          const top = Math.min(...rects.map((r) => r.top));
          const bottom = Math.max(...rects.map((r) => r.bottom));
          const first = shown[rects.findIndex((r) => r.top === top)];
          if ((top < 16 || bottom > clear) && !isPinned(first)) first.scrollIntoView({ block: "start", behavior });
        } else {
          const r = shown[0].getBoundingClientRect();
          if (r.top < 90 || r.bottom > window.innerHeight - 150) {
            shown[0].scrollIntoView({ block: r.height > window.innerHeight * 0.6 ? "start" : "center", behavior });
          }
        }
      }
      const next = merge(
        shown.map((el) => {
          const r = el.getBoundingClientRect();
          return { x: r.left - PAD, y: r.top - PAD, w: r.width + 2 * PAD, h: r.height + 2 * PAD };
        }),
      );
      const sig = next.map((b) => [b.x, b.y, b.w, b.h].map(Math.round).join(",")).join(";");
      if (sig !== last) {
        last = sig;
        setBoxes(next);
      }
      frame = requestAnimationFrame(loop);
    };
    frame = requestAnimationFrame(loop);
    return () => cancelAnimationFrame(frame);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [signature, stepId]);
  return boxes;
}

const centre = (b: Box): Box => ({ x: b.x + b.w / 2, y: b.y + b.h / 2, w: 0, h: 0 });
const lerp = (a: number, b: number, k: number) => a + (b - a) * k;

function lerpBoxes(from: Box[], to: Box[], k: number): Box[] {
  const out: Box[] = [];
  for (let i = 0; i < Math.max(from.length, to.length); i++) {
    const a = from[i] ?? centre(to[i]); // a new box grows from its centre
    const b = to[i] ?? centre(from[i]); // a box that goes shrinks away
    const box = { x: lerp(a.x, b.x, k), y: lerp(a.y, b.y, k), w: lerp(a.w, b.w, k), h: lerp(a.h, b.h, k) };
    if (box.w > 2 && box.h > 2) out.push(box);
  }
  return out;
}

function roundedRect(box: Box): string {
  const [x, y, w, h] = [box.x, box.y, box.w, box.h].map((n) => Math.round(n * 2) / 2);
  const r = Math.min(RADIUS, w / 2, h / 2);
  return (
    `M${x + r} ${y}H${x + w - r}A${r} ${r} 0 0 1 ${x + w} ${y + r}V${y + h - r}` +
    `A${r} ${r} 0 0 1 ${x + w - r} ${y + h}H${x + r}A${r} ${r} 0 0 1 ${x} ${y + h - r}V${y + r}A${r} ${r} 0 0 1 ${x + r} ${y}Z`
  );
}

/** Scroll whatever is under the pointer (the page, or the open finding's panel). */
function forwardWheel(e: React.WheelEvent) {
  scrollBy(scrollerAt(e.clientX, e.clientY), e.deltaY);
}

/** Touch: a finger drag on the blocker scrolls what is under it, like the mouse wheel. The first
 *  finger is followed by its id, and what it scrolls is found once, when it touches down. */
let touch: { id: number; y: number; scroller: HTMLElement | null } | null = null;
function onTouchStart(e: React.TouchEvent) {
  const t = e.changedTouches[0];
  if (!t || touch) return;
  touch = { id: t.identifier, y: t.clientY, scroller: scrollerAt(t.clientX, t.clientY) };
}
function onTouchMove(e: React.TouchEvent) {
  const t = touch && Array.from(e.touches).find((x) => x.identifier === touch!.id);
  if (!touch || !t) return;
  scrollBy(touch.scroller, touch.y - t.clientY);
  touch.y = t.clientY;
}
function onTouchEnd(e: React.TouchEvent) {
  if (touch && Array.from(e.changedTouches).some((t) => t.identifier === touch!.id)) touch = null;
}

/** The scrollable panel under a point, or null for the page itself. */
function scrollerAt(x: number, y: number): HTMLElement | null {
  for (const el of document.elementsFromPoint(x, y)) {
    if ((el as HTMLElement).closest("[data-tutorial-layer]")) continue;
    let node: HTMLElement | null = el as HTMLElement;
    while (node && node !== document.body && node !== document.documentElement) {
      const style = getComputedStyle(node);
      if (/(auto|scroll)/.test(style.overflowY) && node.scrollHeight > node.clientHeight + 1) return node;
      node = node.parentElement;
    }
    break;
  }
  return null;
}

function scrollBy(scroller: HTMLElement | null, deltaY: number) {
  (scroller ?? window).scrollBy({ top: deltaY });
}

/** The blur with sharp holes, the rings and the click blocker. On a new card the holes and rings
 *  glide to the new sections in one animation loop that writes styles straight to the page, so
 *  React doesn't re-render anything per frame (it felt laggy before, PR #66 review). */
export function Spotlight({ target, stepId, leaving = false }: { target: Box[]; stepId: number; leaving?: boolean }) {
  const overlay = useRef<HTMLDivElement>(null);
  const rings = useRef<(HTMLDivElement | null)[]>([]);
  const targetRef = useRef<Box[]>(target);
  const shownRef = useRef<Box[]>(target);
  const pending = useRef<Box[] | null>(null);
  const glide = useRef<{ from: Box[]; start: number } | null>(null);
  const lastStep = useRef(stepId);
  targetRef.current = target;

  // A new card: glide from where the highlights are now, once the new sections are found.
  if (stepId !== lastStep.current) {
    lastStep.current = stepId;
    pending.current = shownRef.current;
  }
  useEffect(() => {
    const from = pending.current;
    if (from && target !== from) {
      pending.current = null;
      if (!reducedMotion()) glide.current = { from, start: performance.now() };
    }
  }, [target]);

  useEffect(() => {
    let frame = 0;
    let lastPath = "";
    const draw = (now: number) => {
      let boxes = targetRef.current;
      const g = glide.current;
      if (g) {
        const t = Math.min((now - g.start) / GLIDE_MS, 1);
        if (t >= 1) glide.current = null;
        else boxes = lerpBoxes(g.from, boxes, easeOut(t));
      }
      shownRef.current = boxes;
      const path = `M0 0H${window.innerWidth}V${window.innerHeight}H0Z` + boxes.map(roundedRect).join("");
      if (path !== lastPath) {
        lastPath = path;
        if (overlay.current) overlay.current.style.clipPath = `path(evenodd, '${path}')`;
        rings.current.forEach((el, i) => {
          if (!el) return;
          const b = boxes[i];
          if (!b) {
            el.style.display = "none";
            return;
          }
          el.style.display = "block";
          el.style.transform = `translate(${b.x}px, ${b.y}px)`;
          el.style.width = `${b.w}px`;
          el.style.height = `${b.h}px`;
        });
      }
      frame = requestAnimationFrame(draw);
    };
    frame = requestAnimationFrame(draw);
    return () => cancelAnimationFrame(frame);
  }, []);

  return (
    <>
      <div
        ref={overlay}
        data-tutorial-layer
        aria-hidden
        className={leaving ? "tour-unfade fixed inset-0 z-[60]" : "tour-fade fixed inset-0 z-[60]"}
        style={{
          pointerEvents: "none",
          background: "rgba(12, 12, 16, 0.28)",
          backdropFilter: "blur(2px)",
          WebkitBackdropFilter: "blur(2px)",
          willChange: "clip-path",
        }}
      />
      {Array.from({ length: RING_POOL }).map((_, i) => (
        <div
          key={i}
          ref={(el) => {
            rings.current[i] = el;
          }}
          data-tutorial-layer
          aria-hidden
          className="tour-ring fixed top-0 left-0 z-[61] rounded-[14px]"
          style={{ pointerEvents: "none", display: "none", willChange: "transform" }}
        />
      ))}
      <div
        data-tutorial-layer
        aria-hidden
        className="fixed inset-0 z-[62]"
        style={{ pointerEvents: "auto", touchAction: "none" }}
        onWheel={forwardWheel}
        onTouchStart={onTouchStart}
        onTouchMove={onTouchMove}
        onTouchEnd={onTouchEnd}
        onTouchCancel={onTouchEnd}
        onPointerDown={(e) => e.preventDefault()}
        onClick={(e) => e.preventDefault()}
        onContextMenu={(e) => e.preventDefault()}
      />
    </>
  );
}
