// Cherry blossoms where Mr. Kentaro vanishes at the end of the tour (A39). Purely decorative:
// it ignores the pointer and removes itself when the petals have fallen.
import { useEffect, useMemo, useRef } from "react";
import { createPortal } from "react-dom";

const PINKS = ["#ffb7c5", "#ff9fb7", "#ffd1dc", "#f88fae", "#ffc4d6"];
const COUNT = 34;

type Petal = {
  angle: number;
  speed: number;
  spin: number;
  size: number;
  delay: number;
  duration: number;
  drift: number;
  fall: number;
  color: string;
  blossom: boolean;
};

function makePetals(): Petal[] {
  return Array.from({ length: COUNT }, (_, i) => ({
    angle: ((-165 + Math.random() * 150) * Math.PI) / 180, // an upward fan
    speed: 90 + Math.random() * 230,
    spin: (Math.random() * 2 - 1) * 720,
    size: 10 + Math.random() * 12,
    delay: Math.random() * 220,
    duration: 1450 + Math.random() * 650,
    drift: (Math.random() * 2 - 1) * 90,
    fall: 220 + Math.random() * 260,
    color: PINKS[i % PINKS.length],
    blossom: i % 6 === 0,
  }));
}

function PetalShape({ color }: { color: string }) {
  return (
    <svg viewBox="0 0 10 12" width="100%" height="100%">
      <path d="M5 0.6 C9.4 3.6 9.2 8.4 5 11.6 C0.8 8.4 0.6 3.6 5 0.6 Z" fill={color} />
      <path d="M5 0.6 L4.2 2.4 L5 2 L5.8 2.4 Z" fill="#fff" opacity="0.7" />
      <path d="M5 3 Q5.6 7 5 10" stroke="#fff" strokeWidth="0.5" fill="none" opacity="0.5" />
    </svg>
  );
}

function BlossomShape({ color }: { color: string }) {
  return (
    <svg viewBox="-10 -10 20 20" width="100%" height="100%">
      {[0, 72, 144, 216, 288].map((r) => (
        <path key={r} d="M0 -1.5 C3.2 -4 3 -8.6 0 -9.4 C-3 -8.6 -3.2 -4 0 -1.5 Z" fill={color} transform={`rotate(${r})`} />
      ))}
      <circle r="2" fill="#ffe27a" />
    </svg>
  );
}

export function SakuraBurst({ x, y }: { x: number; y: number }) {
  const petals = useMemo(makePetals, []);
  const box = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const children = Array.from(box.current?.children ?? []) as HTMLElement[];
    const animations = children.map((el, i) => {
      const p = petals[i];
      const dx = Math.cos(p.angle) * p.speed;
      const dy = Math.sin(p.angle) * p.speed;
      const at = (tx: number, ty: number, r: number, s: number) =>
        `translate(-50%, -50%) translate(${tx}px, ${ty}px) rotate(${r}deg) scale(${s})`;
      return el.animate(
        [
          { transform: at(0, 0, 0, 0.3), opacity: 0 },
          { transform: at(dx * 0.25, dy * 0.25, p.spin * 0.1, 1), opacity: 1, offset: 0.08 },
          { transform: at(dx, dy, p.spin * 0.4, 1), opacity: 1, offset: 0.35 },
          { transform: at(dx + p.drift, dy + p.fall, p.spin, 0.85), opacity: 0 },
        ],
        { duration: p.duration, delay: p.delay, easing: "cubic-bezier(0.2, 0.6, 0.35, 1)", fill: "both" },
      );
    });
    return () => animations.forEach((a) => a.cancel());
  }, [petals]);

  return createPortal(
    <div ref={box} aria-hidden className="pointer-events-none fixed z-[64]" style={{ left: x, top: y, width: 0, height: 0 }}>
      {petals.map((p, i) => (
        <span key={i} className="absolute top-0 left-0 block" style={{ width: p.size * (p.blossom ? 1.4 : 1), height: p.size * (p.blossom ? 1.4 : 1.2) }}>
          {p.blossom ? <BlossomShape color={p.color} /> : <PetalShape color={p.color} />}
        </span>
      ))}
    </div>,
    document.body,
  );
}
