import { FormEvent, useCallback, useEffect, useState } from "react";
import { api, fmtMoney, RecurringPlan } from "../api";

export default function PlansCard({ portfolioId, currency }: { portfolioId: string; currency: string }) {
  const [plans, setPlans] = useState<RecurringPlan[]>([]);
  const [symbol, setSymbol] = useState("");
  const [amount, setAmount] = useState("100");
  const [cadence, setCadence] = useState("MONTHLY");
  const [error, setError] = useState("");

  const refresh = useCallback(() => {
    api.listPlans(portfolioId).then(setPlans).catch((e: Error) => setError(e.message));
  }, [portfolioId]);
  useEffect(refresh, [refresh]);

  async function create(e: FormEvent) {
    e.preventDefault();
    setError("");
    try {
      await api.createPlan(portfolioId, { symbol, amount, cadence });
      setSymbol("");
      refresh();
    } catch (err) {
      setError((err as Error).message);
    }
  }

  async function toggle(plan: RecurringPlan) {
    await api.updatePlan(portfolioId, plan.id, { enabled: !plan.enabled });
    refresh();
  }

  async function remove(plan: RecurringPlan) {
    await api.deletePlan(portfolioId, plan.id);
    refresh();
  }

  return (
    <div className="card">
      <h2>Recurring purchases (DCA)</h2>
      {plans.length > 0 && (
        <table>
          <thead>
            <tr>
              <th>Symbol</th>
              <th className="num">Amount</th>
              <th>Cadence</th>
              <th>Next run</th>
              <th className="num">Runs</th>
              <th>Status</th>
              <th></th>
            </tr>
          </thead>
          <tbody>
            {plans.map((p) => (
              <tr key={p.id}>
                <td>{p.symbol}</td>
                <td className="num">{fmtMoney(p.amount, currency)}</td>
                <td>{p.cadence}</td>
                <td className="muted">{new Date(p.next_run_at + (p.next_run_at.endsWith("Z") ? "" : "Z")).toLocaleString()}</td>
                <td className="num">{p.run_count}</td>
                <td>
                  <span className={`badge ${p.enabled ? "FILLED" : "CANCELLED"}`}>
                    {p.enabled ? "ACTIVE" : "PAUSED"}
                  </span>
                </td>
                <td style={{ whiteSpace: "nowrap" }}>
                  <button className="ghost" onClick={() => toggle(p)}>
                    {p.enabled ? "Pause" : "Resume"}
                  </button>{" "}
                  <button className="ghost" onClick={() => remove(p)}>Delete</button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
      <form className="form-row" onSubmit={create} style={{ marginTop: plans.length ? 12 : 0 }}>
        <div className="field">
          <label htmlFor="plan-symbol">Symbol</label>
          <input id="plan-symbol" value={symbol} required style={{ width: 100 }}
            onChange={(e) => setSymbol(e.target.value.toUpperCase())} />
        </div>
        <div className="field">
          <label htmlFor="plan-amount">Amount per purchase</label>
          <input id="plan-amount" type="number" step="any" min="1" value={amount} required
            style={{ width: 120 }} onChange={(e) => setAmount(e.target.value)} />
        </div>
        <div className="field">
          <label htmlFor="plan-cadence">Cadence</label>
          <select id="plan-cadence" value={cadence} onChange={(e) => setCadence(e.target.value)}>
            <option value="DAILY">Daily</option>
            <option value="WEEKLY">Weekly</option>
            <option value="MONTHLY">Monthly</option>
          </select>
        </div>
        <button type="submit">Add plan</button>
      </form>
      <div className="muted" style={{ marginTop: 8 }}>
        First purchase executes within a minute of creation, then on the cadence. Runs 24/7 in
        server mode.
      </div>
      {error && <div className="error">{error}</div>}
    </div>
  );
}
