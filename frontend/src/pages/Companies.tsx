import { useEffect, useState } from "react";
import { api, PortfolioView } from "../api";
import OrderTicket from "../components/OrderTicket";
import SymbolSearch from "../components/SymbolSearch";

export default function CompaniesPage() {
  const [portfolios, setPortfolios] = useState<PortfolioView[]>([]);
  const [portfolioId, setPortfolioId] = useState("");
  const [placed, setPlaced] = useState("");

  useEffect(() => {
    api
      .listPortfolios()
      .then((ps) => {
        setPortfolios(ps);
        setPortfolioId((cur) => cur || ps[0]?.id || "");
      })
      .catch(() => setPortfolios([]));
  }, []);

  return (
    <div>
      <h1>Companies</h1>
      <div className="card">
        <h2>Find a company</h2>
        <SymbolSearch />
        <p className="muted" style={{ marginTop: 12 }}>
          Search any listed company or ticker to open its dashboard with live
          pricing and interactive charts.
        </p>
      </div>
      {portfolios.length > 0 && portfolioId && (
        <>
          <div className="form-row" style={{ marginBottom: 8 }}>
            <div className="field">
              <label htmlFor="co-portfolio">Trade into portfolio</label>
              <select
                id="co-portfolio"
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
          <OrderTicket
            key={portfolioId}
            portfolioId={portfolioId}
            onPlaced={() => setPlaced("Order placed ✓")}
          />
        </>
      )}
    </div>
  );
}
