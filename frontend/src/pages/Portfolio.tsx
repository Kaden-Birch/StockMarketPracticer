import { useCallback, useEffect, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { api, fmtMoney, Order, pnlClass, PortfolioView, Txn } from "../api";
import OrderTicket from "../components/OrderTicket";
import PlansCard from "../components/PlansCard";
import RebalanceCard from "../components/RebalanceCard";
import { useEvents } from "../hooks/useEvents";

export default function PortfolioPage() {
  const { id = "" } = useParams();
  const navigate = useNavigate();
  const [portfolio, setPortfolio] = useState<PortfolioView | null>(null);
  const [orders, setOrders] = useState<Order[]>([]);
  const [txns, setTxns] = useState<Txn[]>([]);
  const [error, setError] = useState("");

  const refresh = useCallback(() => {
    Promise.all([api.getPortfolio(id), api.listOrders(id), api.listTransactions(id)])
      .then(([p, o, t]) => {
        setPortfolio(p);
        setOrders(o);
        setTxns(t);
      })
      .catch((e: Error) => setError(e.message));
  }, [id]);

  useEffect(refresh, [refresh]);
  useEvents((type, data) => {
    const d = data as { portfolio_id?: string };
    if (type === "order_filled" && d.portfolio_id === id) refresh();
    if (type === "quotes") refresh();
  });

  async function cancel(orderId: string) {
    try {
      await api.cancelOrder(id, orderId);
      refresh();
    } catch (e) {
      setError((e as Error).message);
    }
  }

  async function closePosition(symbol: string, quantity: string) {
    if (!window.confirm(`Sell all ${quantity} ${symbol} at market?`)) return;
    try {
      await api.placeOrder(id, { symbol, side: "SELL", type: "MARKET", quantity });
      refresh();
    } catch (e) {
      setError((e as Error).message);
    }
  }

  async function toggleReinvest() {
    if (!portfolio) return;
    await api.updatePortfolio(id, { dividend_reinvest: !portfolio.dividend_reinvest });
    refresh();
  }

  async function remove() {
    if (!window.confirm(`Delete portfolio "${portfolio?.name}"? This cannot be undone.`)) return;
    await api.deletePortfolio(id);
    navigate("/");
  }

  if (error && !portfolio) return <div className="error">{error}</div>;
  if (!portfolio) return <div className="muted">Loading…</div>;

  const pending = orders.filter((o) => o.status === "PENDING");
  const doneOrders = orders.filter((o) => o.status !== "PENDING").slice(0, 20);

  return (
    <div>
      <div style={{ display: "flex", alignItems: "center", gap: 12, flexWrap: "wrap" }}>
        <h1 style={{ marginBottom: 0 }}>{portfolio.name}</h1>
        <span style={{ flex: 1 }} />
        <Link to={`/portfolios/${id}/analytics`}>
          <button className="ghost" type="button">Analytics</button>
        </Link>
        <a href={api.exportUrl(id, "csv")} download>
          <button className="ghost" type="button">CSV</button>
        </a>
        <a href={api.exportUrl(id, "json")} download>
          <button className="ghost" type="button">JSON</button>
        </a>
        <a href={api.exportUrl(id, "md")} download>
          <button className="ghost" type="button">Markdown</button>
        </a>
        <button className="ghost" type="button" onClick={toggleReinvest}
          title="Automatically reinvest cash dividends into the paying stock">
          Dividend reinvest: {portfolio.dividend_reinvest ? "ON" : "OFF"}
        </button>
      </div>
      <div style={{ height: 12 }} />
      {portfolio.quote_errors.length > 0 && (
        <div className="error">Some quotes unavailable: {portfolio.quote_errors.join("; ")}</div>
      )}

      <div className="cards-row">
        <div className="card stat">
          <div className="label">Total value</div>
          <div className="value">{fmtMoney(portfolio.total_value, portfolio.currency)}</div>
          <div className="sub">started at {fmtMoney(portfolio.starting_balance, portfolio.currency)}</div>
        </div>
        <div className="card stat">
          <div className="label">Cash</div>
          <div className="value">{fmtMoney(portfolio.cash_balance, portfolio.currency)}</div>
        </div>
        <div className="card stat">
          <div className="label">Unrealized P&L</div>
          <div className={`value ${pnlClass(portfolio.unrealized_pnl)}`}>
            {fmtMoney(portfolio.unrealized_pnl, portfolio.currency)}
          </div>
        </div>
        <div className="card stat">
          <div className="label">Day change</div>
          <div className={`value ${pnlClass(portfolio.day_change)}`}>
            {fmtMoney(portfolio.day_change, portfolio.currency)}
          </div>
        </div>
        <div className="card stat">
          <div className="label">Lifetime return</div>
          <div className={`value ${pnlClass(portfolio.lifetime_return)}`}>
            {fmtMoney(portfolio.lifetime_return, portfolio.currency)}
          </div>
          <div className="sub">{portfolio.cost_basis_method} cost basis</div>
        </div>
      </div>

      <div className="card">
        <h2>Holdings</h2>
        {portfolio.holdings.length === 0 ? (
          <p className="muted">No positions yet.</p>
        ) : (
          <table>
            <thead>
              <tr>
                <th>Symbol</th>
                <th className="num">Shares</th>
                <th className="num">Avg cost</th>
                <th className="num">Price</th>
                <th className="num">Market value</th>
                <th className="num">Unrealized</th>
                <th className="num">Day</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              {portfolio.holdings.map((h) => (
                <tr key={h.symbol}>
                  <td>
                    <Link to={`/companies/${h.symbol}`}>{h.symbol}</Link>
                  </td>
                  <td className="num">{h.quantity}</td>
                  <td className="num">{fmtMoney(h.avg_cost, portfolio.currency)}</td>
                  <td className="num">{fmtMoney(h.price, portfolio.currency)}</td>
                  <td className="num">{fmtMoney(h.market_value, portfolio.currency)}</td>
                  <td className={`num ${pnlClass(h.unrealized_pnl)}`}>
                    {fmtMoney(h.unrealized_pnl, portfolio.currency)}
                  </td>
                  <td className={`num ${pnlClass(h.day_change)}`}>
                    {fmtMoney(h.day_change, portfolio.currency)}
                  </td>
                  <td>
                    <button className="ghost" onClick={() => closePosition(h.symbol, h.quantity)}>
                      Close
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      <OrderTicket portfolioId={id} onPlaced={refresh} />
      {error && <div className="error">{error}</div>}
      <PlansCard portfolioId={id} currency={portfolio.currency} />
      <RebalanceCard key={portfolio.holdings.map((h) => h.symbol).join(",")}
        portfolio={portfolio} onExecuted={refresh} />

      {pending.length > 0 && (
        <div className="card">
          <h2>Pending orders</h2>
          <table>
            <thead>
              <tr>
                <th>Symbol</th>
                <th>Side</th>
                <th>Type</th>
                <th className="num">Shares</th>
                <th className="num">Limit</th>
                <th className="num">Stop</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              {pending.map((o) => (
                <tr key={o.id}>
                  <td>{o.symbol}</td>
                  <td>{o.side}</td>
                  <td>{o.type}</td>
                  <td className="num">{o.quantity ?? o.notional}</td>
                  <td className="num">{fmtMoney(o.limit_price, portfolio.currency)}</td>
                  <td className="num">{fmtMoney(o.stop_price, portfolio.currency)}</td>
                  <td>
                    <button className="ghost" onClick={() => cancel(o.id)}>
                      Cancel
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {doneOrders.length > 0 && (
        <div className="card">
          <h2>Recent orders</h2>
          <table>
            <thead>
              <tr>
                <th>Placed</th>
                <th>Symbol</th>
                <th>Side</th>
                <th>Type</th>
                <th className="num">Shares</th>
                <th>Status</th>
              </tr>
            </thead>
            <tbody>
              {doneOrders.map((o) => (
                <tr key={o.id}>
                  <td className="muted">{new Date(o.created_at).toLocaleString()}</td>
                  <td>{o.symbol}</td>
                  <td>{o.side}</td>
                  <td>{o.type}</td>
                  <td className="num">{o.quantity ?? o.notional}</td>
                  <td>
                    <span className={`badge ${o.status}`}>{o.status}</span>
                    {o.reject_reason && <span className="muted"> {o.reject_reason}</span>}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      <div className="card">
        <h2>Transactions</h2>
        {txns.length === 0 ? (
          <p className="muted">No transactions yet.</p>
        ) : (
          <table>
            <thead>
              <tr>
                <th>Executed</th>
                <th>Symbol</th>
                <th>Side</th>
                <th className="num">Shares</th>
                <th className="num">Price</th>
                <th className="num">Amount</th>
                <th className="num">Realized P&L</th>
                <th>Origin</th>
              </tr>
            </thead>
            <tbody>
              {txns.map((t) => (
                <tr key={t.id}>
                  <td className="muted">{new Date(t.executed_at).toLocaleString()}</td>
                  <td>{t.symbol}</td>
                  <td className={t.kind !== "TRADE" ? "" : t.side === "BUY" ? "gain" : "loss"}>
                    {t.kind === "TRADE" ? t.side : t.kind}
                  </td>
                  <td className="num">{t.quantity}</td>
                  <td className="num">{fmtMoney(t.price, portfolio.currency)}</td>
                  <td className="num">{fmtMoney(t.amount, portfolio.currency)}</td>
                  <td className={`num ${pnlClass(t.realized_pnl)}`}>
                    {fmtMoney(t.realized_pnl, portfolio.currency)}
                  </td>
                  <td>
                    <span className="badge">{t.origin}</span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      <button className="danger" onClick={remove}>
        Delete portfolio
      </button>
    </div>
  );
}
