import { useState } from "react";
import { Link, useParams } from "react-router-dom";
import { api, fmtMoney, pnlClass, WhatIfResult } from "../api";
import MultiLineChart from "../components/MultiLineChart";

type ScenarioType = "substitute" | "never_sold" | "adopt_ai" | "monthly_dca";

const SCENARIOS: { type: ScenarioType; title: string; blurb: string }[] = [
  { type: "substitute", title: "What if I'd bought X instead?",
    blurb: "Replays every trade of one symbol as if it had been another." },
  { type: "never_sold", title: "What if I never sold?",
    blurb: "Suppresses all sales of a symbol and keeps the shares." },
  { type: "adopt_ai", title: "What if I followed the AI?",
    blurb: "Adds every unexecuted AI buy recommendation at its date." },
  { type: "monthly_dca", title: "What if I'd invested monthly?",
    blurb: "Spreads lump-sum purchases into equal monthly buys." },
];

export default function WhatIfPage() {
  const { id = "" } = useParams();
  const [scenario, setScenario] = useState<ScenarioType>("substitute");
  const [fromSymbol, setFromSymbol] = useState("");
  const [toSymbol, setToSymbol] = useState("");
  const [symbol, setSymbol] = useState("");
  const [range, setRange] = useState("1Y");
  const [result, setResult] = useState<WhatIfResult | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  async function run() {
    setBusy(true);
    setError("");
    setResult(null);
    const body: Record<string, string> = { type: scenario };
    if (scenario === "substitute") {
      body.from_symbol = fromSymbol;
      body.to_symbol = toSymbol;
    } else if (scenario !== "adopt_ai") {
      body.symbol = symbol;
    }
    try {
      setResult(await api.whatIf(id, body, range));
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  const chartSeries = result
    ? [
        { label: "Actual", points: result.actual_points.map((p) => ({
            ts: Math.floor(new Date(p.date + "T00:00:00Z").getTime() / 1000), value: p.value })) },
        { label: "Hypothetical", points: result.hypothetical_points.map((p) => ({
            ts: Math.floor(new Date(p.date + "T00:00:00Z").getTime() / 1000), value: p.value })) },
      ]
    : [];

  return (
    <div>
      <h1>
        What-If Simulator — <Link to={`/portfolios/${id}`}>portfolio</Link>
      </h1>
      <div className="card">
        <div className="form-row">
          {SCENARIOS.map((s) => (
            <button key={s.type} type="button"
              className={`ghost ${scenario === s.type ? "active" : ""}`}
              onClick={() => { setScenario(s.type); setResult(null); }}
              title={s.blurb}>
              {s.title}
            </button>
          ))}
        </div>
        <p className="muted" style={{ margin: "8px 0" }}>
          {SCENARIOS.find((s) => s.type === scenario)?.blurb}
        </p>
        <div className="form-row">
          {scenario === "substitute" && (
            <>
              <div className="field">
                <label htmlFor="wi-from">Instead of</label>
                <input id="wi-from" value={fromSymbol} required style={{ width: 100 }}
                  onChange={(e) => setFromSymbol(e.target.value.toUpperCase())} placeholder="AAPL" />
              </div>
              <div className="field">
                <label htmlFor="wi-to">I'd bought</label>
                <input id="wi-to" value={toSymbol} required style={{ width: 100 }}
                  onChange={(e) => setToSymbol(e.target.value.toUpperCase())} placeholder="NVDA" />
              </div>
            </>
          )}
          {(scenario === "never_sold" || scenario === "monthly_dca") && (
            <div className="field">
              <label htmlFor="wi-symbol">Symbol</label>
              <input id="wi-symbol" value={symbol} required style={{ width: 100 }}
                onChange={(e) => setSymbol(e.target.value.toUpperCase())} placeholder="AAPL" />
            </div>
          )}
          <div className="field">
            <label htmlFor="wi-range">Chart range</label>
            <select id="wi-range" value={range} onChange={(e) => setRange(e.target.value)}>
              <option>1M</option><option>3M</option><option>6M</option>
              <option>1Y</option><option>5Y</option>
            </select>
          </div>
          <button onClick={run} disabled={busy} type="button">
            {busy ? "Simulating…" : "Simulate"}
          </button>
        </div>
      </div>

      {error && <div className="error">{error}</div>}

      {result && (
        <>
          <div className="cards-row">
            <div className="card stat">
              <div className="label">Actual value</div>
              <div className="value">{fmtMoney(String(result.actual_final), result.currency)}</div>
            </div>
            <div className="card stat">
              <div className="label">Hypothetical value</div>
              <div className="value">{fmtMoney(String(result.hypothetical_final), result.currency)}</div>
            </div>
            <div className="card stat">
              <div className="label">Difference</div>
              <div className={`value ${pnlClass(String(result.delta))}`}>
                {fmtMoney(String(result.delta), result.currency)}
                {result.delta_pct !== null && ` (${result.delta_pct}%)`}
              </div>
              <div className="sub">{result.description}</div>
            </div>
          </div>
          <div className="card">
            <h2>Actual vs hypothetical</h2>
            <MultiLineChart series={chartSeries} height={320} />
            <p className="muted" style={{ marginTop: 8 }}>{result.note}</p>
          </div>
        </>
      )}
    </div>
  );
}
