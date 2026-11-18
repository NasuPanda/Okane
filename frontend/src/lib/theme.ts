import { useCallback, useEffect, useState } from "react";

export type Theme = "light" | "dark";
const KEY = "okane-theme";

function systemTheme(): Theme {
  return window.matchMedia?.("(prefers-color-scheme: dark)").matches ? "dark" : "light";
}

export function storedTheme(): Theme {
  try {
    const saved = localStorage.getItem(KEY);
    if (saved === "light" || saved === "dark") return saved;
  } catch {
    /* storage unavailable: fall back to the system setting */
  }
  return systemTheme();
}

export function applyTheme(theme: Theme) {
  document.documentElement.classList.toggle("dark", theme === "dark");
}

/** Light/dark theme, remembered per browser; follows the system until the person chooses. */
export function useTheme() {
  const [theme, setTheme] = useState<Theme>(() => storedTheme());
  useEffect(() => applyTheme(theme), [theme]);
  const toggle = useCallback(() => {
    setTheme((current) => {
      const next = current === "dark" ? "light" : "dark";
      try {
        localStorage.setItem(KEY, next);
      } catch {
        /* the choice just won't persist */
      }
      return next;
    });
  }, []);
  return { theme, toggle };
}
