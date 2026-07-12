import { ColorType, createChart, UTCTimestamp } from "lightweight-charts";
import { useEffect, useRef } from "react";
import { chartBaseOptions, seriesColor, useThemeAttr } from "../chartTheme";

export interface LineSeriesData {
  label: string;
  points: { ts: number; value: number }[];
}

/** Multi-series comparison chart. Colors follow the fixed categorical slot
 * order by series identity (input order), never re-ranked by value. */
export default function MultiLineChart({
  series,
  height = 360,
  valueSuffix = "",
}: {
  series: LineSeriesData[];
  height?: number;
  valueSuffix?: string;
}) {
  const containerRef = useRef<HTMLDivElement>(null);
  const theme = useThemeAttr();

  useEffect(() => {
    const el = containerRef.current;
    if (!el) return;
    const base = chartBaseOptions();
    const chart = createChart(el, {
      height,
      ...base,
      layout: { ...base.layout, background: { type: ColorType.Solid, color: "transparent" } },
    });
    series.forEach((s, i) => {
      const line = chart.addLineSeries({
        color: seriesColor(i, theme),
        lineWidth: 2,
        priceLineVisible: false,
        title: s.label,
      });
      line.setData(s.points.map((p) => ({ time: p.ts as UTCTimestamp, value: p.value })));
    });
    chart.timeScale().fitContent();
    const observer = new ResizeObserver(() => chart.applyOptions({ width: el.clientWidth }));
    observer.observe(el);
    return () => {
      observer.disconnect();
      chart.remove();
    };
  }, [series, theme, height]);

  return (
    <div>
      <div ref={containerRef} />
      <div style={{ display: "flex", gap: 16, flexWrap: "wrap", marginTop: 8 }} aria-hidden={false}>
        {series.map((s, i) => (
          <span key={s.label} style={{ display: "inline-flex", alignItems: "center", gap: 6 }}>
            <span
              style={{
                width: 12, height: 12, borderRadius: 3, display: "inline-block",
                background: seriesColor(i, theme),
              }}
            />
            <span className="muted">{s.label}{valueSuffix}</span>
          </span>
        ))}
      </div>
    </div>
  );
}
