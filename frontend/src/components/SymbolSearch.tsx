import { useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { api, SymbolMatch } from "../api";

export default function SymbolSearch() {
  const [query, setQuery] = useState("");
  const [results, setResults] = useState<SymbolMatch[]>([]);
  const navigate = useNavigate();
  const timer = useRef<number>();

  useEffect(() => {
    window.clearTimeout(timer.current);
    if (query.trim().length < 1) {
      setResults([]);
      return;
    }
    timer.current = window.setTimeout(() => {
      api.search(query).then(setResults).catch(() => setResults([]));
    }, 250);
    return () => window.clearTimeout(timer.current);
  }, [query]);

  return (
    <div style={{ position: "relative" }}>
      <input
        placeholder="Search companies (e.g. AAPL, Nvidia)…"
        value={query}
        onChange={(e) => setQuery(e.target.value)}
        aria-label="Search companies"
        style={{ width: 320 }}
      />
      {results.length > 0 && (
        <div className="search-results">
          {results.map((m) => (
            <div
              key={m.symbol}
              onClick={() => {
                setQuery("");
                setResults([]);
                navigate(`/companies/${m.symbol}`);
              }}
            >
              <strong>{m.symbol}</strong> — {m.name}{" "}
              <span className="muted">{m.exchange}</span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
