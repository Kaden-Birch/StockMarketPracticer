import { ColorType, createChart, UTCTimestamp } from "lightweight-charts";
import { FormEvent, useCallback, useEffect, useRef, useState } from "react";
import { api, fmtMoney, FutureView, pnlClass } from "../api";
import SymbolPicker from "../components/SymbolPicker";
import { chartBaseOptions, useThemeAttr } from "../chartTheme";

function ValueChart({ points }: { points: { date: string; value: string }[] }) {
  const ref = useRef<HTMLDivElement>(null);
  const theme = useThemeAttr();
  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    const base = chartBaseOptions();
    const chart = createChart(el, {
      height: 240,
      ...base,
      layout: { ...base.layout, background: { type: ColorType.Solid, color: "transparent" } },
    });
    const violet = theme === "dark" ? "#9085e9" : "#4a3aa7";
    const area = chart.addAreaSeries({
      lineColor: violet, lineWidth: 2,
      topColor: violet + "33", bottomColor: violet + "00",
    });
    // dedupe by date (long advances can sample two steps onto one calendar day)
    const seen = new Set<string>();
    const data: { time: UTCTimestamp; value: number }[] = [];
    for (const p of points) {
      if (seen.has(p.date)) continue;
      seen.add(p.date);
      data.push({
        time: Math.floor(new Date(p.date).getTime() / 1000) as UTCTimestamp,
        value: Number(p.value),
      });
    }
    area.setData(data);
    chart.timeScale().fitContent();
    const observer = new ResizeObserver(() => chart.applyOptions({ width: el.clientWidth }));
    observer.observe(el);
    return () => {
      observer.disconnect();
      chart.remove();
    };
  }, [points, theme]);
  return <div ref={ref} />;
}

const ADVANCES = [
  { label: "+1 week", days: 5 },
  { label: "+1 month", days: 21 },
  { label: "+6 months", days: 126 },
  { label: "+1 year", days: 260 },
];

