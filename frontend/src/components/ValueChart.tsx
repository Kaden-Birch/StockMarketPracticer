import { ColorType, createChart, UTCTimestamp } from "lightweight-charts";
import { useEffect, useRef } from "react";
import { chartBaseOptions, cssVar, useThemeAttr } from "../chartTheme";

/** Portfolio-value area chart from the reconstructed daily series. */
export default function ValueChart({
  points,
  height = 300,
}: {
  points: { date: string; value: number }[];
  height?: number;
}) {
  const containerRef = useRef<HTMLDivElement>(null);
  const theme = useThemeAttr();

  useEffect(() => {
    const el = containerRef.current;
    if (!el || points.length === 0) return;
    const base = chartBaseOptions();
    const chart = createChart(el, {
      height,
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
    series.setData(
      points.map((p) => ({
        time: (new Date(p.date + "T00:00:00Z").getTime() / 1000) as UTCTimestamp,
        value: p.value,
      })),
    );
    chart.timeScale().fitContent();
    const observer = new ResizeObserver(() => chart.applyOptions({ width: el.clientWidth }));
    observer.observe(el);
    return () => {
      observer.disconnect();
      chart.remove();
    };
  }, [points, theme, height]);

  return <div ref={containerRef} />;
}
