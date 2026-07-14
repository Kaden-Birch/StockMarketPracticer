import { FormEvent, useCallback, useEffect, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import {
  api,
  AiDecisionView,
  AiProfileInfo,
  ClubMessageView,
  ClubRankRow,
  ClubSummary,
  ClubView,
  CompetitionAnalysis,
  CompetitionView,
  fmtMoney,
  LeaderboardCategory,
  StandingRow,
  TournamentInfo,
} from "../api";
import { useModules } from "../hooks/useModules";

const TABS = [
  { id: "leaderboards", label: "Leaderboards", module: "leaderboards" },
  { id: "competitions", label: "Competitions", module: "multiplayer" },
  { id: "clubs", label: "Clubs", module: "multiplayer" },
];

export default function CommunityPage() {
  const [params, setParams] = useSearchParams();
  const { running } = useModules();
  const tabs = TABS.filter((t) => running(t.module));
  const tab = params.get("tab") ?? (tabs[0]?.id || "leaderboards");
  return (
    <div>
      <h1>Community</h1>
      <div className="range-row" role="tablist" aria-label="Community sections">
        {tabs.map((t) => (
          <button key={t.id} className={`ghost ${t.id === tab ? "active" : ""}`}
            role="tab" aria-selected={t.id === tab}
            onClick={() => setParams({ tab: t.id })}>
            {t.label}
          </button>
        ))}
      </div>
      {tab === "leaderboards" && <LeaderboardsTab />}
      {tab === "competitions" && <CompetitionsTab />}
      {tab === "clubs" && <ClubsTab />}
    </div>
  );
}

/* ------------------------------------------------------------ leaderboards */

function LeaderboardsTab() {
  const [boards, setBoards] = useState<LeaderboardCategory[]>([]);
  const [error, setError] = useState("");
  useEffect(() => {
    api.leaderboards().then((b) => setBoards(b.categories)).catch((e: Error) => setError(e.message));
  }, []);
  return (
    <>
      {error && <div className="error">{error}</div>}
      <p className="muted">
        Leaderboards are strictly opt-in: flip “Public on leaderboards” on a
        portfolio’s page to appear here. Rankings refresh about every 5 minutes.
      </p>
      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(340px, 1fr))", gap: 16 }}>
        {boards.map((b) => (
          <div className="card" key={b.id}>
            <h2>{b.name}</h2>
            {b.entries.length === 0 && <p className="muted">No entrants yet.</p>}
            {b.entries.length > 0 && (
              <table>
                <thead>
                  <tr><th>#</th><th>Portfolio</th><th>Score</th></tr>
                </thead>
                <tbody>
                  {b.entries.map((e) => (
                    <tr key={e.rank} style={e.is_me ? { fontWeight: 600 } : undefined}>
                      <td>{e.rank}</td>
                      <td>{e.portfolio}{e.is_me ? " (you)" : ""}</td>
                      <td>{e.label}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </div>
        ))}
      </div>
    </>
  );
}

/* ------------------------------------------------------------ competitions */

function CompetitionsTab() {
  const { running } = useModules();
  const [comps, setComps] = useState<CompetitionView[]>([]);
  const [standings, setStandings] = useState<Record<string, StandingRow[]>>({});
  const [error, setError] = useState("");
  const [tournaments, setTournaments] = useState<TournamentInfo[]>([]);
  const [aiProfiles, setAiProfiles] = useState<AiProfileInfo[]>([]);
  const [aiForm, setAiForm] = useState<Record<string, { profile: string; difficulty: string; adaptive: boolean }>>({});
  const [decisions, setDecisions] = useState<{ player: string; decisions: AiDecisionView[] } | null>(null);
  const [analysis, setAnalysis] = useState<Record<string, CompetitionAnalysis>>({});
  const aiOn = running("ai_competitors");
  const [name, setName] = useState("");
  const [kind, setKind] = useState("PUBLIC");
  const [scoring, setScoring] = useState("RETURN");
  const [balance, setBalance] = useState("100000");
  const [joinCode, setJoinCode] = useState<Record<string, string>>({});

  const refresh = useCallback(() => {
    api.listCompetitions().then(setComps).catch((e: Error) => setError(e.message));
    api.tournaments().then(setTournaments).catch(() => undefined);
    api.aiProfiles().then(setAiProfiles).catch(() => undefined);
  }, []);
  useEffect(refresh, [refresh]);

  async function startTournament(template: string) {
    setError("");
    try {
      const t = await api.startTournament(template);
      refresh();
      await showStandings(t.competition_id);
    } catch (err) {
      setError((err as Error).message);
    }
  }

  async function addAi(compId: string) {
    const form = aiForm[compId] ?? { profile: "index", difficulty: "intermediate", adaptive: false };
    setError("");
    try {
      await api.addAiPlayer(compId, form);
      refresh();
      await showStandings(compId);
    } catch (err) {
      setError((err as Error).message);
    }
  }

  async function openDecisions(playerId: string) {
    setError("");
    try {
      setDecisions(await api.aiDecisions(playerId));
    } catch (err) {
      setError((err as Error).message);
    }
  }

  async function showAnalysis(compId: string) {
    setError("");
    try {
      const a = await api.competitionAnalysis(compId);
      setAnalysis((prev) => ({ ...prev, [compId]: a }));
    } catch (err) {
      setError((err as Error).message);
    }
  }

  async function create(e: FormEvent) {
    e.preventDefault();
    setError("");
    try {
      await api.createCompetition({ name, kind, scoring, starting_balance: balance });
      setName("");
      refresh();
    } catch (err) {
      setError((err as Error).message);
    }
  }

  async function join(c: CompetitionView) {
    setError("");
    try {
      await api.joinCompetition(c.id, joinCode[c.id] || "", "");
      refresh();
    } catch (err) {
      setError((err as Error).message);
    }
  }

  async function showStandings(id: string) {
    try {
      const s = await api.standings(id);
      setStandings((prev) => ({ ...prev, [id]: s.standings }));
    } catch (err) {
      setError((err as Error).message);
    }
  }

  return (
    <>
      {error && <div className="error">{error}</div>}
      {aiOn && tournaments.length > 0 && (
        <div className="card">
          <h2>AI Tournaments</h2>
          <p className="muted">
            One click starts a private game against simulated opponents —
            every AI trade is marked and its full decision log is open.
          </p>
          <div style={{ display: "flex", gap: 12, flexWrap: "wrap" }}>
            {tournaments.map((t) => (
              <div key={t.id} style={{ flex: "1 1 260px", border: "1px solid var(--border)",
                                       borderRadius: 8, padding: 12 }}>
                <strong>{t.name}</strong>
                <p className="muted" style={{ margin: "6px 0" }}>{t.description}</p>
                <p className="muted">{t.ai_players.length} AI opponent{t.ai_players.length > 1 ? "s" : ""}</p>
                <button onClick={() => startTournament(t.id)}>Start</button>
              </div>
            ))}
          </div>
        </div>
      )}
      {decisions && (
        <div className="card">
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline" }}>
            <h2>Decision log — {decisions.player}</h2>
            <button className="ghost" onClick={() => setDecisions(null)}>Close</button>
          </div>
          <p className="muted">
            Full transparency: what it did, why, the data it used, its
            confidence, and what it expected to happen.
          </p>
          {decisions.decisions.map((d, i) => (
            <div key={i} style={{ borderBottom: "1px solid var(--border)", padding: "8px 0" }}>
              <strong>
                <span className={`badge ${d.action === "BUY" ? "FILLED"
                  : d.action === "SELL" ? "PENDING"
                  : d.action === "MISTAKE" ? "REJECTED" : "CANCELLED"}`}>
                  {d.action}
                </span>{" "}
                {d.symbol}
              </strong>{" "}
              <span className="muted">confidence {d.confidence}% · {new Date(d.created_at).toLocaleString()}</span>
              <div>{d.reason}</div>
              <div className="muted">Expected: {d.expected_outcome}</div>
              {"selection" in d.data_used && (
                <div className="muted">Data: {String(d.data_used.selection)}
                  {"scores" in d.data_used
                    ? " · scores " + JSON.stringify(d.data_used.scores) : ""}
                </div>
              )}
            </div>
          ))}
        </div>
      )}
      <div className="card">
        <h2>Start a competition</h2>
        <p className="muted">
          Every player who joins gets a fresh game portfolio with the same
          starting balance — everyone competes from the same line.
        </p>
        <form onSubmit={create} className="row" style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
          <input placeholder="Competition name" value={name} required
            onChange={(e) => setName(e.target.value)} />
          <select value={kind} onChange={(e) => setKind(e.target.value)}>
            <option value="PUBLIC">Public — anyone can join</option>
            <option value="PRIVATE">Private — invite code</option>
          </select>
          <select value={scoring} onChange={(e) => setScoring(e.target.value)}>
            <option value="RETURN">Score by return</option>
            <option value="RISK_ADJUSTED">Score by risk-adjusted return</option>
            <option value="DIVERSIFICATION">Score by diversification</option>
          </select>
          <input style={{ width: 120 }} value={balance} title="Starting balance"
            onChange={(e) => setBalance(e.target.value)} />
          <button type="submit">Create</button>
        </form>
      </div>
      {comps.map((c) => (
        <div className="card" key={c.id}>
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline", flexWrap: "wrap", gap: 8 }}>
            <h2>
              {c.name} <span className="muted">({c.kind.toLowerCase()}, {c.entries} joined)</span>
            </h2>
            <span className="muted">
              {fmtMoney(c.starting_balance)} start · scored by {c.scoring.toLowerCase().replace("_", "-")}
            </span>
          </div>
          {c.invite_code && (
            <p className="muted">Invite code: <code>{c.invite_code}</code></p>
          )}
          <div style={{ display: "flex", gap: 8, alignItems: "center", flexWrap: "wrap" }}>
            {!c.joined && (
              <>
                {c.kind === "PRIVATE" && (
                  <input placeholder="Invite code" style={{ width: 140 }}
                    value={joinCode[c.id] || ""}
                    onChange={(e) => setJoinCode({ ...joinCode, [c.id]: e.target.value })} />
                )}
                <button onClick={() => join(c)}>Join</button>
              </>
            )}
            {c.joined && <span className="badge FILLED">Joined</span>}
            <button className="ghost" onClick={() => showStandings(c.id)}>Standings</button>
            {aiOn && <button className="ghost" onClick={() => showAnalysis(c.id)}>Analysis</button>}
          </div>
          {aiOn && aiProfiles.length > 0 && (
            <div style={{ display: "flex", gap: 6, alignItems: "center", flexWrap: "wrap", marginTop: 8 }}>
              <span className="muted">Add AI opponent:</span>
              <select value={(aiForm[c.id] ?? { profile: "index" }).profile}
                onChange={(e) => setAiForm({ ...aiForm, [c.id]: {
                  ...(aiForm[c.id] ?? { difficulty: "intermediate", adaptive: false }),
                  profile: e.target.value } })}>
                {aiProfiles.map((p) => (
                  <option key={p.id} value={p.id} title={p.philosophy}>{p.name}</option>
                ))}
              </select>
              <select value={(aiForm[c.id] ?? { difficulty: "intermediate" }).difficulty}
                onChange={(e) => setAiForm({ ...aiForm, [c.id]: {
                  ...(aiForm[c.id] ?? { profile: "index", adaptive: false }),
                  difficulty: e.target.value } })}>
                {(aiProfiles[0]?.difficulties ?? []).map((d) => (
                  <option key={d} value={d}>{d}</option>
                ))}
              </select>
              <label style={{ display: "flex", gap: 4, alignItems: "center" }}
                title="Adaptive AIs watch the standings and adjust their strategy">
                <input type="checkbox"
                  checked={(aiForm[c.id] ?? { adaptive: false }).adaptive}
                  onChange={(e) => setAiForm({ ...aiForm, [c.id]: {
                    ...(aiForm[c.id] ?? { profile: "index", difficulty: "intermediate" }),
                    adaptive: e.target.checked } })} />
                adaptive
              </label>
              <button className="ghost" onClick={() => addAi(c.id)}>Add 🤖</button>
            </div>
          )}
          {standings[c.id] && (
            <table style={{ marginTop: 10 }}>
              <thead>
                <tr><th>#</th><th>Player</th><th>Return</th><th>Value</th><th>Score</th><th /></tr>
              </thead>
              <tbody>
                {standings[c.id].map((r) => (
                  <tr key={r.rank} style={r.is_me ? { fontWeight: 600 } : undefined}>
                    <td>{r.rank}</td>
                    <td>{r.display_name}{r.is_me ? " (you)" : ""}</td>
                    <td>{r.return_pct === null ? "—" : `${r.return_pct.toFixed(2)}%`}</td>
                    <td>{fmtMoney(r.total_value)}</td>
                    <td>{r.score === null ? "—" : r.score}</td>
                    <td>
                      {r.is_ai && r.ai_player_id && (
                        <button className="ghost"
                          onClick={() => openDecisions(r.ai_player_id!)}>
                          Decisions
                        </button>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
          {analysis[c.id] && (
            <div style={{ marginTop: 10, borderTop: "1px solid var(--border)", paddingTop: 8 }}>
              <h3>Game analysis</h3>
              {analysis[c.id].findings.map((f, i) => <p key={i}>• {f}</p>)}
              <table>
                <thead>
                  <tr><th>#</th><th>Player</th><th>Return</th><th>Trades</th>
                      <th>Win rate</th><th>Diversification</th><th>Cash</th></tr>
                </thead>
                <tbody>
                  {analysis[c.id].standings.map((r) => (
                    <tr key={r.rank} style={r.is_you ? { fontWeight: 600 } : undefined}>
                      <td>{r.rank}</td>
                      <td>{r.name}{r.is_you ? " (you)" : ""}</td>
                      <td>{r.return_pct}%</td>
                      <td>{r.trades}</td>
                      <td>{r.win_rate === null ? "—" : `${r.win_rate}%`}</td>
                      <td>{r.diversification ?? "—"}</td>
                      <td>{r.cash_pct === null ? "—" : `${r.cash_pct}%`}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      ))}
      {comps.length === 0 && <p className="muted">No competitions yet.</p>}
    </>
  );
}

/* ------------------------------------------------------------------- clubs */

function ClubsTab() {
  const [clubs, setClubs] = useState<ClubSummary[]>([]);
  const [selected, setSelected] = useState<string | null>(null);
  const [error, setError] = useState("");
  const [name, setName] = useState("");
  const [withPortfolio, setWithPortfolio] = useState(true);
  const [inviteCode, setInviteCode] = useState("");

  const refresh = useCallback(() => {
    api.listClubs().then(setClubs).catch((e: Error) => setError(e.message));
  }, []);
  useEffect(refresh, [refresh]);

  async function create(e: FormEvent) {
    e.preventDefault();
    setError("");
    try {
      const club = await api.createClub({ name, with_portfolio: withPortfolio });
      setName("");
      refresh();
      setSelected(club.id);
    } catch (err) {
      setError((err as Error).message);
    }
  }

  async function join(e: FormEvent) {
    e.preventDefault();
    setError("");
    try {
      const c = await api.joinClub(inviteCode.trim());
      setInviteCode("");
      refresh();
      setSelected(c.id);
    } catch (err) {
      setError((err as Error).message);
    }
  }

  return (
    <>
      {error && <div className="error">{error}</div>}
      <div className="card">
        <h2>Investment clubs</h2>
        <div style={{ display: "flex", gap: 24, flexWrap: "wrap" }}>
          <form onSubmit={create} style={{ display: "flex", gap: 8, alignItems: "center", flexWrap: "wrap" }}>
            <input placeholder="New club name" value={name} required
              onChange={(e) => setName(e.target.value)} />
            <label style={{ display: "flex", gap: 4, alignItems: "center" }}>
              <input type="checkbox" checked={withPortfolio}
                onChange={(e) => setWithPortfolio(e.target.checked)} />
              shared club portfolio
            </label>
            <button type="submit">Create club</button>
          </form>
          <form onSubmit={join} style={{ display: "flex", gap: 8, alignItems: "center" }}>
            <input placeholder="Invite code" value={inviteCode} required
              onChange={(e) => setInviteCode(e.target.value)} style={{ width: 140 }} />
            <button type="submit" className="ghost">Join a club</button>
          </form>
        </div>
        {clubs.length > 0 && (
          <div className="range-row" style={{ marginTop: 12 }}>
            {clubs.map((c) => (
              <button key={c.id} className={`ghost ${selected === c.id ? "active" : ""}`}
                onClick={() => setSelected(c.id)}>
                {c.name}
              </button>
            ))}
          </div>
        )}
        {clubs.length === 0 && <p className="muted">You're not in any clubs yet.</p>}
      </div>
      {selected && <ClubDetail id={selected} onGone={() => { setSelected(null); refresh(); }} />}
    </>
  );
}

function ClubDetail({ id, onGone }: { id: string; onGone: () => void }) {
  const [club, setClub] = useState<ClubView | null>(null);
  const [messages, setMessages] = useState<ClubMessageView[]>([]);
  const [rankings, setRankings] = useState<ClubRankRow[]>([]);
  const [draft, setDraft] = useState("");
  const [error, setError] = useState("");

  const refresh = useCallback(() => {
    api.clubDetail(id).then(setClub).catch((e: Error) => setError(e.message));
    api.clubMessages(id).then(setMessages).catch(() => undefined);
    api.clubRankings(id).then(setRankings).catch(() => undefined);
  }, [id]);
  useEffect(refresh, [refresh]);

  async function send(e: FormEvent) {
    e.preventDefault();
    if (!draft.trim()) return;
    try {
      await api.postClubMessage(id, draft.trim());
      setDraft("");
      refresh();
    } catch (err) {
      setError((err as Error).message);
    }
  }

  async function remove() {
    if (!window.confirm(`Delete club “${club?.name}”? This cannot be undone.`)) return;
    try {
      await api.deleteClub(id);
      onGone();
    } catch (err) {
      setError((err as Error).message);
    }
  }

  if (!club) return error ? <div className="error">{error}</div> : null;
  return (
    <div style={{ display: "grid", gridTemplateColumns: "2fr 1fr", gap: 16, alignItems: "start" }}>
      <div className="card">
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline" }}>
          <h2>{club.name}</h2>
          <button className="ghost" onClick={remove}>Delete club</button>
        </div>
        {club.description && <p className="muted">{club.description}</p>}
        {club.invite_code && (
          <p className="muted">Invite code: <code>{club.invite_code}</code></p>
        )}
        {club.club_portfolio_id && (
          <p>
            <Link to={`/portfolios/${club.club_portfolio_id}`}>Open the shared club portfolio →</Link>
          </p>
        )}
        <h3>Discussion</h3>
        <div style={{ maxHeight: 320, overflowY: "auto", display: "flex", flexDirection: "column", gap: 6 }}>
          {messages.map((m) => (
            <div key={m.id}>
              <strong>{m.author}</strong>{" "}
              <span className="muted">{new Date(m.created_at).toLocaleString()}</span>
              <div>{m.body}</div>
            </div>
          ))}
          {messages.length === 0 && <p className="muted">No messages yet — say hi!</p>}
        </div>
        <form onSubmit={send} style={{ display: "flex", gap: 8, marginTop: 10 }}>
          <input style={{ flex: 1 }} placeholder="Write a message…" value={draft}
            onChange={(e) => setDraft(e.target.value)} />
          <button type="submit">Send</button>
        </form>
      </div>
      <div className="card">
        <h3>Members</h3>
        <table>
          <tbody>
            {club.members.map((m) => (
              <tr key={m.username}>
                <td>{m.username}</td>
                <td className="muted">{m.role.toLowerCase()}</td>
              </tr>
            ))}
          </tbody>
        </table>
        <h3 style={{ marginTop: 14 }}>Member rankings</h3>
        <p className="muted">Best personal-portfolio return.</p>
        <table>
          <tbody>
            {rankings.map((r) => (
              <tr key={r.username}>
                <td>{r.rank}. {r.username}</td>
                <td>{r.best_return_pct === null ? "—" : `${r.best_return_pct.toFixed(2)}%`}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
