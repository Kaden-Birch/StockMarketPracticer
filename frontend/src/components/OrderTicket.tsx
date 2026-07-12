import { FormEvent, useState } from "react";
import { api } from "../api";

interface Props {
  portfolioId: string;
  defaultSymbol?: string;
  onPlaced: () => void;
}

type Sizing = "quantity" | "notional" | "pct_cash" | "pct_portfolio" | "pct_position";

export default function OrderTicket({ portfolioId, defaultSymbol = "", onPlaced }: Props) {
  const [symbol, setSymbol] = useState(defaultSymbol);
  const [side, setSide] = useState("BUY");
  const [type, setType] = useState("MARKET");
  const [sizing, setSizing] = useState<Sizing>("quantity");
  const [quantity, setQuantity] = useState("");
  const [notional, setNotional] = useState("");
  const [percent, setPercent] = useState("");
  const [limitPrice, setLimitPrice] = useState("");
  const [stopPrice, setStopPrice] = useState("");
  const [trailMode, setTrailMode] = useState<"percent" | "amount">("percent");
  const [trail, setTrail] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  const needsLimit = type === "LIMIT" || type === "STOP_LIMIT";
  const needsStop = type === "STOP" || type === "STOP_LIMIT";
  const isTrailing = type === "TRAILING_STOP";

  const sizingOptions: { value: Sizing; label: string; show: boolean }[] = [
    { value: "quantity", label: "Shares", show: true },
    { value: "notional", label: "Amount ($)", show: type === "MARKET" && side === "BUY" },
    { value: "pct_cash", label: "% of cash", show: type === "MARKET" && side === "BUY" },
    { value: "pct_portfolio", label: "% of portfolio", show: type === "MARKET" && side === "BUY" },
    { value: "pct_position", label: "% of position", show: side === "SELL" && !isTrailing },
  ];
  const visibleSizing = sizingOptions.filter((o) => o.show);
  const effectiveSizing = visibleSizing.some((o) => o.value === sizing) ? sizing : "quantity";
  const usesPercent = effectiveSizing.startsWith("pct_");

  async function submit(e: FormEvent) {
    e.preventDefault();
    setError("");
    setBusy(true);
    try {
      const percentOf =
        effectiveSizing === "pct_cash" ? "CASH"
        : effectiveSizing === "pct_portfolio" ? "PORTFOLIO"
        : effectiveSizing === "pct_position" ? "POSITION"
        : null;
      await api.placeOrder(portfolioId, {
        symbol,
        side,
        type,
        quantity: effectiveSizing === "quantity" ? quantity || null : null,
        notional: effectiveSizing === "notional" ? notional || null : null,
        percent: usesPercent ? percent || null : null,
        percent_of: percentOf,
        limit_price: needsLimit ? limitPrice || null : null,
        stop_price: needsStop ? stopPrice || null : null,
        trail_amount: isTrailing && trailMode === "amount" ? trail || null : null,
        trail_percent: isTrailing && trailMode === "percent" ? trail || null : null,
      });
      setQuantity("");
      setNotional("");
      setPercent("");
      setTrail("");
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
            <option value="TRAILING_STOP">Trailing Stop</option>
          </select>
        </div>
        {visibleSizing.length > 1 && (
          <div className="field">
            <label htmlFor="ot-sizing">Size by</label>
            <select
              id="ot-sizing"
              value={effectiveSizing}
              onChange={(e) => setSizing(e.target.value as Sizing)}
            >
              {visibleSizing.map((o) => (
                <option key={o.value} value={o.value}>{o.label}</option>
              ))}
            </select>
          </div>
        )}
        {effectiveSizing === "quantity" && (
          <div className="field">
            <label htmlFor="ot-qty">Shares</label>
            <input id="ot-qty" type="number" step="any" min="0" value={quantity}
              onChange={(e) => setQuantity(e.target.value)} required style={{ width: 100 }} />
          </div>
        )}
        {effectiveSizing === "notional" && (
          <div className="field">
            <label htmlFor="ot-notional">Amount</label>
            <input id="ot-notional" type="number" step="any" min="0" value={notional}
              onChange={(e) => setNotional(e.target.value)} required style={{ width: 100 }} />
          </div>
        )}
        {usesPercent && (
          <div className="field">
            <label htmlFor="ot-pct">Percent</label>
            <input id="ot-pct" type="number" step="any" min="0" max="100" value={percent}
              onChange={(e) => setPercent(e.target.value)} required style={{ width: 90 }} />
          </div>
        )}
        {needsLimit && (
          <div className="field">
            <label htmlFor="ot-limit">Limit price</label>
            <input id="ot-limit" type="number" step="any" min="0" value={limitPrice}
              onChange={(e) => setLimitPrice(e.target.value)} required style={{ width: 100 }} />
          </div>
        )}
        {needsStop && (
          <div className="field">
            <label htmlFor="ot-stop">Stop price</label>
            <input id="ot-stop" type="number" step="any" min="0" value={stopPrice}
              onChange={(e) => setStopPrice(e.target.value)} required style={{ width: 100 }} />
          </div>
        )}
        {isTrailing && (
          <>
            <div className="field">
              <label htmlFor="ot-trailmode">Trail by</label>
              <select id="ot-trailmode" value={trailMode}
                onChange={(e) => setTrailMode(e.target.value as "percent" | "amount")}>
                <option value="percent">Percent</option>
                <option value="amount">Amount ($)</option>
              </select>
            </div>
            <div className="field">
              <label htmlFor="ot-trail">{trailMode === "percent" ? "Trail %" : "Trail $"}</label>
              <input id="ot-trail" type="number" step="any" min="0" value={trail}
                onChange={(e) => setTrail(e.target.value)} required style={{ width: 90 }} />
            </div>
          </>
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
