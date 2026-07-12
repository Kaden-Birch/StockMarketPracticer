import { useCallback, useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { api, AiSettings, fmtMoney, ModelView, PortfolioView, RecommendationView } from "../api";

function ImpactTable({ impact, currency }: { impact: Record<string, string | null>; currency: string }) {
  if (!impact || Object.keys(impact).length === 0) return null;
  return (
    <table style={{ marginTop: 8, maxWidth: 520 }}>
      <tbody>
        <tr>
          <th>Cash</th>
          <td className="num">{fmtMoney(impact.cash_before, currency)} → {fmtMoney(impact.cash_after, currency)}</td>
        </tr>
        <tr>
          <th>Position value</th>
          <td className="num">
            {fmtMoney(impact.position_value_before, currency)} → {fmtMoney(impact.position_value_after, currency)}
            {impact.position_weight_after_pct && ` (${impact.position_weight_after_pct}% of portfolio)`}
          </td>
        </tr>
      </tbody>
    </table>
  );
}

function RecCard({
  rec, currency, onDecide,
}: {
  rec: RecommendationView;
  currency: string;
  onDecide: (id: string, approve: boolean) => void;
}) {
  const actionCls = rec.action === "BUY" ? "gain" : rec.action === "SELL" ? "loss" : "";
  return (
    <div className="card" style={{ borderLeft: "3px solid var(--accent)" }}>
      <div style={{ display: "flex", gap: 10, alignItems: "center", flexWrap: "wrap" }}>
        <strong className={actionCls}>
          {rec.action}{rec.symbol && ` ${rec.symbol}`}
          {rec.sizing.notional && ` — ${fmtMoney(rec.sizing.notional, currency)}`}
        </strong>
        {rec.confidence !== null && (
          <span className="badge">confidence {(Number(rec.confidence) * 100).toFixed(0)}%</span>
        )}
        <span className={`badge ${rec.status === "EXECUTED" ? "FILLED" : rec.status}`}>{rec.status}</span>
        <span className="muted">{rec.model_id}</span>
        <span style={{ flex: 1 }} />
        {rec.status === "PENDING" && (
          <>
            <button onClick={() => onDecide(rec.id, true)}>
              {rec.action === "HOLD" || !rec.sizing.notional ? "Acknowledge" : "Approve & execute"}
            </button>
            <button className="ghost" onClick={() => onDecide(rec.id, false)}>Reject</button>
          </>
        )}
      </div>
      <p style={{ margin: "8px 0 0" }}>{rec.rationale}</p>
      <ImpactTable impact={rec.expected_impact} currency={currency} />
      <div className="muted" style={{ marginTop: 6 }}>
        {new Date(rec.created_at + (rec.created_at.endsWith("Z") ? "" : "Z")).toLocaleString()}
        {rec.executed_order_id && " · executed as an AI-assisted order"}
      </div>
    </div>
  );
}

export default function AssistantPage() {
  const { id = "" } = useParams();
  const [portfolio, setPortfolio] = useState<PortfolioView | null>(null);
  const [models, setModels] = useState<ModelView[]>([]);
  const [modelId, setModelId] = useState("");
  const [settings, setSettings] = useState<AiSettings | null>(null);
  const [recs, setRecs] = useState<RecommendationView[]>([]);
  const [analysis, setAnalysis] = useState("");
  const [disclaimer, setDisclaimer] = useState("");
  const [running, setRunning] = useState(false);
  const [error, setError] = useState("");

  const refresh = useCallback(() => {
    api.getPortfolio(id).then(setPortfolio).catch((e: Error) => setError(e.message));
    api.aiRecommendations(id).then(setRecs).catch(() => undefined);
    api.aiSettings(id).then(setSettings).catch(() => undefined);
    api.aiModels().then((res) => {
      setModels(res.models);
      setDisclaimer(res.disclaimer);
      const usable = res.models.filter((m) => m.installed || m.loaded);
      if (!modelId && usable.length > 0) {
        setModelId(res.default_model || usable[0].id);
      }
    }).catch(() => undefined);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [id]);
  useEffect(refresh, [refresh]);

  async function analyze() {
    setRunning(true);
    setError("");
    setAnalysis("");
    try {
      const result = await api.aiAnalyze(id, modelId || undefined);
      setAnalysis(result.analysis);
      refresh();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setRunning(false);
    }
  }

  async function decide(recId: string, approve: boolean) {
    setError("");
    try {
      if (approve) await api.aiApprove(id, recId);
      else await api.aiReject(id, recId);
      refresh();
    } catch (e) {
      setError((e as Error).message);
    }
  }

  async function saveSettings(patch: Partial<AiSettings>) {
    const updated = await api.aiUpdateSettings(id, patch);
    setSettings(updated);
  }

  const usableModels = models.filter((m) => m.installed || m.loaded);
  const pending = recs.filter((r) => r.status === "PENDING");
  const past = recs.filter((r) => r.status !== "PENDING");

  return (
    <div>
      <h1>
        AI Assistant{portfolio && <> — <Link to={`/portfolios/${id}`}>{portfolio.name}</Link></>}
      </h1>
      {error && <div className="error">{error}</div>}

      <div className="card">
        <h2>Analyze portfolio</h2>
        <div className="form-row">
          <div className="field">
            <label htmlFor="ai-model">Model</label>
            <select id="ai-model" value={modelId} onChange={(e) => setModelId(e.target.value)}>
              {usableModels.length === 0 && <option value="">No models installed</option>}
              {usableModels.map((m) => (
                <option key={m.id} value={m.id}>{m.name} ({m.parameters})</option>
              ))}
            </select>
          </div>
          <button onClick={analyze} disabled={running || usableModels.length === 0}>
            {running ? "Analyzing… (local inference)" : "Analyze portfolio"}
          </button>
          {usableModels.length === 0 && (
            <span className="muted">Install a model on the <Link to="/models">Models</Link> page first.</span>
          )}
        </div>
        {analysis && (
          <div style={{ marginTop: 12 }}>
            <p style={{ whiteSpace: "pre-wrap" }}>{analysis}</p>
          </div>
        )}
        <p className="muted" style={{ marginTop: 10 }}>
          {disclaimer || "AI output is informational and educational only."} The assistant
          only sees your real portfolio data and real market data; suggestions referencing
          anything else are dropped automatically.
        </p>
      </div>

      {settings && (
        <div className="card">
          <h2>AI trading guardrails</h2>
          <div className="form-row">
            <button
              className={`ghost ${settings.ai_auto_execute ? "active" : ""}`}
              onClick={() => saveSettings({ ai_auto_execute: !settings.ai_auto_execute })}
            >
              Auto-execute: {settings.ai_auto_execute ? "ON" : "OFF (review each)"}
            </button>
            <div className="field">
              <label htmlFor="ai-max-notional">Max per AI trade ($)</label>
              <input id="ai-max-notional" type="number" min="1" style={{ width: 120 }}
                defaultValue={settings.ai_max_trade_notional}
                onBlur={(e) => e.target.value && saveSettings({ ai_max_trade_notional: e.target.value } as never)} />
            </div>
            <div className="field">
              <label htmlFor="ai-max-trades">Max AI trades / day</label>
              <input id="ai-max-trades" type="number" min="1" max="50" style={{ width: 90 }}
                defaultValue={settings.ai_max_trades_per_day}
                onBlur={(e) => e.target.value && saveSettings({ ai_max_trades_per_day: Number(e.target.value) })} />
            </div>
          </div>
          <p className="muted">
            Every AI-executed trade is permanently marked {settings.ai_auto_execute ? "AI_AUTO" : "AI_ASSISTED"} and
            shown distinctly on charts and reports. Oversized suggestions are clamped to the cap.
          </p>
        </div>
      )}

      {pending.length > 0 && (
        <>
          <h2 style={{ margin: "18px 0 10px" }}>Pending recommendations</h2>
          {pending.map((r) => (
            <RecCard key={r.id} rec={r} currency={portfolio?.currency ?? "USD"} onDecide={decide} />
          ))}
        </>
      )}

      {past.length > 0 && (
        <>
          <h2 style={{ margin: "18px 0 10px" }}>History</h2>
          {past.map((r) => (
            <RecCard key={r.id} rec={r} currency={portfolio?.currency ?? "USD"} onDecide={decide} />
          ))}
        </>
      )}
    </div>
  );
}
