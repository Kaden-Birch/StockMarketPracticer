import { useCallback, useEffect, useState } from "react";
import { api, CareerView, fmtMoney } from "../api";

export default function CareerPage() {
  const [view, setView] = useState<CareerView | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  const refresh = useCallback(() => {
    api.career().then(setView).catch((e: Error) => setError(e.message));
  }, []);
  useEffect(refresh, [refresh]);

  async function evaluate() {
    setBusy(true);
    setError("");
    try {
      setView(await api.careerEvaluate());
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  if (!view) return error ? <div className="error">{error}</div> : <p className="muted">Loading…</p>;

  const currentObjectives = view.objectives.filter((o) => o.current);
  const doneCount = currentObjectives.filter((o) => o.done).length;
  return (
    <div>
      <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
        <h1 style={{ marginBottom: 0 }}>Career</h1>
        <span style={{ flex: 1 }} />
        <button onClick={evaluate} disabled={busy}>
          {busy ? "Evaluating…" : "Evaluate progress"}
        </button>
      </div>
      {error && <div className="error">{error}</div>}

      <div className="card">
        <h2>Rank: {view.rank_name}</h2>
        <div style={{ display: "flex", gap: 6, flexWrap: "wrap", alignItems: "center" }}>
          {view.ladder.map((r, i) => (
            <span key={r} style={{ display: "flex", alignItems: "center", gap: 6 }}>
              <span className={`badge ${i < view.rank ? "FILLED" : i === view.rank ? "PENDING" : "CANCELLED"}`}>
                {r}
              </span>
              {i < view.ladder.length - 1 && <span className="muted">→</span>}
            </span>
          ))}
        </div>
        {view.next_rank && (
          <p className="muted" style={{ marginTop: 8 }}>
            {doneCount}/{currentObjectives.length} objectives complete toward{" "}
            <strong>{view.next_rank}</strong>.
          </p>
        )}
        {view.progress && (
          <p className="muted">
            {view.progress.trades} trades · {fmtMoney(view.progress.total_value)} under
            management · best diversification {view.progress.best_diversification ?? "—"}
          </p>
        )}
      </div>

      <div className="card">
        <h2>Current objectives</h2>
        {currentObjectives.map((o) => (
          <p key={o.code}>
            {o.done ? "✅" : "⬜"} <strong>{o.label}</strong>{" "}
            <span className="muted">— {o.description}</span>
          </p>
        ))}
      </div>

      <div className="card">
        <h2>Advanced challenges</h2>
        <p className="muted">
          Career-defining feats — they unlock at higher ranks but count
          whenever you achieve them.
        </p>
        {view.challenges.map((o) => (
          <p key={o.code}>
            {o.done ? "🏆" : "🔒"} <strong>{o.label}</strong>{" "}
            <span className="muted">— {o.description} (rank: {o.rank_name})</span>
          </p>
        ))}
      </div>

      <div className="card">
        <h2>The full ladder</h2>
        {view.ladder.map((rankName, i) => (
          <div key={rankName} style={{ marginBottom: 8 }}>
            <strong>{rankName}</strong>
            {view.objectives.filter((o) => o.rank === i).map((o) => (
              <span key={o.code} className="muted"> · {o.done ? "✓" : "○"} {o.label}</span>
            ))}
          </div>
        ))}
      </div>
    </div>
  );
}
