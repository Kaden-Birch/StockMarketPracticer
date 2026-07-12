import { FormEvent, useState } from "react";
import { api } from "../api";

interface Props {
  portfolioId: string;
  defaultSymbol?: string;
  onPlaced: () => void;
}

export default function OrderTicket({ portfolioId, defaultSymbol = "", onPlaced }: Props) {
  const [symbol, setSymbol] = useState(defaultSymbol);
  const [side, setSide] = useState("BUY");
  const [type, setType] = useState("MARKET");
  const [sizing, setSizing] = useState<"quantity" | "notional">("quantity");
  const [quantity, setQuantity] = useState("");
  const [notional, setNotional] = useState("");
  const [limitPrice, setLimitPrice] = useState("");
  const [stopPrice, setStopPrice] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  const needsLimit = type === "LIMIT" || type === "STOP_LIMIT";
  const needsStop = type === "STOP" || type === "STOP_LIMIT";
  const notionalAllowed = type === "MARKET" && side === "BUY";

  async function submit(e: FormEvent) {
    e.preventDefault();
    setError("");
    setBusy(true);
    try {
      const useNotional = sizing === "notional" && notionalAllowed;
      await api.placeOrder(portfolioId, {
        symbol,
        side,
        type,
        quantity: useNotional ? null : quantity || null,
        notional: useNotional ? notional || null : null,
        limit_price: needsLimit ? limitPrice || null : null,
        stop_price: needsStop ? stopPrice || null : null,
      });
      setQuantity("");
      setNotional("");
      onPlaced();
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <form className="card" onSubmit={submit}>
      <h2>Place order</h2>
      <div className="form-row">
        <div className="field">
          <label htmlFor="ot-symbol">Symbol</label>
          <input
            id="ot-symbol"
            value={symbol}
            onChange={(e) => setSymbol(e.target.value.toUpperCase())}
            required
            style={{ width: 100 }}
          />
        </div>
        <div className="field">
          <label htmlFor="ot-side">Side</label>
          <select id="ot-side" value={side} onChange={(e) => setSide(e.target.value)}>
            <option>BUY</option>
            <option>SELL</option>
          </select>
        </div>
        <div className="field">
          <label htmlFor="ot-type">Type</label>
          <select id="ot-type" value={type} onChange={(e) => setType(e.target.value)}>
            <option value="MARKET">Market</option>
            <option value="LIMIT">Limit</option>
            <option value="STOP">Stop</option>
            <option value="STOP_LIMIT">Stop Limit</option>
          </select>
        </div>
        {notionalAllowed && (
          <div className="field">
            <label htmlFor="ot-sizing">Size by</label>
            <select
              id="ot-sizing"
              value={sizing}
              onChange={(e) => setSizing(e.target.value as "quantity" | "notional")}
            >
              <option value="quantity">Shares</option>
              <option value="notional">Amount ($)</option>
            </select>
          </div>
        )}
        {sizing === "notional" && notionalAllowed ? (
          <div className="field">
            <label htmlFor="ot-notional">Amount</label>
            <input
              id="ot-notional"
              type="number"
              step="any"
              min="0"
              value={notional}
              onChange={(e) => setNotional(e.target.value)}
              required
              style={{ width: 110 }}
            />
          </div>
        ) : (
          <div className="field">
            <label htmlFor="ot-qty">Shares</label>
            <input
              id="ot-qty"
              type="number"
              step="any"
              min="0"
              value={quantity}
              onChange={(e) => setQuantity(e.target.value)}
              required
              style={{ width: 110 }}
            />
          </div>
        )}
        {needsLimit && (
          <div className="field">
            <label htmlFor="ot-limit">Limit price</label>
            <input
              id="ot-limit"
              type="number"
              step="any"
              min="0"
              value={limitPrice}
              onChange={(e) => setLimitPrice(e.target.value)}
              required
              style={{ width: 110 }}
            />
          </div>
        )}
        {needsStop && (
          <div className="field">
            <label htmlFor="ot-stop">Stop price</label>
            <input
              id="ot-stop"
              type="number"
              step="any"
              min="0"
              value={stopPrice}
              onChange={(e) => setStopPrice(e.target.value)}
              required
              style={{ width: 110 }}
            />
          </div>
        )}
        <button type="submit" disabled={busy}>
          {busy ? "Placing…" : `${side === "BUY" ? "Buy" : "Sell"} ${symbol || ""}`}
        </button>
      </div>
      {error && <div className="error">{error}</div>}
      <div className="muted" style={{ marginTop: 8 }}>
        Simulated trading with real market prices — no real money is involved.
      </div>
    </form>
  );
}
