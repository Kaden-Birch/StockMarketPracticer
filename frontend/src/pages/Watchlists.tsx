import { FormEvent, useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api, fmtMoney, pnlClass, WatchlistView } from "../api";

export default function WatchlistsPage() {
  const [lists, setLists] = useState<WatchlistView[]>([]);
  const [name, setName] = useState("");
  const [addSymbol, setAddSymbol] = useState<Record<string, string>>({});
  const [error, setError] = useState("");
  const [loaded, setLoaded] = useState(false);

  const refresh = useCallback(() => {
    api
      .listWatchlists()
      .then((l) => {
        setLists(l);
        setLoaded(true);
      })
      .catch((e: Error) => setError(e.message));
  }, []);
  useEffect(refresh, [refresh]);

  async function create(e: FormEvent) {
    e.preventDefault();
    setError("");
    try {
      await api.createWatchlist(name);
      setName("");
      refresh();
    } catch (err) {
      setError((err as Error).message);
    }
  }

  async function addItem(listId: string) {
    const symbol = (addSymbol[listId] || "").trim();
    if (!symbol) return;
    setError("");
    try {
      await api.addWatchlistItem(listId, symbol);
      setAddSymbol({ ...addSymbol, [listId]: "" });
      refresh();
    } catch (err) {
      setError((err as Error).message);
    }
  }

  return (
    <div>
      <h1>Watchlists</h1>
      {error && <div className="error">{error}</div>}
      {loaded && lists.length === 0 && (
        <p className="muted">No watchlists yet — create one below.</p>
      )}
      {lists.map((wl) => (
        <div className="card" key={wl.id}>
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
            <h2>{wl.name}</h2>
            <button
              className="ghost"
              onClick={async () => {
                if (window.confirm(`Delete watchlist "${wl.name}"?`)) {
                  await api.deleteWatchlist(wl.id);
                  refresh();
                }
              }}
            >
              Delete list
            </button>
          </div>
          {wl.quote_errors.length > 0 && (
            <div className="error">Some quotes unavailable: {wl.quote_errors.join("; ")}</div>
          )}
          {wl.items.length > 0 && (
            <table>
              <thead>
                <tr>
                  <th>Symbol</th>
                  <th className="num">Price</th>
                  <th className="num">Change</th>
                  <th className="num">Change %</th>
                  <th></th>
                </tr>
              </thead>
              <tbody>
                {wl.items.map((item) => (
                  <tr key={item.symbol}>
                    <td>
                      <Link to={`/companies/${item.symbol}`}>{item.symbol}</Link>
                    </td>
                    <td className="num">
                      {fmtMoney(item.price, item.currency ?? "USD")}
                    </td>
                    <td className={`num ${pnlClass(item.change)}`}>
                      {fmtMoney(item.change, item.currency ?? "USD")}
                    </td>
                    <td className={`num ${pnlClass(item.change_pct)}`}>
                      {item.change_pct !== null ? `${item.change_pct}%` : "—"}
                    </td>
                    <td>
                      <button
                        className="ghost"
                        onClick={async () => {
                          await api.removeWatchlistItem(wl.id, item.symbol);
                          refresh();
                        }}
                      >
                        Remove
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
          <div className="form-row" style={{ marginTop: 10 }}>
            <div className="field">
              <label htmlFor={`add-${wl.id}`}>Add symbol</label>
              <input
                id={`add-${wl.id}`}
                value={addSymbol[wl.id] || ""}
                onChange={(e) =>
                  setAddSymbol({ ...addSymbol, [wl.id]: e.target.value.toUpperCase() })
                }
                onKeyDown={(e) => {
                  if (e.key === "Enter") {
                    e.preventDefault();
                    addItem(wl.id);
                  }
                }}
                placeholder="AAPL"
                style={{ width: 110 }}
              />
            </div>
            <button className="ghost" type="button" onClick={() => addItem(wl.id)}>
              Add
            </button>
          </div>
        </div>
      ))}
      <form className="card" onSubmit={create}>
        <h2>New watchlist</h2>
        <div className="form-row">
          <div className="field">
            <label htmlFor="wl-name">Name</label>
            <input
              id="wl-name"
              value={name}
              onChange={(e) => setName(e.target.value)}
              required
              placeholder="Tech giants"
            />
          </div>
          <button type="submit">Create</button>
        </div>
      </form>
    </div>
  );
}
