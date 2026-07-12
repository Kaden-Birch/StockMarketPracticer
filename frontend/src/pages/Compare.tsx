import { useEffect, useState } from "react";
import { api, CompareSeries } from "../api";
import MultiLineChart from "../components/MultiLineChart";
import { useChartRange } from "../chartSync";

const RANGES = ["1M", "3M", "6M", "1Y", "5Y", "MAX"];

export default function ComparePage() {
  const [input, setInput] = useState("AAPL, MSFT, NVDA");
  const [symbols, setSymbols] = useState<string[]>([]);
  const [range, setRange, sync, setSync] = useChartRange("1Y");
  const [series, setSeries] = useState<CompareSeries[]>([]);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (symbols.length < 2) return;
    let cancelled = false;
    setLoading(true);
    const effective = range === "1D" || range === "5D" ? "1M" : range;
    api
      .compare(symbols, effective)
      .then((res) => {
        if (!cancelled) {
          setSeries(res.series);
          setError("");
        }
      })
      .catch((e: Error) => !cancelled && setError(e.message))
      .finally(() => !cancelled && setLoading(false));
    return () => {
      cancelled = true;
    };
  }, [symbols, range]);

  function run() {
    const parsed = input
      .split(/[\s,]+/)
      .map((s) => s.trim().toUpperCase())
      .filter(Boolean);
    setSymbols([...new Set(parsed)]);
    api.gamifyEvent("companies_compared", parsed.join(",")).catch(() => undefined);
  }

  return (
    <div>
      <h1>Compare companies</h1>
      <div className="card">
        <div className="form-row">
          <div className="field" style={{ flex: 1 }}>
            <label htmlFor="cmp-symbols">Symbols (2–8, comma separated)</label>
            <input
              id="cmp-symbols"
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter") {
                  e.preventDefault();
                  run();
                }
              }}
              style={{ width: "100%" }}
            />
          </div>
          <button onClick={run} type="button">Compare</button>
        </div>
      </div>
      {error && <div className="error">{error}</div>}
      {symbols.length >= 2 && (
        <div className="card">
          <h2>Price performance (indexed to 100)</h2>
          <div className="range-row" role="tablist" aria-label="Compare range">
            {RANGES.map((r) => (
              <button key={r} className={`ghost ${r === range ? "active" : ""}`}
                onClick={() => setRange(r)} role="tab" aria-selected={r === range}>
                {r}
              </button>
            ))}
            <span style={{ flex: 1 }} />
            <button className={`ghost ${sync ? "active" : ""}`} onClick={() => setSync(!sync)}
              title="Synchronize the date range across all charts">
              Sync
            </button>
          </div>
          {loading && <p className="muted">Loading…</p>}
          {series.length > 0 && (
            <>
              <MultiLineChart
                series={series.map((s) => ({ label: s.symbol, points: s.points }))}
              />
              <table style={{ marginTop: 16 }}>
                <thead>
                  <tr>
                    <th>Symbol</th>
                    <th className="num">Total return ({range})</th>
                    <th className="num">Volatility (ann.)</th>
                    <th>Currency</th>
                    <th>Data</th>
                  </tr>
                </thead>
                <tbody>
                  {series.map((s) => (
                    <tr key={s.symbol}>
                      <td>{s.symbol}</td>
                      <td className={`num ${s.total_return_pct !== null && s.total_return_pct < 0 ? "loss" : "gain"}`}>
                        {s.total_return_pct !== null ? `${s.total_return_pct}%` : "—"}
                      </td>
                      <td className="num">
                        {s.volatility_pct !== null ? `${s.volatility_pct}%` : "—"}
                      </td>
                      <td>{s.currency}</td>
                      <td className="muted">{s.provider}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </>
          )}
        </div>
      )}
      <p className="muted">
        Fundamentals comparison (revenue, P/E, margins…) arrives with a keyed fundamentals
        provider — price-based metrics only for now.
      </p>
    </div>
  );
}
