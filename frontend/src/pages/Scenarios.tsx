import { FormEvent, useCallback, useEffect, useState } from "react";
import {
  api,
  fmtMoney,
  pnlClass,
  ScenarioComparison,
  ScenarioInfo,
  ScenarioSessionView,
} from "../api";
import MultiLineChart from "../components/MultiLineChart";

export default function ScenariosPage() {
  const [catalog, setCatalog] = useState<ScenarioInfo[]>([]);
  const [sessions, setSessions] = useState<{ id: string; scenario_id: string; completed: boolean }[]>([]);
  const [active, setActive] = useState<ScenarioSessionView | null>(null);
  const [error, setError] = useState("");

  const refresh = useCallback(() => {
    api.scenarios()
      .then((r) => { setCatalog(r.catalog); setSessions(r.sessions); })
      .catch((e: Error) => setError(e.message));
  }, []);
  useEffect(refresh, [refresh]);

  async function start(id: string) {
    setError("");
    try {
      setActive(await api.startScenario(id));
      refresh();
    } catch (e) {
      setError((e as Error).message);
    }
  }

  async function open(id: string) {
    setError("");
    try {
      setActive(await api.scenarioSession(id));
    } catch (e) {
      setError((e as Error).message);
    }
  }

  return (
    <div>
      <h1>Historical Scenarios</h1>
      <p className="muted">
        Replay real market history day by day — genuine prices, no knowledge
        of the future. Trade through the crash the way investors actually
        lived it.
      </p>
      {error && <div className="error">{error}</div>}

      {active ? (
        <SessionPlayer view={active} setView={setActive}
          onExit={() => { setActive(null); refresh(); }} setError={setError} />
      ) : (
        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(360px, 1fr))", gap: 16 }}>
          {catalog.map((s) => {
            const mine = sessions.filter((x) => x.scenario_id === s.id);
            const running = mine.find((x) => !x.completed);
            return (
              <div className="card" key={s.id}>
                <div style={{ display: "flex", gap: 8, alignItems: "baseline" }}>
                  <h2 style={{ marginBottom: 0 }}>{s.name}</h2>
                  <span className="muted">{s.period}</span>
                </div>
                <p className="muted">difficulty: {s.difficulty} · start {fmtMoney(s.starting_cash)}</p>
                <p>{s.description}</p>
                <p className="muted">Universe: {s.universe.join(", ")} · benchmark {s.benchmark}</p>
                <div style={{ display: "flex", gap: 8 }}>
                  {running ? (
                    <button onClick={() => open(running.id)}>Continue replay</button>
                  ) : (
                    <button onClick={() => start(s.id)}>Start replay</button>
                  )}
                  {mine.some((x) => x.completed) && (
                    <button className="ghost"
                      onClick={() => open(mine.find((x) => x.completed)!.id)}>
                      Review finished run
                    </button>
                  )}
                </div>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}

function SessionPlayer({ view, setView, onExit, setError }: {
  view: ScenarioSessionView;
  setView: (v: ScenarioSessionView) => void;
  onExit: () => void;
  setError: (e: string) => void;
}) {
  const [comparison, setComparison] = useState<ScenarioComparison | null>(null);
  const [symbol, setSymbol] = useState(view.scenario.universe[0]);
  const [side, setSide] = useState("BUY");
  const [quantity, setQuantity] = useState("");
  const [busy, setBusy] = useState(false);

  const loadComparison = useCallback(() => {
    api.scenarioComparison(view.id).then(setComparison).catch(() => undefined);
  }, [view.id]);
  useEffect(loadComparison, [loadComparison]);

  async function advance(days: number) {
    setBusy(true);
    setError("");
    try {
      setView(await api.scenarioAdvance(view.id, days));
      loadComparison();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  async function trade(e: FormEvent) {
    e.preventDefault();
    setError("");
    try {
      await api.scenarioTrade(view.id, { symbol, side, quantity });
      setQuantity("");
      setView(await api.scenarioSession(view.id));
    } catch (err) {
      setError((err as Error).message);
    }
  }

  const progress = Math.round((view.day / view.total_days) * 100);
  return (
    <div>
      <div style={{ display: "flex", alignItems: "center", gap: 12, flexWrap: "wrap" }}>
        <button className="ghost" onClick={onExit}>← All scenarios</button>
        <h2 style={{ marginBottom: 0 }}>{view.scenario.name}</h2>
        <span className="badge PENDING">📅 {view.virtual_date}</span>
        <span className="muted">day {view.day} / {view.total_days} ({progress}%)</span>
        {view.completed && <span className="badge FILLED">COMPLETED</span>}
      </div>

      <div className="cards-row" style={{ marginTop: 12 }}>
        <div className="card stat">
          <div className="label">Your value</div>
          <strong>{fmtMoney(view.value)}</strong>
          <div className={pnlClass(view.return_pct)}>{Number(view.return_pct) >= 0 ? "+" : ""}{view.return_pct}%</div>
        </div>
        <div className="card stat">
          <div className="label">Market ({view.scenario.benchmark})</div>
          <div className={pnlClass(view.market_return_pct)}>
            {Number(view.market_return_pct) >= 0 ? "+" : ""}{view.market_return_pct}%
          </div>
        </div>
        <div className="card stat">
          <div className="label">Cash</div>
          <strong>{fmtMoney(view.cash)}</strong>
        </div>
      </div>

      {!view.completed && (
        <div className="card">
          <div style={{ display: "flex", gap: 8, alignItems: "center", flexWrap: "wrap" }}>
            <strong>Advance time:</strong>
            {[1, 5, 21, 63].map((d) => (
              <button key={d} className="ghost" disabled={busy} onClick={() => advance(d)}>
                +{d === 1 ? "1 day" : d === 5 ? "1 week" : d === 21 ? "1 month" : "3 months"}
              </button>
            ))}
            <span className="muted">Prices only move when you advance — decide first.</span>
          </div>
          <form onSubmit={trade} style={{ display: "flex", gap: 8, marginTop: 10, flexWrap: "wrap" }}>
            <select value={symbol} onChange={(e) => setSymbol(e.target.value)}>
              {view.scenario.universe.map((s) => (
                <option key={s} value={s} disabled={!view.quotes[s]?.listed}>
                  {s}{view.quotes[s]?.listed ? "" : " (not listed yet)"}
                </option>
              ))}
            </select>
            <select value={side} onChange={(e) => setSide(e.target.value)}>
              <option value="BUY">Buy</option>
              <option value="SELL">Sell</option>
            </select>
            <input placeholder="Quantity" value={quantity} required style={{ width: 110 }}
              onChange={(e) => setQuantity(e.target.value)} />
            <button type="submit">
              Trade @ {view.quotes[symbol]?.price ?? "—"}
            </button>
          </form>
        </div>
      )}

      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 16 }}>
        <div className="card">
          <h3>Market on {view.virtual_date}</h3>
          <table>
            <thead><tr><th>Symbol</th><th>Close</th><th>Day move</th></tr></thead>
            <tbody>
              {view.scenario.universe.map((s) => {
                const q = view.quotes[s];
                if (!q?.listed) return (
                  <tr key={s}><td>{s}</td><td className="muted" colSpan={2}>not listed yet</td></tr>
                );
                const move = q.prev_close
                  ? ((Number(q.price) - Number(q.prev_close)) / Number(q.prev_close)) * 100
                  : null;
                return (
                  <tr key={s}>
                    <td>{s}</td>
                    <td>{q.price}</td>
                    <td className={move === null ? "" : move > 0 ? "gain" : move < 0 ? "loss" : ""}>
                      {move === null ? "—" : `${move > 0 ? "+" : ""}${move.toFixed(2)}%`}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
        <div className="card">
          <h3>Your holdings</h3>
          {view.holdings.length === 0 && <p className="muted">All cash.</p>}
          {view.holdings.length > 0 && (
            <table>
              <thead><tr><th>Symbol</th><th>Shares</th><th>Value</th></tr></thead>
              <tbody>
                {view.holdings.map((h) => (
                  <tr key={h.symbol}>
                    <td>{h.symbol}</td><td>{h.quantity}</td>
                    <td>{fmtMoney(h.market_value)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      </div>

      {comparison && comparison.series[0].points.length > 1 && (
        <div className="card">
          <h3>You vs the market vs AI strategies</h3>
          <MultiLineChart
            series={comparison.series.map((s) => ({
              label: s.name,
              points: s.points.map(([ts, v]) => ({ ts, value: Number(v) })),
            }))}
          />
          <p className="muted">
            AI strategies are transparent simulations computed from the same
            historical prices (equal-weight buy & hold, monthly index DCA,
            3-month momentum) — shown for comparison, not advice.
          </p>
        </div>
      )}

      {comparison && comparison.players.length > 0 && (
        <div className="card">
          <h3>Other players in this scenario</h3>
          <table>
            <thead><tr><th>Player</th><th>Day</th><th>Value</th><th>Return</th></tr></thead>
            <tbody>
              {comparison.players.map((p) => (
                <tr key={p.display_name}>
                  <td>{p.display_name}{p.completed ? " ✓" : ""}</td>
                  <td>{p.day}</td>
                  <td>{fmtMoney(p.value)}</td>
                  <td className={pnlClass(p.return_pct)}>{p.return_pct}%</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
