import { useState } from "react";
import { api, fmtMoney, PortfolioView, RebalancePlan } from "../api";

export default function RebalanceCard({
  portfolio,
  onExecuted,
}: {
  portfolio: PortfolioView;
  onExecuted: () => void;
}) {
  const [targets, setTargets] = useState<Record<string, string>>(() =>
    Object.fromEntries(portfolio.holdings.map((h) => [h.symbol, ""])),
  );
  const [newSymbol, setNewSymbol] = useState("");
  const [plan, setPlan] = useState<RebalancePlan | null>(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  function numericTargets(): Record<string, number> {
    return Object.fromEntries(
      Object.entries(targets)
        .filter(([, v]) => v !== "" && !isNaN(Number(v)))
        .map(([k, v]) => [k, Number(v)]),
    );
  }

  async function preview() {
    setError("");
    setBusy(true);
    try {
      const res = await api.rebalance(portfolio.id, numericTargets(), false);
      setPlan(res.plan);
    } catch (e) {
      setError((e as Error).message);
      setPlan(null);
    } finally {
      setBusy(false);
    }
  }

  async function execute() {
    setError("");
    setBusy(true);
    try {
      await api.rebalance(portfolio.id, numericTargets(), true);
      setPlan(null);
      onExecuted();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  const totalPct = Object.values(numericTargets()).reduce((a, b) => a + b, 0);

  return (
    <div className="card">
      <h2>Rebalance</h2>
      <div className="form-row">
        {Object.keys(targets).map((symbol) => (
          <div className="field" key={symbol}>
            <label htmlFor={`rb-${symbol}`}>{symbol} %</label>
            <input
              id={`rb-${symbol}`}
              type="number" step="any" min="0" max="100"
              value={targets[symbol]}
              onChange={(e) => setTargets({ ...targets, [symbol]: e.target.value })}
              style={{ width: 80 }}
            />
          </div>
        ))}
        <div className="field">
          <label htmlFor="rb-new">Add symbol</label>
          <input
            id="rb-new" value={newSymbol} placeholder="MSFT" style={{ width: 90 }}
            onChange={(e) => setNewSymbol(e.target.value.toUpperCase())}
            onKeyDown={(e) => {
              if (e.key === "Enter" && newSymbol) {
                e.preventDefault();
                setTargets({ ...targets, [newSymbol]: "" });
                setNewSymbol("");
              }
            }}
          />
        </div>
        <button className="ghost" onClick={preview} disabled={busy || totalPct <= 0} type="button">
          Preview
        </button>
      </div>
      <div className="muted" style={{ marginTop: 6 }}>
        Targets total {totalPct.toFixed(1)}% — the remainder stays in cash.
      </div>
      {error && <div className="error">{error}</div>}
      {plan && (
        <div style={{ marginTop: 12 }}>
          {plan.trades.length === 0 ? (
            <p className="muted">Already balanced — no trades needed.</p>
          ) : (
            <>
              <table>
                <thead>
                  <tr>
                    <th>Symbol</th><th>Side</th><th className="num">Est. value</th>
                  </tr>
                </thead>
                <tbody>
                  {plan.trades.map((t, i) => (
                    <tr key={i}>
                      <td>{t.symbol}</td>
                      <td className={t.side === "BUY" ? "gain" : "loss"}>{t.side}</td>
                      <td className="num">{fmtMoney(t.est_value, portfolio.currency)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
              <button onClick={execute} disabled={busy} style={{ marginTop: 10 }} type="button">
                Execute rebalance
              </button>
            </>
          )}
        </div>
      )}
    </div>
  );
}
