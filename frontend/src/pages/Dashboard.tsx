import { FormEvent, useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api, fmtMoney, pnlClass, PortfolioView } from "../api";
import NetWorthChart from "../components/NetWorthChart";
import { useEvents } from "../hooks/useEvents";

interface GameInfo {
  id: string | null;
  name: string;
  portfolios: number;
}

export default function Dashboard() {
  const [portfolios, setPortfolios] = useState<PortfolioView[]>([]);
  const [games, setGames] = useState<GameInfo[]>([]);
  // "" = everything; "none" = ungrouped only; otherwise a game id
  const [activeGame, setActiveGame] = useState("");
  const [newGameName, setNewGameName] = useState("");
  const [addingGame, setAddingGame] = useState(false);
  const [name, setName] = useState("");
  const [balance, setBalance] = useState("10000");
  const [method, setMethod] = useState("FIFO");
  const [mode, setMode] = useState("CLASSIC");
  const [preset, setPreset] = useState("ACADEMY");
  const [error, setError] = useState("");
  const [loaded, setLoaded] = useState(false);

  const refresh = useCallback(() => {
    api
      .listPortfolios(activeGame)
      .then((p) => {
        setPortfolios(p);
        setLoaded(true);
      })
      .catch((e: Error) => setError(e.message));
    api.listGames().then(setGames).catch(() => setGames([]));
  }, [activeGame]);

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
        mode,
        preset,
        game_id: activeGame && activeGame !== "none" ? activeGame : null,
      });
      setName("");
      refresh();
    } catch (err) {
      setError((err as Error).message);
    }
  }

  async function addGame(e: FormEvent) {
    e.preventDefault();
    if (!newGameName.trim()) return;
    try {
      const g = await api.createGame(newGameName.trim());
      setNewGameName("");
      setAddingGame(false);
      setActiveGame(g.id);
    } catch (err) {
      setError((err as Error).message);
    }
  }

  async function removeGame(id: string) {
    if (!window.confirm("Delete this game? Its portfolios stay and become ungrouped.")) return;
    try {
      await api.deleteGame(id);
      setActiveGame("");
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

  const hasGames = games.some((g) => g.id !== null);
  const activeGameName = games.find((g) => g.id === activeGame)?.name;

  return (
    <div>
      <h1>Dashboard</h1>

      {(hasGames || addingGame) && (
        <div className="range-row" role="tablist" aria-label="Games"
          style={{ marginBottom: 12 }}>
          <button className={`ghost ${activeGame === "" ? "active" : ""}`}
            onClick={() => setActiveGame("")} role="tab"
            aria-selected={activeGame === ""}>
            All
          </button>
          {games.map((g) => (
            <button key={g.id ?? "none"}
              className={`ghost ${activeGame === (g.id ?? "none") ? "active" : ""}`}
              onClick={() => setActiveGame(g.id ?? "none")} role="tab"
              aria-selected={activeGame === (g.id ?? "none")}
              title={`${g.portfolios} portfolio${g.portfolios === 1 ? "" : "s"}`}>
              {g.name} ({g.portfolios})
            </button>
          ))}
          {addingGame ? (
            <form onSubmit={addGame} style={{ display: "flex", gap: 6 }}>
              <input value={newGameName} autoFocus placeholder="Game name"
                onChange={(e) => setNewGameName(e.target.value)} style={{ width: 160 }} />
              <button type="submit">Add</button>
              <button type="button" className="ghost"
                onClick={() => setAddingGame(false)}>Cancel</button>
            </form>
          ) : (
            <button className="ghost" onClick={() => setAddingGame(true)}
              title="Games are isolated spaces — group portfolios into separate worlds that don't mix">
              + New game
            </button>
          )}
          {activeGame && activeGame !== "none" && (
            <button className="ghost" onClick={() => removeGame(activeGame)}
              title="Delete this game (portfolios survive, ungrouped)">
              🗑 Delete game
            </button>
          )}
        </div>
      )}
      {!hasGames && !addingGame && (
        <p className="muted" style={{ marginTop: -8 }}>
          <button className="ghost" onClick={() => setAddingGame(true)}>+ New game</button>{" "}
          — create isolated spaces that group portfolios into separate worlds.
        </p>
      )}

      {portfolios.length > 0 && (
        <div className="cards-row">
          <div className="card stat">
            <div className="label">
              Total value{activeGameName ? ` — ${activeGameName}` : ""}
            </div>
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

      {portfolios.length > 0 && (
        <NetWorthChart gameId={activeGame === "none" ? "" : activeGame} />
      )}

      <div className="card">
        <h2>Portfolios{activeGameName ? ` — ${activeGameName}` : ""}</h2>
        {loaded && portfolios.length === 0 && (
          <p className="muted">No portfolios here yet — create one below.</p>
        )}
        {portfolios.length > 0 && (
          <table>
            <thead>
              <tr>
                <th>Name</th>
                {activeGame === "" && hasGames && <th>Game</th>}
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
                  {activeGame === "" && hasGames && (
                    <td className="muted">
                      {games.find((g) => g.id === p.game_id)?.name ?? "—"}
                    </td>
                  )}
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
        <h2>New portfolio{activeGameName ? ` in ${activeGameName}` : ""}</h2>
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
          <div className="field">
            <label htmlFor="pf-mode">Mode</label>
            <select id="pf-mode" value={mode} onChange={(e) => setMode(e.target.value)}
              title="Beginner adds guidance; Expert skips all tutorials. Nothing is ever locked.">
              <option value="BEGINNER">Beginner</option>
              <option value="CLASSIC">Classic</option>
              <option value="EXPERT">Expert</option>
            </select>
          </div>
          <div className="field">
            <label htmlFor="pf-preset">Experience</label>
            <select id="pf-preset" value={preset} onChange={(e) => setPreset(e.target.value)}
              title="Preset decides which modules are active for this portfolio.">
              <option value="ACADEMY">Academy (everything)</option>
              <option value="LEARNING">Learning (no gamification)</option>
              <option value="PROFESSIONAL">Professional (clean analytics)</option>
            </select>
          </div>
          <button type="submit">Create</button>
        </div>
        {error && <div className="error">{error}</div>}
      </form>
    </div>
  );
}
