import { FormEvent, useCallback, useEffect, useState } from "react";
import { api, MemberView, ProposalView } from "../api";

/** Cooperative-portfolio controls (roadmap 7.2): members with roles and
 * trade proposals that execute on a majority vote. */
export default function CommunityCard({ portfolioId, onTraded }:
  { portfolioId: string; onTraded: () => void }) {
  const [owner, setOwner] = useState("");
  const [members, setMembers] = useState<MemberView[]>([]);
  const [proposals, setProposals] = useState<ProposalView[]>([]);
  const [error, setError] = useState("");
  const [open, setOpen] = useState(false);

  const [newMember, setNewMember] = useState("");
  const [newRole, setNewRole] = useState("MEMBER");
  const [symbol, setSymbol] = useState("");
  const [side, setSide] = useState("BUY");
  const [quantity, setQuantity] = useState("");
  const [rationale, setRationale] = useState("");

  const refresh = useCallback(() => {
    api.listMembers(portfolioId)
      .then((m) => { setOwner(m.owner); setMembers(m.members); })
      .catch(() => undefined); // module disabled — card stays collapsed
    api.listProposals(portfolioId).then(setProposals).catch(() => undefined);
  }, [portfolioId]);
  useEffect(refresh, [refresh]);

  async function addMember(e: FormEvent) {
    e.preventDefault();
    setError("");
    try {
      await api.addMember(portfolioId, newMember.trim(), newRole);
      setNewMember("");
      refresh();
    } catch (err) {
      setError((err as Error).message);
    }
  }

  async function propose(e: FormEvent) {
    e.preventDefault();
    setError("");
    try {
      await api.createProposal(portfolioId, {
        symbol: symbol.trim().toUpperCase(), side, quantity, rationale,
      });
      setSymbol(""); setQuantity(""); setRationale("");
      refresh();
      onTraded();
    } catch (err) {
      setError((err as Error).message);
    }
  }

  async function vote(id: string, approve: boolean) {
    setError("");
    try {
      const p = await api.voteProposal(portfolioId, id, approve);
      refresh();
      if (p.status === "EXECUTED") onTraded();
    } catch (err) {
      setError((err as Error).message);
    }
  }

  const openProposals = proposals.filter((p) => p.status === "OPEN");
  const decided = proposals.filter((p) => p.status !== "OPEN").slice(0, 5);

  return (
    <div className="card">
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
        <h2 style={{ marginBottom: 0 }}>
          Cooperative trading
          {members.length > 0 && (
            <span className="muted"> — {members.length + 1} participants</span>
          )}
          {openProposals.length > 0 && (
            <span className="badge PENDING" style={{ marginLeft: 8 }}>
              {openProposals.length} open vote{openProposals.length > 1 ? "s" : ""}
            </span>
          )}
        </h2>
        <button className="ghost" onClick={() => setOpen(!open)}>
          {open ? "Hide" : "Manage"}
        </button>
      </div>
      {error && <div className="error">{error}</div>}

      {(open || openProposals.length > 0) && (
        <>
          {openProposals.map((p) => (
            <div key={p.id} style={{ margin: "10px 0", padding: 10, border: "1px solid var(--border, #444)", borderRadius: 8 }}>
              <strong>{p.side} {p.quantity ?? p.notional} {p.symbol}</strong>{" "}
              <span className="muted">proposed by {p.proposer}</span>
              {p.rationale && <div className="muted">“{p.rationale}”</div>}
              <div style={{ display: "flex", gap: 8, alignItems: "center", marginTop: 6 }}>
                <span className="muted">
                  {p.approvals} yes / {p.rejections} no of {p.eligible_voters} voters
                </span>
                <button onClick={() => vote(p.id, true)}>Approve</button>
                <button className="ghost" onClick={() => vote(p.id, false)}>Reject</button>
              </div>
            </div>
          ))}
        </>
      )}

      {open && (
        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 16, marginTop: 10 }}>
          <div>
            <h3>Members</h3>
            <table>
              <tbody>
                <tr><td>{owner}</td><td className="muted">owner</td><td /></tr>
                {members.map((m) => (
                  <tr key={m.username}>
                    <td>{m.username}</td>
                    <td className="muted">{m.role.toLowerCase()}</td>
                    <td>
                      <button className="ghost" onClick={async () => {
                        await api.removeMember(portfolioId, m.username).catch((e: Error) => setError(e.message));
                        refresh();
                      }}>Remove</button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
            <form onSubmit={addMember} style={{ display: "flex", gap: 6, marginTop: 8, flexWrap: "wrap" }}>
              <input placeholder="Username" value={newMember} required
                onChange={(e) => setNewMember(e.target.value)} style={{ width: 130 }} />
              <select value={newRole} onChange={(e) => setNewRole(e.target.value)}>
                <option value="MANAGER">Manager</option>
                <option value="MEMBER">Member — can vote</option>
                <option value="VIEWER">Viewer — read only</option>
              </select>
              <button type="submit" className="ghost">Add</button>
            </form>
          </div>
          <div>
            <h3>Propose a trade</h3>
            <p className="muted">Executes as a market order once a majority approves.</p>
            <form onSubmit={propose} style={{ display: "flex", gap: 6, flexWrap: "wrap" }}>
              <input placeholder="Symbol" value={symbol} required style={{ width: 90 }}
                onChange={(e) => setSymbol(e.target.value)} />
              <select value={side} onChange={(e) => setSide(e.target.value)}>
                <option value="BUY">Buy</option>
                <option value="SELL">Sell</option>
              </select>
              <input placeholder="Quantity" value={quantity} required style={{ width: 90 }}
                onChange={(e) => setQuantity(e.target.value)} />
              <input placeholder="Why? (rationale)" value={rationale} style={{ flex: 1, minWidth: 140 }}
                onChange={(e) => setRationale(e.target.value)} />
              <button type="submit">Propose</button>
            </form>
            {decided.length > 0 && (
              <>
                <h3 style={{ marginTop: 12 }}>Recent decisions</h3>
                <table>
                  <tbody>
                    {decided.map((p) => (
                      <tr key={p.id}>
                        <td>{p.side} {p.quantity ?? p.notional} {p.symbol}</td>
                        <td><span className={`badge ${p.status === "EXECUTED" ? "FILLED" : "REJECTED"}`}>{p.status}</span></td>
                        <td className="muted">{p.detail}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
