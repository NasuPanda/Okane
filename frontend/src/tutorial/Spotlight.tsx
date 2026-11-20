// The focus effect (docs/ASSUMPTIONS.md A39): the page is softly blurred except for the sections a
// card explains, which get a glowing ring. A transparent layer on top takes every click, so
// nothing on the page can be pressed during the tour; the mouse wheel still scrolls.
import { useEffect, useRef, useState } from "react";

export type Box = { x: number; y: number; w: number; h: number };

const PAD = 8;
const RADIUS = 14;

export const reducedMotion = () => window.matchMedia?.("(prefers-reduced-motion: reduce)").matches ?? false;
/** The glide between cards: a soft ease-out, shared with the card's CSS transition. */
export const GLIDE_MS = 600;
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

/** Where the highlighted sections are, kept up to date while the page scrolls and animates.
 *  On a new card the previous boxes stay until the new sections are found (another page may
 *  still be loading), so the highlight glides instead of blinking out. */
export function useTargetBoxes(keys: string[], stepId: number): Box[] {
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
        const r = shown[0].getBoundingClientRect();
        if (r.top < 90 || r.bottom > window.innerHeight - 150) {
          shown[0].scrollIntoView({
            block: r.height > window.innerHeight * 0.6 ? "start" : "center",
            behavior: reducedMotion() ? "auto" : "smooth",
          });
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

/** The highlights glide to the next card's sections; in between cards they follow the page
 *  directly (scrolling, resizing). The glide starts when the new card's sections appear. */
export function useTweenedBoxes(target: Box[], stepId: number): Box[] {
  const [shown, setShown] = useState<Box[]>(target);
  const shownRef = useRef<Box[]>(target);
  const targetRef = useRef<Box[]>(target);
  const pending = useRef<{ step: number; from: Box[] } | null>(null);
  const glide = useRef<{ from: Box[]; start: number } | null>(null);
  const lastStep = useRef(stepId);
  targetRef.current = target;

  if (stepId !== lastStep.current) {
    lastStep.current = stepId;
    pending.current = { step: stepId, from: shownRef.current };
  }

  useEffect(() => {
    const p = pending.current;
    if (p && target !== p.from) {
      pending.current = null;
      if (!reducedMotion()) glide.current = { from: p.from, start: performance.now() };
    }
    if (glide.current) return;
    shownRef.current = target;
    setShown(target);
  }, [target]);

  useEffect(() => {
    let frame = 0;
    const tick = (now: number) => {
      const g = glide.current;
      if (g) {
        const t = Math.min((now - g.start) / GLIDE_MS, 1);
        const next = lerpBoxes(g.from, targetRef.current, easeOut(t));
        if (t >= 1) glide.current = null;
        shownRef.current = t >= 1 ? targetRef.current : next;
        setShown(shownRef.current);
      }
      frame = requestAnimationFrame(tick);
    };
    frame = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(frame);
  }, []);

  return shown;
}

function roundedRect({ x, y, w, h }: Box): string {
  const r = Math.min(RADIUS, w / 2, h / 2);
  return (
    `M${x + r} ${y}H${x + w - r}A${r} ${r} 0 0 1 ${x + w} ${y + r}V${y + h - r}` +
    `A${r} ${r} 0 0 1 ${x + w - r} ${y + h}H${x + r}A${r} ${r} 0 0 1 ${x} ${y + h - r}V${y + r}A${r} ${r} 0 0 1 ${x + r} ${y}Z`
  );
}

/** Scroll whatever is under the pointer (the page, or the open finding's panel). */
function forwardWheel(e: React.WheelEvent) {
  for (const el of document.elementsFromPoint(e.clientX, e.clientY)) {
    if ((el as HTMLElement).closest("[data-tutorial-layer]")) continue;
    let node: HTMLElement | null = el as HTMLElement;
    while (node && node !== document.body && node !== document.documentElement) {
      const style = getComputedStyle(node);
      if (/(auto|scroll)/.test(style.overflowY) && node.scrollHeight > node.clientHeight + 1) {
        node.scrollBy({ top: e.deltaY });
        return;
      }
      node = node.parentElement;
    }
    break;
  }
  window.scrollBy({ top: e.deltaY });
}

export function Spotlight({ boxes, leaving = false }: { boxes: Box[]; leaving?: boolean }) {
  const W = window.innerWidth;
  const H = window.innerHeight;
  const path = `M0 0H${W}V${H}H0Z` + boxes.map(roundedRect).join("");
  return (
    <>
      <div
        data-tutorial-layer
        aria-hidden
        className={leaving ? "tour-unfade fixed inset-0 z-[60]" : "tour-fade fixed inset-0 z-[60]"}
        style={{
          pointerEvents: "none",
          background: "rgba(12, 12, 16, 0.28)",
          backdropFilter: "blur(3px)",
          WebkitBackdropFilter: "blur(3px)",
          clipPath: `path(evenodd, '${path}')`,
        }}
      />
      {boxes.map((b, i) => (
        <div
          key={i}
          data-tutorial-layer
          aria-hidden
          className="tour-ring fixed z-[61] rounded-[14px]"
          style={{ pointerEvents: "none", left: b.x, top: b.y, width: b.w, height: b.h }}
        />
      ))}
      <div
        data-tutorial-layer
        aria-hidden
        className="fixed inset-0 z-[62]"
        style={{ pointerEvents: "auto" }}
        onWheel={forwardWheel}
        onPointerDown={(e) => e.preventDefault()}
        onClick={(e) => e.preventDefault()}
        onContextMenu={(e) => e.preventDefault()}
      />
    </>
  );
}
