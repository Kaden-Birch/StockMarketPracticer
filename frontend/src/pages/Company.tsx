import { useEffect, useState } from "react";
import { useParams } from "react-router-dom";
import { api, fmtMoney, pnlClass, QuoteView } from "../api";
import PriceChart from "../components/PriceChart";
import SymbolSearch from "../components/SymbolSearch";

export default function CompanyPage() {
  const { symbol = "" } = useParams();
  const [quote, setQuote] = useState<QuoteView | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    setQuote(null);
    setError("");
    api
      .quotes([symbol])
      .then((q) => setQuote(q[symbol.toUpperCase()] ?? null))
      .catch((e: Error) => setError(e.message));
    // research XP for reviewing a company (server-capped per day)
    api.gamifyEvent("company_viewed", symbol.toUpperCase()).catch(() => undefined);
  }, [symbol]);

  const change =
    quote && quote.previous_close
      ? Number(quote.price) - Number(quote.previous_close)
      : null;
  const changePct =
    change !== null && quote?.previous_close
      ? (change / Number(quote.previous_close)) * 100
      : null;

  return (
    <div>
      <div style={{ marginBottom: 16 }}>
        <SymbolSearch />
      </div>
      <h1>{symbol.toUpperCase()}</h1>
      {error && <div className="error">{error}</div>}
      {quote && (
        <div className="cards-row">
          <div className="card stat">
            <div className="label">Price ({quote.currency})</div>
            <div className="value">{fmtMoney(quote.price, quote.currency)}</div>
            <div className="sub">
              {quote.market_state !== "UNKNOWN" && `${quote.market_state} · `}
              as of {new Date(quote.as_of).toLocaleString()} · {quote.provider}
            </div>
          </div>
          {change !== null && (
            <div className="card stat">
              <div className="label">Change today</div>
              <div className={`value ${pnlClass(String(change))}`}>
                {fmtMoney(String(change), quote.currency)}{" "}
                {changePct !== null && `(${changePct.toFixed(2)}%)`}
              </div>
              <div className="sub">
                previous close {fmtMoney(quote.previous_close, quote.currency)}
              </div>
            </div>
          )}
        </div>
      )}
      <div className="card">
        <PriceChart symbol={symbol.toUpperCase()} />
      </div>
    </div>
  );
}
