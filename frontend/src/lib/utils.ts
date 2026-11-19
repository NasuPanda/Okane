import { type ClassValue, clsx } from "clsx";
import { twMerge } from "tailwind-merge";

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

const whole = new Intl.NumberFormat("en-GB", { maximumFractionDigits: 0 });
const cents = new Intl.NumberFormat("en-GB", { minimumFractionDigits: 2, maximumFractionDigits: 2 });

/** Full amount with thousands separators, e.g. 1,838,462. Amounts are scaled EUR. */
export function eur(value: number | null | undefined, withCents = false): string {
  if (value === null || value === undefined || Number.isNaN(value)) return "–";
  return (withCents ? cents : whole).format(value);
}

/** Compact amount for cards and axes: 1.84M, 514K. */
export function shortEur(value: number | null | undefined): string {
  if (value === null || value === undefined) return "–";
  const size = Math.abs(value);
  const sign = value < 0 ? "-" : "";
  if (size >= 1_000_000) return `${sign}${(size / 1_000_000).toFixed(2)}M`;
  if (size >= 1_000) return `${sign}${(size / 1_000).toFixed(0)}K`;
  return `${sign}${size.toFixed(0)}`;
}

export function day(value: string | null | undefined): string {
  if (!value) return "–";
  const d = new Date(`${value}T00:00:00`);
  return d.toLocaleDateString("en-GB", { day: "numeric", month: "short", year: "numeric" });
}

export function stamp(value: string | null | undefined): string {
  if (!value) return "–";
  const d = new Date(value.endsWith("Z") ? value : `${value}Z`);
  return d.toLocaleString("en-GB", {
    day: "numeric",
    month: "short",
    hour: "2-digit",
    minute: "2-digit",
  });
}

/** A local date-time from the backend (no time zone), as "Mon 23 Nov". */
export function dueDay(value: string | null | undefined): string {
  if (!value) return "–";
  return new Date(value).toLocaleDateString("en-GB", { weekday: "short", day: "numeric", month: "short" });
}

export function monthLabel(value: string): string {
  const [y, m] = value.split("-").map(Number);
  return new Date(y, m - 1, 1).toLocaleDateString("en-GB", { month: "short", year: "2-digit" });
}
