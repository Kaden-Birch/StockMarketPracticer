import { useEffect, useState } from "react";
import { useParams } from "react-router-dom";
import { api, fmtMoney, pnlClass, SharedPortfolioView, SharedStrategyView } from "../api";

/** Public, read-only share view (roadmap 7.6). Rendered OUTSIDE the auth
 * gate — the backend endpoint is auth-exempt and anonymized. */
export default function SharedPage() {
  const { token = "" } = useParams();
  const [data, setData] = useState<SharedPortfolioView | SharedStrategyView | null>(null);
  const [error, setError] = useState("");
  useEffect(() => {
    api.sharedView(token).then(setData).catch((e: Error) => setError(e.message));
  }, [token]);

  return (
    <main className="content" style={{ margin: "6vh auto", maxWidth: 720 }}>
      <div className="brand" style={{ marginBottom: 16 }}>AIPTP</div>
      {error && <div className="error">{error === "Share link not found"
        ? "This share link does not exist or was revoked." : error}</div>}
      {data?.kind === "portfolio" && <SharedPortfolio view={data} />}
      {data?.kind === "strategy" && <SharedStrategy view={data} />}
      <p className="muted" style={{ marginTop: 16 }}>
        Shared read-only from AIPTP — a paper-trading simulator. Simulated
        funds; real market data. Not financial advice.
      </p>
    </main>
  );
}

function SharedPortfolio({ view }: { view: SharedPortfolioView }) {
  return (
    <div className="card">
      <h1>{view.name}</h1>
      <p className="muted">
        Simulated portfolio · started at {fmtMoney(view.starting_balance, view.currency)} ·{" "}
        {new Date(view.created_at).toLocaleDateString()}
      </p>
      <div style={{ display: "flex", gap: 24, flexWrap: "wrap", margin: "12px 0" }}>
        <div>
          <div className="muted">Total value</div>
          <strong>{fmtMoney(view.total_value, view.currency)}</strong>
        </div>
        <div>
          <div className="muted">Total return</div>
          <strong className={pnlClass(view.lifetime_return)}>
            {view.total_return_pct === null ? "—" : `${Number(view.total_return_pct).toFixed(2)}%`}
          </strong>
        </div>
        <div>
          <div className="muted">Day change</div>
          <strong className={pnlClass(view.day_change)}>
            {fmtMoney(view.day_change, view.currency)}
          </strong>
        </div>
      </div>
      {view.holdings.length > 0 && (
        <table>
          <thead>
            <tr><th>Symbol</th><th>Quantity</th><th>Market value</th></tr>
          </thead>
          <tbody>
            {view.holdings.map((h) => (
              <tr key={h.symbol}>
                <td>{h.symbol}</td>
                <td>{h.quantity}</td>
                <td>{fmtMoney(h.market_value, view.currency)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
      {view.holdings.length === 0 && <p className="muted">All cash right now.</p>}
    </div>
  );
}

function SharedStrategy({ view }: { view: SharedStrategyView }) {
  return (
    <div className="card">
      <h1>{view.name}</h1>
      {view.description && <p className="muted">{view.description}</p>}
      <p>
        <strong>Universe:</strong> {view.universe.join(", ")} ·{" "}
        <strong>Benchmark:</strong> {view.benchmark} ·{" "}
        <strong>Entry size:</strong> {fmtMoney(view.entry_notional)}
      </p>
      <h3>Entry trigger</h3>
      <pre style={{ overflowX: "auto" }}>{JSON.stringify(view.entry_trigger, null, 2)}</pre>
      {view.exit_trigger && (
        <>
          <h3>Exit trigger</h3>
          <pre style={{ overflowX: "auto" }}>{JSON.stringify(view.exit_trigger, null, 2)}</pre>
        </>
      )}
      <p className="muted">
        Sign in to AIPTP and import this strategy from the share dialog to
        backtest it yourself.
      </p>
    </div>
  );
}
