import { FormEvent, useCallback, useEffect, useRef, useState } from "react";
import { api, BacktestResults, BacktestRunView, fmtMoney, pnlClass, StrategyView } from "../api";
import MultiLineChart from "../components/MultiLineChart";

type CondType = "price" | "pct_move" | "indicator";

interface CondRow {
  type: CondType;
  op: string;
  value: string;
  name: string;
  period: string;
}

const emptyCond = (): CondRow => ({ type: "price", op: "<", value: "", name: "RSI", period: "14" });

function condToNode(c: CondRow): object {
  if (c.type === "indicator") {
    return { indicator: { symbol: "$SYMBOL", name: c.name, period: Number(c.period),
                          op: c.op, value: Number(c.value) } };
  }
  return { [c.type]: { symbol: "$SYMBOL", op: c.op, value: Number(c.value) } };
}

function CondEditor({ label, conds, setConds }: {
  label: string;
  conds: CondRow[];
  setConds: (c: CondRow[]) => void;
}) {
  const set = (i: number, patch: Partial<CondRow>) =>
    setConds(conds.map((c, j) => (j === i ? { ...c, ...patch } : c)));
  return (
    <div style={{ marginBottom: 8 }}>
      <div className="muted" style={{ marginBottom: 4 }}>{label} (each symbol in the universe)</div>
      {conds.map((c, i) => (
        <div className="form-row" key={i} style={{ marginBottom: 6 }}>
          <select value={c.type} onChange={(e) => set(i, { type: e.target.value as CondType })}>
            <option value="price">Price</option>
            <option value="pct_move">% move (day)</option>
            <option value="indicator">Indicator</option>
          </select>
          {c.type === "indicator" && (
            <>
              <select value={c.name} onChange={(e) => set(i, { name: e.target.value })}>
                <option>RSI</option><option>SMA</option><option>EMA</option>
              </select>
              <input type="number" min="1" value={c.period} style={{ width: 70 }}
                title="Period" onChange={(e) => set(i, { period: e.target.value })} />
            </>
          )}
          <select value={c.op} onChange={(e) => set(i, { op: e.target.value })}>
            <option value="<">&lt;</option><option value="<=">&le;</option>
            <option value=">">&gt;</option><option value=">=">&ge;</option>
          </select>
          <input type="number" step="any" value={c.value} required style={{ width: 100 }}
            onChange={(e) => set(i, { value: e.target.value })} />
          {conds.length > 1 && (
            <button type="button" className="ghost"
              onClick={() => setConds(conds.filter((_, j) => j !== i))}>×</button>
          )}
        </div>
      ))}
      <button type="button" className="ghost" onClick={() => setConds([...conds, emptyCond()])}>
        + AND condition
      </button>
    </div>
  );
}

