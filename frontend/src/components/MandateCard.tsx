import { useCallback, useEffect, useState } from "react";
import { api, MandateCompliance } from "../api";

const STATUS_ICON = { ok: "✅", violation: "❌", pending: "⏳" } as const;

/** Portfolio mandate + live compliance (roadmap 8.4). Reported, never
 * enforced by liquidation. */
export default function MandateCard({ portfolioId }: { portfolioId: string }) {
  const [comp, setComp] = useState<MandateCompliance | null>(null);
  const [options, setOptions] = useState<{ id: string; name: string; summary: string }[]>([]);
  const [error, setError] = useState("");

  const refresh = useCallback(() => {
    api.getMandate(portfolioId).then(setComp).catch(() => setComp(null));
    api.mandates().then(setOptions).catch(() => undefined);
  }, [portfolioId]);
  useEffect(refresh, [refresh]);

  if (comp === null) return null; // career module disabled

  async function set(mandate: string) {
    setError("");
    try {
      setComp(await api.setMandate(portfolioId, mandate));
    } catch (e) {
      setError((e as Error).message);
    }
  }

  return (
    <div className="card">
      <div style={{ display: "flex", alignItems: "center", gap: 10, flexWrap: "wrap" }}>
        <h2 style={{ marginBottom: 0 }}>Mandate</h2>
        <select value={comp.mandate} onChange={(e) => set(e.target.value)}>
          <option value="">No mandate</option>
          {options.map((m) => (
            <option key={m.id} value={m.id}>{m.name}</option>
          ))}
        </select>
        {comp.mandate && (
          <span className={`badge ${comp.compliant === true ? "FILLED"
            : comp.compliant === false ? "REJECTED" : "PENDING"}`}>
            {comp.compliant === true ? "COMPLIANT"
              : comp.compliant === false ? "IN VIOLATION" : "EVALUATING"}
          </span>
        )}
      </div>
      {error && <div className="error">{error}</div>}
      {comp.info && <p className="muted">{comp.info.summary}</p>}
      {comp.rules.map((r) => (
        <p key={r.id} style={{ margin: "4px 0" }}>
          {STATUS_ICON[r.status]} {r.label}{" "}
          <span className="muted">
            — currently {String(r.value)} (target {r.threshold})
          </span>
        </p>
      ))}
      {comp.mandate && (
        <p className="muted">
          Compliance is measured and reported; the platform never force-sells
          your positions.
        </p>
      )}
    </div>
  );
}
