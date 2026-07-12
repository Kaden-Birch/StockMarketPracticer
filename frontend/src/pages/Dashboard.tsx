import { FormEvent, useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api, fmtMoney, pnlClass, PortfolioView } from "../api";
import { useEvents } from "../hooks/useEvents";

export default function Dashboard() {
  const [portfolios, setPortfolios] = useState<PortfolioView[]>([]);
  const [name, setName] = useState("");
  const [balance, setBalance] = useState("10000");
  const [method, setMethod] = useState("FIFO");
  const [error, setError] = useState("");
  const [loaded, setLoaded] = useState(false);

  const refresh = useCallback(() => {
    api
      .listPortfolios()
      .then((p) => {
        setPortfolios(p);
        setLoaded(true);
      })
      .catch((e: Error) => setError(e.message));
  }, []);

  useEffect(refresh, [refresh]);
  useEvents((type) => {
    if (type === "order_filled") refresh();
  });

  async function create(e: FormEvent) {
    e.preventDefault();
    setError("");
    try {
      await api.createPortfolio({
        name,
        starting_balance: balance,
        cost_basis_method: method,
      });
      setName("");
      refresh();
    } catch (err) {
      setError((err as Error).message);
    }
  }

  const totals = portfolios.reduce(
    (acc, p) => ({
      value: acc.value + Number(p.total_value),
      day: acc.day + Number(p.day_change),
      lifetime: acc.lifetime + Number(p.lifetime_return),
    }),
    { value: 0, day: 0, lifetime: 0 },
  );

  return (
    <div>
      <h1>Dashboard</h1>

      {portfolios.length > 0 && (
        <div className="cards-row">
          <div className="card stat">
            <div className="label">Total value</div>
            <div className="value">{fmtMoney(String(totals.value))}</div>
          </div>
          <div className="card stat">
            <div className="label">Day change</div>
            <div className={`value ${pnlClass(String(totals.day))}`}>
              {fmtMoney(String(totals.day))}
            </div>
          </div>
          <div className="card stat">
            <div className="label">Lifetime return</div>
            <div className={`value ${pnlClass(String(totals.lifetime))}`}>
              {fmtMoney(String(totals.lifetime))}
            </div>
          </div>
        </div>
      )}

      <div className="card">
        <h2>Portfolios</h2>
        {loaded && portfolios.length === 0 && (
          <p className="muted">No portfolios yet — create your first one below.</p>
        )}
        {portfolios.length > 0 && (
          <table>
            <thead>
              <tr>
                <th>Name</th>
                <th className="num">Cash</th>
                <th className="num">Market value</th>
                <th className="num">Total value</th>
                <th className="num">Day</th>
                <th className="num">Lifetime</th>
              </tr>
            </thead>
            <tbody>
              {portfolios.map((p) => (
                <tr key={p.id}>
                  <td>
                    <Link to={`/portfolios/${p.id}`}>{p.name}</Link>
                  </td>
                  <td className="num">{fmtMoney(p.cash_balance, p.currency)}</td>
                  <td className="num">{fmtMoney(p.market_value, p.currency)}</td>
                  <td className="num">{fmtMoney(p.total_value, p.currency)}</td>
                  <td className={`num ${pnlClass(p.day_change)}`}>
                    {fmtMoney(p.day_change, p.currency)}
                  </td>
                  <td className={`num ${pnlClass(p.lifetime_return)}`}>
                    {fmtMoney(p.lifetime_return, p.currency)}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      <form className="card" onSubmit={create}>
        <h2>New portfolio</h2>
        <div className="form-row">
          <div className="field">
            <label htmlFor="pf-name">Name</label>
            <input
              id="pf-name"
              value={name}
              onChange={(e) => setName(e.target.value)}
              required
              placeholder="My first portfolio"
            />
          </div>
          <div className="field">
            <label htmlFor="pf-balance">Starting balance ($)</label>
            <input
              id="pf-balance"
              type="number"
              min="1"
              step="any"
              value={balance}
              onChange={(e) => setBalance(e.target.value)}
              required
            />
          </div>
          <div className="field">
            <label htmlFor="pf-method">Cost basis</label>
            <select id="pf-method" value={method} onChange={(e) => setMethod(e.target.value)}>
              <option>FIFO</option>
              <option>LIFO</option>
              <option>AVERAGE</option>
            </select>
          </div>
          <button type="submit">Create</button>
        </div>
        {error && <div className="error">{error}</div>}
      </form>
    </div>
  );
}
