import { useEffect, useState } from "react";
import { useParams } from "react-router-dom";
import { api, fmtMoney, pnlClass, PortfolioView, QuoteView } from "../api";
import OrderTicket from "../components/OrderTicket";
import PriceChart from "../components/PriceChart";
import SymbolSearch from "../components/SymbolSearch";

type Profile = Record<string, string | number | null>;
interface NewsItem {
  title: string;
  publisher: string;
  link: string;
  published_at: number | null;
}

const STAT_FIELDS: { key: string; label: string }[] = [
  { key: "market_cap", label: "Market cap" },
  { key: "trailing_pe", label: "P/E (trailing)" },
  { key: "forward_pe", label: "P/E (forward)" },
  { key: "dividend_yield", label: "Dividend yield" },
  { key: "beta", label: "Beta" },
  { key: "fifty_two_week_high", label: "52-week high" },
  { key: "fifty_two_week_low", label: "52-week low" },
  { key: "employees", label: "Employees" },
];

export default function CompanyPage() {
  const { symbol = "" } = useParams();
  const sym = symbol.toUpperCase();
  const [quote, setQuote] = useState<QuoteView | null>(null);
  const [error, setError] = useState("");
  const [profile, setProfile] = useState<Profile | null>(null);
  const [news, setNews] = useState<NewsItem[]>([]);
  const [portfolios, setPortfolios] = useState<PortfolioView[]>([]);
  const [portfolioId, setPortfolioId] = useState("");
  const [showTrade, setShowTrade] = useState(false);
  const [aiSummary, setAiSummary] = useState("");
  const [aiError, setAiError] = useState("");
  const [aiBusy, setAiBusy] = useState(false);
  const [placed, setPlaced] = useState("");

  useEffect(() => {
    setQuote(null);
    setError("");
    setProfile(null);
    setNews([]);
    setAiSummary("");
    setAiError("");
    setPlaced("");
    api
      .quotes([sym])
      .then((q) => setQuote(q[sym] ?? null))
      .catch((e: Error) => setError(e.message));
    api.companyProfile(sym).then(setProfile).catch(() => setProfile(null));
    api.companyNews(sym).then(setNews).catch(() => setNews([]));
    // research XP for reviewing a company (server-capped per day)
    api.gamifyEvent("company_viewed", sym).catch(() => undefined);
  }, [sym]);

  useEffect(() => {
    api
      .listPortfolios()
      .then((ps) => {
        setPortfolios(ps);
        setPortfolioId((cur) => cur || ps[0]?.id || "");
      })
      .catch(() => setPortfolios([]));
  }, []);

  function runAiSummary() {
    setAiBusy(true);
    setAiError("");
    api
      .companySummary(sym)
      .then((r) => setAiSummary(r.summary))
      .catch((e: Error) => setAiError(e.message))
      .finally(() => setAiBusy(false));
  }

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
      <div style={{ display: "flex", alignItems: "baseline", gap: 16, flexWrap: "wrap" }}>
        <h1 style={{ marginBottom: 8 }}>{sym}</h1>
        {profile?.sector && (
          <span className="muted">
            {String(profile.sector)}
            {profile.industry ? ` · ${String(profile.industry)}` : ""}
          </span>
        )}
        <span style={{ flex: 1 }} />
        {portfolios.length > 0 && (
          <button onClick={() => setShowTrade(!showTrade)}>
            {showTrade ? "Hide trade panel" : `Trade ${sym}`}
          </button>
        )}
      </div>
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
      {showTrade && portfolios.length > 0 && (
        <div style={{ marginBottom: 16 }}>
          <div className="form-row" style={{ marginBottom: 8 }}>
            <div className="field">
              <label htmlFor="cp-portfolio">Portfolio</label>
              <select
                id="cp-portfolio"
                value={portfolioId}
                onChange={(e) => setPortfolioId(e.target.value)}
              >
                {portfolios.map((p) => (
                  <option key={p.id} value={p.id}>{p.name}</option>
                ))}
              </select>
            </div>
            {placed && <span className="gain">{placed}</span>}
          </div>
          {portfolioId && (
            <OrderTicket
              key={`${portfolioId}:${sym}`}
              portfolioId={portfolioId}
              defaultSymbol={sym}
              onPlaced={() => setPlaced("Order placed ✓")}
            />
          )}
        </div>
      )}
      <div className="card">
        <PriceChart symbol={sym} />
      </div>
      <div className="card">
        <div style={{ display: "flex", alignItems: "baseline", gap: 12 }}>
          <h2>AI performance summary</h2>
          <button className="ghost" onClick={runAiSummary} disabled={aiBusy}>
            {aiBusy ? "Writing…" : aiSummary ? "Regenerate" : "Generate"}
          </button>
        </div>
        {aiError && <div className="error">{aiError}</div>}
        {aiSummary ? (
          <p style={{ whiteSpace: "pre-wrap" }}>{aiSummary}</p>
        ) : (
          !aiError && (
            <p className="muted">
              A local AI model writes a plain-language recap of the stock's real
              recent performance — computed statistics only, never invented
              numbers. Requires a loaded model (AI Models page).
            </p>
          )
        )}
      </div>
      {profile && (
        <div className="card">
          <h2>Company profile</h2>
          {profile.summary && <p>{String(profile.summary)}</p>}
          <div className="cards-row">
            {STAT_FIELDS.filter((f) => profile[f.key] !== null && profile[f.key] !== undefined)
              .map((f) => (
                <div className="card stat" key={f.key}>
                  <div className="label">{f.label}</div>
                  <div className="value" style={{ fontSize: "1.1rem" }}>
                    {typeof profile[f.key] === "number"
                      ? Number(profile[f.key]).toLocaleString()
                      : String(profile[f.key])}
                  </div>
                </div>
              ))}
          </div>
          {profile.website && (
            <div className="muted" style={{ marginTop: 8 }}>
              {profile.country ? `${String(profile.country)} · ` : ""}
              <a href={String(profile.website)} target="_blank" rel="noreferrer">
                {String(profile.website)}
              </a>
            </div>
          )}
        </div>
      )}
      {news.length > 0 && (
        <div className="card">
          <h2>Recent news</h2>
          <ul style={{ paddingLeft: 18, margin: 0 }}>
            {news.map((n, i) => (
              <li key={i} style={{ marginBottom: 8 }}>
                <a href={n.link} target="_blank" rel="noreferrer">{n.title}</a>
                <div className="muted">
                  {n.publisher}
                  {n.published_at
                    ? ` · ${new Date(n.published_at * 1000).toLocaleDateString()}`
                    : ""}
                </div>
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}
