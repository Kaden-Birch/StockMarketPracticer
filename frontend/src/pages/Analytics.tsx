import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { Analytics, api, fmtMoney, pnlClass, PortfolioView, ValueHistory } from "../api";
import ValueChart from "../components/ValueChart";
import { useChartRange } from "../chartSync";

const RANGES = ["1M", "3M", "6M", "1Y", "5Y", "MAX"];

function Tile({ label, value, sub, cls }: { label: string; value: string; sub?: string; cls?: string }) {
  return (
    <div className="card stat">
      <div className="label">{label}</div>
      <div className={`value ${cls ?? ""}`}>{value}</div>
      {sub && <div className="sub">{sub}</div>}
    </div>
  );
}

export default function AnalyticsPage() {
  const { id = "" } = useParams();
  const [portfolio, setPortfolio] = useState<PortfolioView | null>(null);
  const [history, setHistory] = useState<ValueHistory | null>(null);
  const [analytics, setAnalytics] = useState<Analytics | null>(null);
  const [range, setRange, sync, setSync] = useChartRange("1Y");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    api.getPortfolio(id).then(setPortfolio).catch((e: Error) => setError(e.message));
    api.gamifyEvent("analytics_reviewed", "", id).catch(() => undefined);
  }, [id]);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    const effective = range === "1D" || range === "5D" ? "1M" : range;
    Promise.all([api.valueHistory(id, effective), api.analytics(id, effective)])
      .then(([h, a]) => {
        if (!cancelled) {
          setHistory(h);
          setAnalytics(a);
          setError("");
        }
      })
      .catch((e: Error) => !cancelled && setError(e.message))
      .finally(() => !cancelled && setLoading(false));
    return () => {
      cancelled = true;
    };
  }, [id, range]);

  const currency = portfolio?.currency ?? "USD";
  const records = analytics?.records;
  const risk = analytics?.risk;
  const div = analytics?.diversification;

  return (
    <div>
      <h1>
        Analytics{portfolio && <> — <Link to={`/portfolios/${id}`}>{portfolio.name}</Link></>}
      </h1>
      {error && <div className="error">{error}</div>}

      <div className="card">
        <h2>Portfolio value</h2>
        <div className="range-row" role="tablist" aria-label="Analytics range">
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
        {loading && <p className="muted">Reconstructing value history…</p>}
        {history && history.points.length > 0 && <ValueChart points={history.points} />}
        {history && history.points.length === 0 && !loading && (
          <p className="muted">No history yet — place some trades first.</p>
        )}
        {history && (
          <div className="muted">
            Reconstructed from the transaction log and real daily prices · benchmark{" "}
            {history.benchmark}
          </div>
        )}
      </div>

      {risk && !risk.error && (
        <>
          <h2 style={{ margin: "20px 0 10px" }}>Risk ({range})</h2>
          <div className="cards-row">
            <Tile label="Sharpe ratio" value={risk.sharpe?.toFixed(2) ?? "—"} />
            <Tile label="Sortino ratio" value={risk.sortino?.toFixed(2) ?? "—"} />
            <Tile label={`Beta vs ${history?.benchmark ?? "SPY"}`} value={risk.beta?.toFixed(2) ?? "—"} />
            <Tile label="Volatility (ann.)" value={risk.volatility !== null ? `${risk.volatility}%` : "—"} />
            <Tile label="Max drawdown" value={risk.max_drawdown !== null ? `${risk.max_drawdown}%` : "—"}
              cls={risk.max_drawdown && risk.max_drawdown < 0 ? "loss" : ""} />
            <Tile label="Diversification" value={div?.score !== null && div ? `${div.score}` : "—"}
              sub="0 concentrated · 100 spread" />
          </div>
        </>
      )}

      {records && (
        <>
          <h2 style={{ margin: "20px 0 10px" }}>Records (lifetime)</h2>
          <div className="cards-row">
            <Tile label="Best investment"
              value={records.best_symbol ? records.best_symbol.symbol : "—"}
              sub={records.best_symbol ? fmtMoney(records.best_symbol.realized_pnl, currency) + " realized" : "no closed trades yet"}
              cls={records.best_symbol ? pnlClass(records.best_symbol.realized_pnl) : ""} />
            <Tile label="Worst investment"
              value={records.worst_symbol ? records.worst_symbol.symbol : "—"}
              sub={records.worst_symbol ? fmtMoney(records.worst_symbol.realized_pnl, currency) + " realized" : ""}
              cls={records.worst_symbol ? pnlClass(records.worst_symbol.realized_pnl) : ""} />
            <Tile label="Win rate"
              value={records.win_rate !== null ? `${records.win_rate}%` : "—"}
              sub={`${records.closed_trades} closed trades`} />
            <Tile label="Avg holding period"
              value={records.avg_holding_days !== null ? `${records.avg_holding_days} days` : "—"} />
            <Tile label="Avg trade return"
              value={records.avg_trip_return !== null ? `${records.avg_trip_return}%` : "—"}
              cls={records.avg_trip_return !== null ? pnlClass(String(records.avg_trip_return)) : ""} />
          </div>
        </>
      )}

      {div && Object.keys(div.weights).length > 0 && (
        <div className="card" style={{ marginTop: 16 }}>
          <h2>Allocation</h2>
          <table>
            <thead>
              <tr><th>Asset</th><th className="num">Weight</th></tr>
            </thead>
            <tbody>
              {Object.entries(div.weights)
                .sort((a, b) => b[1] - a[1])
                .map(([asset, weight]) => (
                  <tr key={asset}>
                    <td>{asset === "CASH" ? "Cash" : <Link to={`/companies/${asset}`}>{asset}</Link>}</td>
                    <td className="num">{weight}%</td>
                  </tr>
                ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
