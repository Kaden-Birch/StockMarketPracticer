import { useCallback, useEffect, useState } from "react";
import { api, ChallengeView, GamifyProfile } from "../api";

const AVATARS = ["📈", "🚀", "🦉", "🐢", "🦁", "💎", "🌱", "⚖️"];
const CATEGORY_LABEL: Record<string, string> = {
  education: "Education", research: "Research",
  portfolio: "Portfolio", challenge: "Challenges",
};

export default function ProfilePage() {
  const [profile, setProfile] = useState<GamifyProfile | null>(null);
  const [challenges, setChallenges] = useState<ChallengeView[]>([]);
  const [editingName, setEditingName] = useState(false);
  const [name, setName] = useState("");
  const [error, setError] = useState("");

  const refresh = useCallback(() => {
    api.gamifyProfile().then((p) => {
      setProfile(p);
      setName(p.username);
    }).catch((e: Error) => setError(e.message));
    api.gamifyChallenges().then(setChallenges).catch(() => undefined);
  }, []);
  useEffect(() => {
    refresh();
    api.gamifyEvaluate().then(refresh).catch(() => undefined);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  if (!profile) return <div className="muted">Loading…</div>;
  const p = profile.progress;
  const currentChallenges = challenges.filter((c) => c.current);
  const earnedCount = profile.achievements.filter((a) => a.earned_at).length;

  async function save(patch: object) {
    await api.updateGamifyProfile(patch);
    refresh();
  }

  return (
    <div>
      <h1>Profile</h1>
      {error && <div className="error">{error}</div>}

      <div className="card">
        <div style={{ display: "flex", gap: 16, alignItems: "center", flexWrap: "wrap" }}>
          <span style={{ fontSize: 44 }} role="img" aria-label="avatar">{profile.avatar}</span>
          <div style={{ flex: 1, minWidth: 240 }}>
            {editingName ? (
              <form
                onSubmit={async (e) => {
                  e.preventDefault();
                  await save({ username: name });
                  setEditingName(false);
                }}
                className="form-row"
              >
                <input value={name} onChange={(e) => setName(e.target.value)} minLength={1} />
                <button type="submit">Save</button>
              </form>
            ) : (
              <h2 style={{ fontSize: 20, color: "var(--text-primary)", margin: 0 }}>
                {profile.username}{" "}
                <button className="ghost" onClick={() => setEditingName(true)}>edit</button>
              </h2>
            )}
            <div className="muted">
              Level {p.level} · {p.title} · {p.xp} XP
            </div>
            <div
              role="progressbar"
              aria-valuenow={p.progress_pct}
              aria-valuemin={0}
              aria-valuemax={100}
              aria-label="Progress to next level"
              style={{
                height: 10, borderRadius: 5, background: "var(--surface-0)",
                border: "1px solid var(--border)", marginTop: 8, overflow: "hidden",
              }}
            >
              <div style={{
                width: `${p.progress_pct}%`, height: "100%",
                background: "var(--accent)", transition: "width .3s",
              }} />
            </div>
            <div className="muted" style={{ fontSize: 11, marginTop: 2 }}>
              {p.xp - p.level_floor_xp} / {p.next_level_xp - p.level_floor_xp} XP to level {p.level + 1}
            </div>
          </div>
          <div className="form-row">
            {AVATARS.map((a) => (
              <button key={a} className={`ghost ${profile.avatar === a ? "active" : ""}`}
                onClick={() => save({ avatar: a })} aria-label={`Avatar ${a}`}>
                {a}
              </button>
            ))}
          </div>
        </div>
      </div>

      <div className="cards-row">
        {Object.entries(profile.xp_by_category).map(([category, xp]) => (
          <div className="card stat" key={category}>
            <div className="label">{CATEGORY_LABEL[category]} XP</div>
            <div className="value">{xp}</div>
          </div>
        ))}
      </div>

      <div className="card">
        <h2>Challenges</h2>
        {currentChallenges.length === 0 && <p className="muted">Loading challenges…</p>}
        <table>
          <thead>
            <tr><th>Cadence</th><th>Challenge</th><th className="num">XP</th><th>Status</th></tr>
          </thead>
          <tbody>
            {currentChallenges.map((c) => (
              <tr key={c.id}>
                <td>{c.period_type}</td>
                <td>
                  <strong>{c.name}</strong>
                  <div className="muted">{c.description}</div>
                </td>
                <td className="num">+{c.xp}</td>
                <td>
                  <span className={`badge ${c.status === "COMPLETED" ? "FILLED" : "PENDING"}`}>
                    {c.status}
                  </span>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        <p className="muted" style={{ marginTop: 8 }}>
          Challenges reward learning, research, and portfolio discipline — never trading volume.
        </p>
      </div>

      <div className="card">
        <h2>Achievements ({earnedCount}/{profile.achievements.length})</h2>
        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(260px, 1fr))", gap: 10 }}>
          {profile.achievements.map((a) => (
            <div key={a.id} style={{
              border: "1px solid var(--border)", borderRadius: 10, padding: "10px 12px",
              opacity: a.earned_at ? 1 : 0.45,
              background: a.earned_at ? "var(--accent-soft)" : "transparent",
            }}>
              <strong>{a.earned_at ? "🏆 " : "🔒 "}{a.name}</strong>
              <div className="muted">{a.description} · +{a.xp} XP</div>
              {a.earned_at && (
                <div className="muted" style={{ fontSize: 11 }}>
                  {new Date(a.earned_at + (a.earned_at.endsWith("Z") ? "" : "Z")).toLocaleDateString()}
                </div>
              )}
            </div>
          ))}
        </div>
      </div>

      <div className="card">
        <h2>Titles</h2>
        <div className="form-row">
          {p.titles.map((t) => (
            <span key={t.level} className={`badge ${t.earned ? "FILLED" : ""}`}
              title={`Level ${t.level}`}>
              {t.title} (Lv {t.level})
            </span>
          ))}
        </div>
      </div>

      <div className="card">
        <h2>Gamification</h2>
        <button className="ghost" onClick={() => save({ gamification_enabled: !profile.gamification_enabled })}>
          {profile.gamification_enabled ? "Turn off XP, achievements & challenges" : "Turn gamification back on"}
        </button>
        <p className="muted" style={{ marginTop: 8 }}>
          Fully optional (PRD §23). Turning it off stops all XP awards and progress
          tracking; nothing about trading changes.
        </p>
      </div>
    </div>
  );
}
