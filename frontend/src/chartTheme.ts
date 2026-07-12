import { useEffect, useState } from "react";

export function cssVar(name: string): string {
  return getComputedStyle(document.documentElement).getPropertyValue(name).trim();
}

/** Tracks the data-theme attribute so charts rebuild with the right colors
 * when the user toggles light/dark. */
export function useThemeAttr(): string {
  const [theme, setTheme] = useState(document.documentElement.dataset.theme ?? "light");
  useEffect(() => {
    const observer = new MutationObserver(() =>
      setTheme(document.documentElement.dataset.theme ?? "light"),
    );
    observer.observe(document.documentElement, {
      attributes: true,
      attributeFilter: ["data-theme"],
    });
    return () => observer.disconnect();
  }, []);
  return theme;
}

/** Categorical series palette — fixed slot order (never cycled or re-ranked),
 * with dark-mode steps validated for the dark surface. */
const SERIES_LIGHT = [
  "#2a78d6", "#1baf7a", "#eda100", "#008300",
  "#4a3aa7", "#e34948", "#e87ba4", "#eb6834",
];
const SERIES_DARK = [
  "#3987e5", "#199e70", "#c98500", "#008300",
  "#9085e9", "#e66767", "#d55181", "#d95926",
];

export function seriesColor(slot: number, theme: string): string {
  const palette = theme === "dark" ? SERIES_DARK : SERIES_LIGHT;
  return palette[slot % palette.length];
}

export function chartBaseOptions() {
  return {
    layout: {
      background: { color: "transparent" },
      textColor: cssVar("--text-secondary"),
      fontFamily: "inherit",
    },
    grid: {
      vertLines: { color: cssVar("--chart-grid") },
      horzLines: { color: cssVar("--chart-grid") },
    },
    timeScale: { borderColor: cssVar("--border") },
    rightPriceScale: { borderColor: cssVar("--border") },
  };
}