export default function FuturePage() {
  const [sessions, setSessions] = useState<
    { id: string; symbols: string; step: number; virtual_date: string }[]
  >([]);
  const [disclaimer, setDisclaimer] = useState("");
  const [view, setView] = useState<FutureView | null>(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  // start form
  const [pick, setPick] = useState("");
  const [universe, setUniverse] = useState<string[]>([]);
  const [cash, setCash] = useState("100000");

  // trade form
  const [tSymbol, setTSymbol] = useState("");
  const [tSide, setTSide] = useState("BUY");
  const [tMode, setTMode] = useState<"quantity" | "notional">("notional");
  const [tAmount, setTAmount] = useState("");
  const [tradeMsg, setTradeMsg] = useState("");

  const refresh = useCallback(() => {
    api
      .futureSessions()
      .then((r) => {
        setSessions(r.sessions);
        setDisclaimer(r.disclaimer);
      })
      .catch((e: Error) => setError(e.message));
  }, []);
  useEffect(refresh, [refresh]);

  function open(id: string) {
    setError("");
    setTradeMsg("");
    api.futureGet(id).then((v) => {
      setView(v);
      setTSymbol(v.symbols[0] ?? "");
    }).catch((e: Error) => setError(e.message));
  }

  function addSymbol() {
    const s = pick.trim().toUpperCase();
    if (s && !universe.includes(s)) setUniverse([...universe, s]);
    setPick("");
  }

  async function start(e: FormEvent) {
    e.preventDefault();
    if (universe.length === 0) {
      setError("Add at least one symbol to the game's universe");
      return;
    }
    setError("");
    setBusy(true);
    try {
      const v = await api.futureStart(universe, cash);
      setView(v);
      setTSymbol(v.symbols[0] ?? "");
      setUniverse([]);
      refresh();
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(false);
    }
  }

  async function advance(days: number) {
    if (!view) return;
    setBusy(true);
    setError("");
    try {
      setView(await api.futureAdvance(view.id, days));
      refresh();
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(false);
    }
  }

  async function trade(e: FormEvent) {
    e.preventDefault();
    if (!view) return;
    setBusy(true);
    setError("");
    setTradeMsg("");
    try {
      const r = await api.futureTrade(view.id, {
        symbol: tSymbol,
        side: tSide,
        quantity: tMode === "quantity" ? tAmount : null,
        notional: tMode === "notional" ? tAmount : null,
      });
      setTradeMsg(`${r.status} at ${fmtMoney(r.filled_price)} (simulated)`);
      setTAmount("");
      setView(await api.futureGet(view.id));
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(false);
    }
  }

  async function abandon() {
    if (!view) return;
    if (!window.confirm("Abandon this future game? Its portfolio and history are deleted.")) return;
    await api.futureAbandon(view.id).catch((e: Error) => setError(e.message));
    setView(null);
    refresh();
  }

  return (
    <div>
      <h1>Future mode 🔮</h1>
      <div className="card" style={{
        borderLeft: "4px solid #eda100", fontWeight: 600,
      }}>
        ⚠️ SIMULATED DATA — {disclaimer ||
          "prices in this mode are statistically-shaped fiction, never real market data."}
      </div>

      {!view && (
        <>
          <div className="card">
            <h2>Your future games</h2>
            {sessions.length === 0 && (
              <p className="muted">
                No games yet. Start one below: it begins at today's REAL prices,
                then you fast-forward through simulated years in minutes.
              </p>
            )}
            {sessions.map((s) => (
              <div key={s.id} className="form-row" style={{ padding: "6px 0" }}>
                <strong>{JSON.parse(s.symbols).join(", ")}</strong>
                <span className="muted">
                  day {s.step} · virtual date {s.virtual_date}
                </span>
                <button className="ghost" onClick={() => open(s.id)}>Open</button>
              </div>
            ))}
          </div>

          <form className="card" onSubmit={start}>
            <h2>Start a new future game</h2>
            <div className="form-row">
              <div className="field">
                <label htmlFor="fut-sym">Add symbol to universe</label>
                <div style={{ display: "flex", gap: 6 }}>
                  <SymbolPicker id="fut-sym" value={pick} onChange={setPick} width={200} />
                  <button type="button" className="ghost" onClick={addSymbol}>Add</button>
                </div>
              </div>
              <div className="field">
                <label htmlFor="fut-cash">Starting cash ($)</label>
                <input id="fut-cash" type="number" min="1" step="any" value={cash}
                  onChange={(e) => setCash(e.target.value)} style={{ width: 120 }} />
              </div>
              <button type="submit" disabled={busy || universe.length === 0}>
                {busy ? "Calibrating…" : "Start game"}
              </button>
            </div>
            {universe.length > 0 && (
              <div className="form-row" style={{ marginTop: 8 }}>
                {universe.map((s) => (
                  <span key={s} className="badge">
                    {s}{" "}
                    <button type="button" className="ghost" style={{ padding: "0 4px" }}
                      onClick={() => setUniverse(universe.filter((u) => u !== s))}>
                      ×
                    </button>
                  </span>
                ))}
              </div>
            )}
            <p className="muted" style={{ marginTop: 8 }}>
              Each stock's simulated future is calibrated to its real past year
              (drift + volatility), starts at its real current price, and is
              deterministic — reopening the game replays the same future. Up to
              12 symbols, 10 simulated years.
            </p>
            {error && <div className="error">{error}</div>}
          </form>
        </>
      )}

      {view && (
        <>
          <div className="form-row" style={{ marginBottom: 12 }}>
            <button className="ghost" onClick={() => { setView(null); refresh(); }}>
              ← All games
            </button>
            <span style={{ flex: 1 }} />
            <button className="ghost" onClick={abandon}>Abandon game</button>
          </div>
          <div className="cards-row">
            <div className="card stat">
              <div className="label">Virtual date</div>
              <div className="value">{view.virtual_date}</div>
              <div className="sub">{view.years_elapsed} simulated years elapsed</div>
            </div>
            <div className="card stat">
              <div className="label">Game value (simulated)</div>
              <div className="value">{fmtMoney(view.value)}</div>
              <div className="sub">cash {fmtMoney(view.cash)}</div>
            </div>
            <div className="card stat">
              <div className="label">Return</div>
              <div className={`value ${pnlClass(view.return_pct)}`}>
                {Number(view.return_pct).toFixed(2)}%
              </div>
              <div className="sub">since game start</div>
            </div>
          </div>

          <div className="card">
            <div className="form-row">
              <strong>Fast-forward time:</strong>
              {ADVANCES.map((a) => (
                <button key={a.days} disabled={busy} onClick={() => advance(a.days)}>
                  {a.label}
                </button>
              ))}
              {busy && <span className="muted">Simulating…</span>}
            </div>
          </div>

          {error && <div className="error">{error}</div>}

          <div className="card">
            <h2>Game value over simulated time</h2>
            <ValueChart points={view.value_points} />
            <div className="muted">SIMULATED prices — not real market data.</div>
          </div>

          <form className="card" onSubmit={trade}>
            <h2>Trade (at simulated prices)</h2>
            <div className="form-row">
              <div className="field">
                <label htmlFor="ft-sym">Symbol</label>
                <select id="ft-sym" value={tSymbol} onChange={(e) => setTSymbol(e.target.value)}>
                  {view.symbols.map((s) => <option key={s}>{s}</option>)}
                </select>
              </div>
              <div className="field">
                <label htmlFor="ft-side">Side</label>
                <select id="ft-side" value={tSide} onChange={(e) => setTSide(e.target.value)}>
                  <option>BUY</option>
                  <option>SELL</option>
                </select>
              </div>
              <div className="field">
                <label htmlFor="ft-mode">Size by</label>
                <select id="ft-mode" value={tMode}
                  onChange={(e) => setTMode(e.target.value as "quantity" | "notional")}>
                  <option value="notional">Amount ($)</option>
                  <option value="quantity">Shares</option>
                </select>
              </div>
              <div className="field">
                <label htmlFor="ft-amt">{tMode === "notional" ? "Amount" : "Shares"}</label>
                <input id="ft-amt" type="number" step="any" min="0" value={tAmount}
                  onChange={(e) => setTAmount(e.target.value)} required style={{ width: 110 }} />
              </div>
              <button type="submit" disabled={busy}>{tSide === "BUY" ? "Buy" : "Sell"}</button>
              {tradeMsg && <span className="gain">{tradeMsg}</span>}
            </div>
          </form>

          <div className="card">
            <h2>Simulated quotes</h2>
            <table>
              <thead>
                <tr>
                  <th>Symbol</th>
                  <th className="num">Price (sim)</th>
                  <th className="num">Day change</th>
                  <th className="num">Since start</th>
                </tr>
              </thead>
              <tbody>
                {view.symbols.map((s) => {
                  const q = view.quotes[s];
                  const day = q.prev_close
                    ? ((Number(q.price) / Number(q.prev_close)) - 1) * 100 : null;
                  const total = ((Number(q.price) / Number(q.start_price)) - 1) * 100;
                  return (
                    <tr key={s}>
                      <td>{s}</td>
                      <td className="num">{fmtMoney(q.price)}</td>
                      <td className={`num ${day !== null ? pnlClass(String(day)) : ""}`}>
                        {day !== null ? `${day.toFixed(2)}%` : "—"}
                      </td>
                      <td className={`num ${pnlClass(String(total))}`}>
                        {total.toFixed(2)}%
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>

          {view.holdings.length > 0 && (
            <div className="card">
              <h2>Holdings</h2>
              <table>
                <thead>
                  <tr><th>Symbol</th><th className="num">Shares</th>
                    <th className="num">Value (sim)</th></tr>
                </thead>
                <tbody>
                  {view.holdings.map((h) => (
                    <tr key={h.symbol}>
                      <td>{h.symbol}</td>
                      <td className="num">{h.quantity}</td>
                      <td className="num">{fmtMoney(h.market_value)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </>
      )}
    </div>
  );
}