function ResultsView({ r }: { r: BacktestResults }) {
  const series = [
    { label: "Strategy", points: r.equity_curve.map((p) => ({
        ts: Math.floor(new Date(p.date + "T00:00:00Z").getTime() / 1000),
        value: Math.round((p.value / Number(r.initial_cash)) * 10000) / 100 })) },
    { label: r.benchmark, points: r.equity_curve.map((p) => ({
        ts: Math.floor(new Date(p.date + "T00:00:00Z").getTime() / 1000),
        value: Math.round((p.benchmark_close / r.equity_curve[0].benchmark_close) * 10000) / 100 })) },
  ];
  return (
    <div>
      <div className="cards-row">
        <div className="card stat">
          <div className="label">Total return</div>
          <div className={`value ${pnlClass(String(r.total_return_pct))}`}>{r.total_return_pct}%</div>
          <div className="sub">{r.benchmark}: {r.benchmark_return_pct}%</div>
        </div>
        <div className="card stat">
          <div className="label">Final value</div>
          <div className="value">{fmtMoney(String(r.final_value))}</div>
          <div className="sub">from {fmtMoney(r.initial_cash)}</div>
        </div>
        <div className="card stat">
          <div className="label">Win rate</div>
          <div className="value">{r.win_rate !== null ? `${r.win_rate}%` : "—"}</div>
          <div className="sub">{r.wins}W / {r.losses}L of {r.closed_trades} closed</div>
        </div>
        <div className="card stat">
          <div className="label">Max drawdown</div>
          <div className="value loss">{r.risk.max_drawdown ?? "—"}%</div>
        </div>
        <div className="card stat">
          <div className="label">Sharpe</div>
          <div className="value">{r.risk.sharpe ?? "—"}</div>
          <div className="sub">Sortino {r.risk.sortino ?? "—"} · β {r.risk.beta ?? "—"}</div>
        </div>
      </div>
      <div className="card">
        <h2>Equity curve (indexed to 100)</h2>
        <MultiLineChart series={series} height={300} />
      </div>
      <div className="cards-row">
        <div className="card" style={{ flex: 1 }}>
          <h2>By market condition</h2>
          <table>
            <thead><tr><th>Regime</th><th className="num">Days</th><th className="num">Return</th></tr></thead>
            <tbody>
              {Object.entries(r.by_regime).map(([name, v]) => (
                <tr key={name}>
                  <td style={{ textTransform: "capitalize" }}>{name}</td>
                  <td className="num">{v.days}</td>
                  <td className={`num ${v.total_return_pct !== null ? pnlClass(String(v.total_return_pct)) : ""}`}>
                    {v.total_return_pct !== null ? `${v.total_return_pct}%` : "—"}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        {r.open_positions.length > 0 && (
          <div className="card" style={{ flex: 1 }}>
            <h2>Open at end</h2>
            <table>
              <thead><tr><th>Symbol</th><th className="num">Shares</th><th className="num">Value</th></tr></thead>
              <tbody>
                {r.open_positions.map((p) => (
                  <tr key={p.symbol}>
                    <td>{p.symbol}</td><td className="num">{p.quantity}</td>
                    <td className="num">{fmtMoney(p.value)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
      {r.trade_log.length > 0 && (
        <div className="card">
          <h2>Trade log ({r.trades} trades)</h2>
          <table>
            <thead>
              <tr><th>Date</th><th>Side</th><th>Symbol</th><th className="num">Shares</th>
                  <th className="num">Price</th><th className="num">Realized</th></tr>
            </thead>
            <tbody>
              {r.trade_log.slice(-100).map((t, i) => (
                <tr key={i}>
                  <td className="muted">{t.date}</td>
                  <td className={t.side === "BUY" ? "gain" : "loss"}>{t.side}</td>
                  <td>{t.symbol}</td>
                  <td className="num">{t.quantity}</td>
                  <td className="num">{fmtMoney(t.price)}</td>
                  <td className={`num ${t.realized_pnl ? pnlClass(t.realized_pnl) : ""}`}>
                    {t.realized_pnl ? fmtMoney(t.realized_pnl) : "—"}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

export default function StrategiesPage() {
  const [strategies, setStrategies] = useState<StrategyView[]>([]);
  const [run, setRun] = useState<BacktestRunView | null>(null);
  const [running, setRunning] = useState(false);
  const [error, setError] = useState("");
  const [shareUrl, setShareUrl] = useState("");
  const pollRef = useRef<number>();

  // builder
  const [name, setName] = useState("");
  const [universe, setUniverse] = useState("AAPL, MSFT, NVDA");
  const [entry, setEntry] = useState<CondRow[]>([
    { type: "indicator", op: "<", value: "35", name: "RSI", period: "14" },
  ]);
  const [useExit, setUseExit] = useState(true);
  const [exit, setExit] = useState<CondRow[]>([
    { type: "indicator", op: ">", value: "65", name: "RSI", period: "14" },
  ]);
  const [notional, setNotional] = useState("1000");
  const [cash, setCash] = useState("10000");
  const [range, setRange] = useState("1Y");

  const refresh = useCallback(() => {
    api.listStrategies().then(setStrategies).catch((e: Error) => setError(e.message));
  }, []);
  useEffect(refresh, [refresh]);
  useEffect(() => () => window.clearInterval(pollRef.current), []);

  async function create(e: FormEvent) {
    e.preventDefault();
    setError("");
    const toAst = (rows: CondRow[]) => {
      const nodes = rows.map(condToNode);
      return nodes.length === 1 ? nodes[0] : { all: nodes };
    };
    try {
      await api.createStrategy({
        name,
        universe: universe.split(/[\s,]+/).filter(Boolean),
        entry_trigger: toAst(entry),
        exit_trigger: useExit ? toAst(exit) : null,
        entry_notional: notional,
        initial_cash: cash,
      });
      setName("");
      refresh();
    } catch (err) {
      setError((err as Error).message);
    }
  }

  async function backtest(strategyId: string) {
    setError("");
    setRun(null);
    setRunning(true);
    try {
      const { run_id } = await api.startBacktest(strategyId, range);
      window.clearInterval(pollRef.current);
      pollRef.current = window.setInterval(async () => {
        const r = await api.getBacktest(run_id);
        setRun(r);
        if (r.status !== "RUNNING") {
          window.clearInterval(pollRef.current);
          setRunning(false);
          if (r.status === "FAILED") setError(`Backtest failed: ${r.error}`);
        }
      }, 500);
    } catch (err) {
      setError((err as Error).message);
      setRunning(false);
    }
  }

  return (
    <div>
      <h1>Strategies</h1>
      {error && <div className="error">{error}</div>}
      {shareUrl && (
        <p className="muted">
          Read-only link (copied): <code>{shareUrl}</code>{" "}
          <button className="ghost" onClick={() => setShareUrl("")}>Dismiss</button>
        </p>
      )}

      <div className="card">
        <h2>Your strategies</h2>
        {strategies.length === 0 && <p className="muted">No strategies yet — build one below.</p>}
        {strategies.map((s) => (
          <div key={s.id} className="form-row"
            style={{ borderBottom: "1px solid var(--border)", padding: "8px 0", alignItems: "center" }}>
            <strong>{s.name}</strong>
            <span className="muted">
              {s.universe.join(", ")} · {fmtMoney(s.entry_notional)} per entry ·
              start {fmtMoney(s.initial_cash)}
            </span>
            <span style={{ flex: 1 }} />
            <select value={range} onChange={(e) => setRange(e.target.value)}>
              <option>6M</option><option>1Y</option><option>2Y</option><option>5Y</option>
            </select>
            <button disabled={running} onClick={() => backtest(s.id)}>
              {running ? "Running…" : "Backtest"}
            </button>
            <button className="ghost" title="Create a public read-only link others can import from"
              onClick={async () => {
                try {
                  const link = await api.shareStrategy(s.id);
                  const url = `${window.location.origin}/shared/${link.token}`;
                  setShareUrl(url);
                  await navigator.clipboard?.writeText(url).catch(() => undefined);
                } catch (e) {
                  setError((e as Error).message);
                }
              }}>
              Share
            </button>
            <button className="ghost"
              onClick={async () => {
                if (window.confirm(`Delete strategy "${s.name}"?`)) {
                  await api.deleteStrategy(s.id);
                  refresh();
                }
              }}>
              Delete
            </button>
          </div>
        ))}
      </div>

      {run && run.status === "RUNNING" && (
        <div className="card">Backtesting… {run.progress_pct}%</div>
      )}
      {run && run.status === "DONE" && Object.keys(run.results).length > 0 && (
        <ResultsView r={run.results as BacktestResults} />
      )}

      <form className="card" onSubmit={create}>
        <h2>New strategy</h2>
        <div className="form-row" style={{ marginBottom: 10 }}>
          <div className="field">
            <label htmlFor="st-name">Name</label>
            <input id="st-name" value={name} required style={{ width: 200 }}
              onChange={(e) => setName(e.target.value)} placeholder="RSI mean reversion" />
          </div>
          <div className="field" style={{ flex: 1 }}>
            <label htmlFor="st-universe">Universe (symbols)</label>
            <input id="st-universe" value={universe} style={{ width: "100%" }}
              onChange={(e) => setUniverse(e.target.value.toUpperCase())} />
          </div>
          <div className="field">
            <label htmlFor="st-notional">$ per entry</label>
            <input id="st-notional" type="number" min="1" value={notional} style={{ width: 100 }}
              onChange={(e) => setNotional(e.target.value)} />
          </div>
          <div className="field">
            <label htmlFor="st-cash">Starting cash</label>
            <input id="st-cash" type="number" min="1" value={cash} style={{ width: 110 }}
              onChange={(e) => setCash(e.target.value)} />
          </div>
        </div>
        <CondEditor label="Enter when" conds={entry} setConds={setEntry} />
        <div style={{ margin: "10px 0" }}>
          <button type="button" className={`ghost ${useExit ? "active" : ""}`}
            onClick={() => setUseExit(!useExit)}>
            {useExit ? "Exit rule: ON" : "Exit rule: OFF (hold to end)"}
          </button>
        </div>
        {useExit && <CondEditor label="Exit when" conds={exit} setConds={setExit} />}
        <button type="submit" style={{ marginTop: 8 }}>Create strategy</button>
        <div className="muted" style={{ marginTop: 8 }}>
          Backtests replay real daily bars through the exact same rule evaluation and
          order/accounting engine used for live trading.
        </div>
      </form>
    </div>
  );
}
