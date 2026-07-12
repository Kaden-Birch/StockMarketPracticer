import {
  ColorType,
  createChart,
  IChartApi,
  ISeriesApi,
  UTCTimestamp,
} from "lightweight-charts";
import { useEffect, useRef, useState } from "react";
import { api, HistoryBar } from "../api";

const RANGES = ["1D", "5D", "1M", "3M", "6M", "1Y", "5Y", "MAX"];

function cssVar(name: string): string {
  return getComputedStyle(document.documentElement).getPropertyValue(name).trim();
}

/** Tracks the data-theme attribute so charts rebuild with the right colors
 * when the user toggles light/dark. */
function useThemeAttr(): string {
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

export default function PriceChart({ symbol }: { symbol: string }) {
  const containerRef = useRef<HTMLDivElement>(null);
  const chartRef = useRef<IChartApi | null>(null);
  const seriesRef = useRef<ISeriesApi<"Area"> | null>(null);
  const [range, setRange] = useState("1M");
  const [error, setError] = useState("");
  const [provider, setProvider] = useState("");
  const theme = useThemeAttr();
  const [chartEpoch, setChartEpoch] = useState(0);

  useEffect(() => {
    const el = containerRef.current;
    if (!el) return;
    const chart = createChart(el, {
      height: 360,
      layout: {
        background: { type: ColorType.Solid, color: "transparent" },
        textColor: cssVar("--text-secondary"),
        fontFamily: "inherit",
      },
      grid: {
        vertLines: { color: cssVar("--chart-grid") },
        horzLines: { color: cssVar("--chart-grid") },
      },
      timeScale: { borderColor: cssVar("--border") },
      rightPriceScale: { borderColor: cssVar("--border") },
    });
    const accent = cssVar("--accent");
    const series = chart.addAreaSeries({
      lineColor: accent,
      lineWidth: 2,
      topColor: accent + "33",
      bottomColor: accent + "00",
    });
    chartRef.current = chart;
    seriesRef.current = series;

    const observer = new ResizeObserver(() => chart.applyOptions({ width: el.clientWidth }));
    observer.observe(el);
    setChartEpoch((n) => n + 1); // trigger a data reload into the new chart
    return () => {
      observer.disconnect();
      chart.remove();
      chartRef.current = null;
      seriesRef.current = null;
    };
  }, [theme]);

  useEffect(() => {
    if (chartEpoch === 0) return;
    let cancelled = false;
    setError("");
    api
      .history(symbol, range)
      .then((hist) => {
        if (cancelled || !seriesRef.current || !chartRef.current) return;
        const data = hist.bars.map((b: HistoryBar) => ({
          time: b.ts as UTCTimestamp,
          value: b.close,
        }));
        seriesRef.current.setData(data);
        chartRef.current.applyOptions({
          timeScale: { timeVisible: range === "1D" || range === "5D" },
        });
        chartRef.current.timeScale().fitContent();
        setProvider(hist.provider);
      })
      .catch((e: Error) => !cancelled && setError(e.message));
    return () => {
      cancelled = true;
    };
  }, [symbol, range, chartEpoch]);

  return (
    <div>
      <div className="range-row" role="tablist" aria-label="Chart range">
        {RANGES.map((r) => (
          <button
            key={r}
            className={`ghost ${r === range ? "active" : ""}`}
            onClick={() => setRange(r)}
            role="tab"
            aria-selected={r === range}
          >
            {r}
          </button>
        ))}
      </div>
      {error && <div className="error">{error}</div>}
      <div ref={containerRef} />
      {provider && (
        <div className="muted">
          Data: {provider} · real market data, may be exchange-delayed
        </div>
      )}
    </div>
  );
}
