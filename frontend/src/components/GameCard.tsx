import { useCallback, useEffect, useState } from "react";
import { api, CoachObservation, ReportCard } from "../api";

/** Per-portfolio "game" panel (roadmap 6.5, 6.9, 6.10): mode + game level,
 * report card grades, and coach observations. */
export default function GameCard({ portfolioId, mode }: { portfolioId: string; mode: string }) {
  const [game, setGame] = useState<{ game_level: number; game_xp: number } | null>(null);
  const [card, setCard] = useState<ReportCard | null>(null);
  const [coach, setCoach] = useState<CoachObservation[]>([]);
  const [read, setRead] = useState<Set<string>>(new Set());

  const refresh = useCallback(() => {
    api.gameView(portfolioId).then(setGame).catch(() => undefined);
    api.reportCard(portfolioId).then(setCard).catch(() => undefined);
    api.coach(portfolioId).then((r) => setCoach(r.observations)).catch(() => undefined);
  }, [portfolioId]);
  useEffect(refresh, [refresh]);

  async function ack(obs: CoachObservation) {
    setRead(new Set([...read, obs.id]));
    await api.gamifyEvent("coach_suggestion_read", obs.topic, portfolioId);
    api.gamifyEvaluate().catch(() => undefined);
  }

  const gradeColor = (g: string) =>
    g.startsWith("A") ? "var(--gain)" : g.startsWith("F") || g.startsWith("D") ? "var(--loss)" : "var(--text-primary)";

  return (
    <div className="cards-row">
      <div className="card" style={{ flex: 1, minWidth: 280 }}>
        <h2>Game progress</h2>
        {game && (
          <p>
            <span className="badge">{mode}</span>{" "}
            Game level <strong>{game.game_level}</strong> · {game.game_xp} XP earned here
          </p>
        )}
        {card && (
          <>
            <div style={{ display: "flex", alignItems: "baseline", gap: 10 }}>
              <h2 style={{ margin: 0 }}>Report card</h2>
              <span style={{ fontSize: 26, fontWeight: 700, color: gradeColor(card.overall) }}>
                {card.overall}
              </span>
            </div>
            <table style={{ marginTop: 6 }}>
              <tbody>
                {Object.entries(card.subjects).map(([subject, s]) => (
                  <tr key={subject}>
                    <th style={{ textTransform: "capitalize" }}>{subject.replace("_", " ")}</th>
                    <td style={{ fontWeight: 700, color: gradeColor(s.grade), width: 40 }}>{s.grade}</td>
                    <td className="muted">{s.detail}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </>
        )}
      </div>
      <div className="card" style={{ flex: 1, minWidth: 280 }}>
        <h2>Learning coach</h2>
        {coach.map((o) => (
          <div key={o.id} style={{ borderBottom: "1px solid var(--border)", padding: "8px 0" }}>
            <div>{o.observation}</div>
            <div className="muted">{o.suggestion}</div>
            <button className="ghost" style={{ marginTop: 6 }} disabled={read.has(o.id)}
              onClick={() => ack(o)}>
              {read.has(o.id) ? "Marked as read ✓ (+XP)" : "Got it — mark as read"}
            </button>
          </div>
        ))}
        {coach.length > 0 && (
          <p className="muted" style={{ marginTop: 8 }}>{coach[0].disclaimer}</p>
        )}
      </div>
    </div>
  );
}
