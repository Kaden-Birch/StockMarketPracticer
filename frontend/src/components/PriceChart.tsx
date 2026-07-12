import {
  ColorType,
  createChart,
  IChartApi,
  ISeriesApi,
  SeriesMarker,
  Time,
  UTCTimestamp,
} from "lightweight-charts";
import { useEffect, useRef, useState } from "react";
import { api, HistoryBar, Txn } from "../api";
import { useChartRange } from "../chartSync";
import { chartBaseOptions, cssVar, useThemeAttr } from "../chartTheme";

const RANGES = ["1D", "5D", "1M", "3M", "6M", "1Y", "5Y", "MAX"];
const SMA_OPTIONS = [20, 50, 200];

function sma(bars: HistoryBar[], period: number): { time: UTCTimestamp; value: number }[] {
  const out: { time: UTCTimestamp; value: number }[] = [];
  let sum = 0;
  for (let i = 0; i < bars.length; i++) {
    sum += bars[i].close;
    if (i >= period) sum -= bars[i - period].close;
    if (i >= period - 1) out.push({ time: bars[i].ts as UTCTimestamp, value: sum / period });
  }
  return out;
}

function markersFromTxns(txns: Txn[], theme: string): SeriesMarker<Time>[] {
  const gain = cssVar("--gain");
  const loss = cssVar("--loss");
  const accent = cssVar("--accent");
  const violet = theme === "dark" ? "#9085e9" : "#4a3aa7";
  return txns.map((t) => {
    const time = Math.floor(new Date(t.executed_at).getTime() / 1000) as UTCTimestamp;
    if (t.kind === "DIVIDEND")
      return { time, position: "belowBar", color: accent, shape: "circle", text: "D" };
    if (t.kind === "SPLIT")
      return { time, position: "belowBar", color: violet, shape: "square", text: "S" };
    const ai = t.origin.startsWith("AI");
    if (t.side === "BUY")
      return {
        time, position: "belowBar", color: ai ? violet : gain,
        shape: "arrowUp", text: ai ? "AI B" : "B",
      };
    return {
      time, position: "aboveBar", color: ai ? violet : loss,
      shape: "arrowDown", text: ai ? "AI S" : "S",
    };
  });
}

export default function PriceChart({ symbol }: { symbol: string }) {
  const containerRef = useRef<HTMLDivElement>(null);
  const chartRef = useRef<IChartApi | null>(null);
  const seriesRef = useRef<ISeriesApi<"Area"> | null>(null);
  const smaSeriesRef = useRef<ISeriesApi<"Line">[]>([]);
  const barsRef = useRef<HistoryBar[]>([]);
  const [range, setRange, sync, setSync] = useChartRange("1M");
  const [error, setError] = useState("");
  const [provider, setProvider] = useState("");
  const [showTrades, setShowTrades] = useState(true);
  const [smaOn, setSmaOn] = useState<number[]>([]);
  const theme = useThemeAttr();
  const [chartEpoch, setChartEpoch] = useState(0);

  useEffect(() => {
    const el = containerRef.current;
    if (!el) return;
    const base = chartBaseOptions();
    const chart = createChart(el, {
      height: 360,
      ...base,
      layout: { ...base.layout, background: { type: ColorType.Solid, color: "transparent" } },
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
    smaSeriesRef.current = [];

    const observer = new ResizeObserver(() => chart.applyOptions({ width: el.clientWidth }));
    observer.observe(el);
    setChartEpoch((n) => n + 1); // trigger a data reload into the new chart
    return () => {
      observer.disconnect();
      chart.remove();
      chartRef.current = null;
      seriesRef.current = null;
      smaSeriesRef.current = [];
    };
  }, [theme]);

  // load price history
  useEffect(() => {
    if (chartEpoch === 0) return;
    let cancelled = false;
    setError("");
    api
      .history(symbol, range)
      .then((hist) => {
        if (cancelled || !seriesRef.current || !chartRef.current) return;
        barsRef.current = hist.bars;
        seriesRef.current.setData(
          hist.bars.map((b) => ({ time: b.ts as UTCTimestamp, value: b.close })),
        );
        chartRef.current.applyOptions({
          timeScale: { timeVisible: range === "1D" || range === "5D" },
        });
        chartRef.current.timeScale().fitContent();
        setProvider(hist.provider);
        refreshSma(smaOn);
      })
      .catch((e: Error) => !cancelled && setError(e.message));
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [symbol, range, chartEpoch]);

  // trade/dividend/split markers
  useEffect(() => {
    if (chartEpoch === 0 || !seriesRef.current) return;
    if (!showTrades || range === "1D" || range === "5D") {
      seriesRef.current.setMarkers([]);
      return;
    }
    let cancelled = false;
    api
      .symbolTransactions(symbol)
      .then((txns) => {
        if (!cancelled && seriesRef.current)
          seriesRef.current.setMarkers(markersFromTxns(txns, theme));
      })
      .catch(() => undefined);
    return () => {
      cancelled = true;
    };
  }, [symbol, range, chartEpoch, showTrades, theme]);

  function refreshSma(periods: number[]) {
    const chart = chartRef.current;
    if (!chart) return;
    smaSeriesRef.current.forEach((s) => chart.removeSeries(s));
    smaSeriesRef.current = [];
    const colors = [cssVar("--gain"), "#eda100", cssVar("--loss")];
    periods.forEach((p, i) => {
      const line = chart.addLineSeries({
        color: colors[i % colors.length],
        lineWidth: 1,
        priceLineVisible: false,
        lastValueVisible: false,
        crosshairMarkerVisible: false,
      });
      line.setData(sma(barsRef.current, p));
      smaSeriesRef.current.push(line);
    });
  }

  function toggleSma(period: number) {
    const next = smaOn.includes(period)
      ? smaOn.filter((p) => p !== period)
      : [...smaOn, period].sort((a, b) => a - b);
    setSmaOn(next);
    refreshSma(next);
  }

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
        <span style={{ flex: 1 }} />
        {SMA_OPTIONS.map((p) => (
          <button
            key={p}
            className={`ghost ${smaOn.includes(p) ? "active" : ""}`}
            onClick={() => toggleSma(p)}
            title={`${p}-bar simple moving average`}
          >
            SMA {p}
          </button>
        ))}
        <button
          className={`ghost ${showTrades ? "active" : ""}`}
          onClick={() => setShowTrades(!showTrades)}
          title="Show buys, sells, dividends, and splits on the chart"
        >
          Events
        </button>
        <button
          className={`ghost ${sync ? "active" : ""}`}
          onClick={() => setSync(!sync)}
          title="Synchronize the date range across all charts"
        >
          Sync
        </button>
      </div>
      {error && <div className="error">{error}</div>}
      <div ref={containerRef} />
      {provider && (
        <div className="muted">
          Data: {provider} · real market data, may be exchange-delayed
          {showTrades && range !== "1D" && range !== "5D" &&
            " · markers: B/S trades, D dividends, S splits (AI trades in violet)"}
        </div>
      )}
    </div>
  );
}
