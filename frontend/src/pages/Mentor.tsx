import { useCallback, useEffect, useState } from "react";
import { api, MentorObservationView, MentorView } from "../api";

const SEVERITY_BADGE: Record<string, string> = {
  important: "REJECTED", notice: "PENDING", info: "FILLED",
};

export default function MentorPage() {
  const [view, setView] = useState<MentorView | null>(null);
  const [narrative, setNarrative] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  const refresh = useCallback(() => {
    api.mentor().then(setView).catch((e: Error) => setError(e.message));
  }, []);
  useEffect(refresh, [refresh]);

  async function analyze() {
    setBusy(true);
    setError("");
    try {
      setView(await api.mentorRefresh());
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  async function narrate() {
    setError("");
    setNarrative("");
    try {
      const r = await api.mentorNarrative();
      setNarrative(r.narrative);
    } catch (e) {
      setError((e as Error).message);
    }
  }

  async function acknowledge(id: string) {
    await api.mentorAcknowledge(id).catch((e: Error) => setError(e.message));
    refresh();
  }

  const profile = view?.profile;
  return (
    <div>
      <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
        <h1 style={{ marginBottom: 0 }}>Your Mentor</h1>
        <span style={{ flex: 1 }} />
        <button onClick={analyze} disabled={busy}>
          {busy ? "Analyzing…" : "Analyze my investing"}
        </button>
        <button className="ghost" onClick={narrate}
          title="A short mentor note written by the local AI model over the verified findings below">
          AI mentor note
        </button>
      </div>
      <p className="muted">
        Every observation below is computed from your real trading history —
        the numbers backing it are shown. The mentor remembers: fixed habits
        move to the résumé, repeated ones count up.
      </p>
      {error && <div className="error">{error}</div>}
      {narrative && (
        <div className="card" style={{ whiteSpace: "pre-wrap" }}>
          <h2>Mentor's note</h2>
          {narrative}
        </div>
      )}

      {profile && (profile.style || profile.strengths.length > 0) && (
        <div className="card">
          <h2>How you invest</h2>
          {profile.style && <p><strong>Style:</strong> {profile.style}</p>}
          {profile.strengths.length > 0 && (
            <p><strong>Strengths:</strong> {profile.strengths.join(" · ")}</p>
          )}
          {profile.knowledge_gaps.length > 0 && (
            <p><strong>Knowledge gaps:</strong> {profile.knowledge_gaps.join(" · ")}</p>
          )}
          {profile.updated_at && (
            <p className="muted">Last analyzed {new Date(profile.updated_at).toLocaleString()}</p>
          )}
        </div>
      )}

      {view && view.observations.length === 0 && (
        <p className="muted">
          No active observations. Trade for a while, then press “Analyze my
          investing”.
        </p>
      )}
      {view?.observations.map((o) => (
        <ObservationCard key={o.id} o={o} onAck={acknowledge} />
      ))}

      {view && view.resolved.length > 0 && (
        <div className="card">
          <h2>Resolved — your progress résumé</h2>
          {view.resolved.map((o) => (
            <p key={o.id} className="muted">✓ {o.title}</p>
          ))}
        </div>
      )}
    </div>
  );
}

function ObservationCard({ o, onAck }:
  { o: MentorObservationView; onAck: (id: string) => void }) {
  return (
    <div className="card">
      <div style={{ display: "flex", alignItems: "baseline", gap: 10 }}>
        <span className={`badge ${SEVERITY_BADGE[o.severity] ?? "FILLED"}`}>
          {o.severity}
        </span>
        <h2 style={{ marginBottom: 0 }}>{o.title}</h2>
        <span style={{ flex: 1 }} />
        {o.status === "ACTIVE" ? (
          <button className="ghost" onClick={() => onAck(o.id)}>Got it</button>
        ) : (
          <span className="muted">acknowledged</span>
        )}
      </div>
      <p>{o.body}</p>
      <p className="muted">
        Seen {o.times_seen}× since {new Date(o.first_seen).toLocaleDateString()} ·
        evidence: {Object.entries(o.evidence).map(([k, v]) => `${k}=${v}`).join(", ")}
      </p>
    </div>
  );
}
