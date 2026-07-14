import { ColorType, createChart, UTCTimestamp } from "lightweight-charts";
import { useEffect, useRef, useState } from "react";
import { api } from "../api";
import { chartBaseOptions, cssVar, useThemeAttr } from "../chartTheme";

const RANGES = ["1M", "3M", "6M", "1Y", "5Y"];

/** Dashboard net-worth-over-time (M11 note 9): every portfolio's cash +
 * holdings summed day by day, rebuilt from real transactions and real
 * prices. Optional inflation-adjusted line at a user-stated assumed rate. */
export default function NetWorthChart({ gameId = "" }: { gameId?: string }) {
  const containerRef = useRef<HTMLDivElement>(null);
  const [range, setRange] = useState("1Y");
  const [inflationOn, setInflationOn] = useState(false);
  const [inflationPct, setInflationPct] = useState("3");
  const [note, setNote] = useState("");
  const [error, setError] = useState("");
  const [empty, setEmpty] = useState(false);
  const theme = useThemeAttr();

  useEffect(() => {
    const el = containerRef.current;
    if (!el) return;
    const base = chartBaseOptions();
    const chart = createChart(el, {
      height: 260,
      ...base,
      layout: { ...base.layout, background: { type: ColorType.Solid, color: "transparent" } },
    });
    const accent = cssVar("--accent");
    const area = chart.addAreaSeries({
      lineColor: accent, lineWidth: 2,
      topColor: accent + "33", bottomColor: accent + "00",
    });
    const realLine = chart.addLineSeries({
      color: "#eda100", lineWidth: 1, lineStyle: 2,
      priceLineVisible: false, lastValueVisible: false,
    });
    const observer = new ResizeObserver(() => chart.applyOptions({ width: el.clientWidth }));
    observer.observe(el);

    let cancelled = false;
    setError("");
    const pct = inflationOn ? Number(inflationPct) || 0 : 0;
    api
      .networth(range, pct, gameId)
      .then((r) => {
        if (cancelled) return;
        setNote(r.note);
        setEmpty(r.points.length === 0);
        area.setData(r.points.map((p) => ({
          time: Math.floor(new Date(p.date).getTime() / 1000) as UTCTimestamp,
          value: p.value,
        })));
        realLine.setData(
          pct > 0
            ? r.points
                .filter((p) => p.real_value !== undefined)
                .map((p) => ({
                  time: Math.floor(new Date(p.date).getTime() / 1000) as UTCTimestamp,
                  value: p.real_value as number,
                }))
            : [],
        );
        chart.timeScale().fitContent();
      })
      .catch((e: Error) => !cancelled && setError(e.message));

    return () => {
      cancelled = true;
      observer.disconnect();
      chart.remove();
    };
  }, [range, inflationOn, inflationPct, gameId, theme]);

  return (
    <div className="card">
      <div className="range-row" role="tablist" aria-label="Net worth range">
        <h2 style={{ margin: 0, marginRight: 8 }}>Net worth over time</h2>
        {RANGES.map((r) => (
          <button key={r} className={`ghost ${r === range ? "active" : ""}`}
            onClick={() => setRange(r)} role="tab" aria-selected={r === range}>
            {r}
          </button>
        ))}
        <span style={{ flex: 1 }} />
        <label style={{ display: "flex", alignItems: "center", gap: 6 }}
          title="Discount the curve by an assumed yearly inflation rate — a planning assumption you choose, not real CPI data">
          <input type="checkbox" checked={inflationOn}
            onChange={(e) => setInflationOn(e.target.checked)} />
          Adjust for inflation
        </label>
        {inflationOn && (
          <label style={{ display: "flex", alignItems: "center", gap: 4 }}>
            <input type="number" step="0.1" min="0" max="20" value={inflationPct}
              onChange={(e) => setInflationPct(e.target.value)} style={{ width: 70 }} />
            %/yr
          </label>
        )}
      </div>
      {error && <div className="error">{error}</div>}
      {empty && !error && (
        <p className="muted">No history yet — the curve appears once your portfolios have activity.</p>
      )}
      <div ref={containerRef} />
      {note && <div className="muted">{note}</div>}
    </div>
  );
}
