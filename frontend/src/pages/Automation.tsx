import { FormEvent, useCallback, useEffect, useState } from "react";
import { useParams, Link } from "react-router-dom";
import { api, AutomationRuleView, PortfolioView, RuleFireView } from "../api";

type CondType =
  | "price" | "pct_move" | "indicator" | "cash" | "allocation"
  | "schedule" | "dividend_event";

interface CondRow {
  type: CondType;
  symbol: string;
  op: string;
  value: string;
  name: string; // indicator name
  period: string;
  at: string; // schedule HH:MM
  within_days: string;
}

const emptyCond = (): CondRow => ({
  type: "price", symbol: "", op: "<", value: "",
  name: "RSI", period: "14", at: "14:30", within_days: "3",
});

function condToNode(c: CondRow): object {
  switch (c.type) {
    case "price":
    case "pct_move":
      return { [c.type]: { symbol: c.symbol, op: c.op, value: Number(c.value) } };
    case "indicator":
      return { indicator: { symbol: c.symbol, name: c.name, period: Number(c.period), op: c.op, value: Number(c.value) } };
    case "cash":
      return { cash: { op: c.op, value: Number(c.value) } };
    case "allocation":
      return { allocation: { symbol: c.symbol, op: c.op, value: Number(c.value) } };
    case "schedule":
      return { schedule: { at: c.at } };
    case "dividend_event":
      return { dividend_event: { symbol: c.symbol, within_days: Number(c.within_days) } };
  }
}

function describeTrigger(trigger: object): string {
  return JSON.stringify(trigger)
    .replace(/[{}"[\]]/g, " ")
    .replace(/\s+/g, " ")
    .trim();
}

function RuleFires({ portfolioId, ruleId }: { portfolioId: string; ruleId: string }) {
  const [fires, setFires] = useState<RuleFireView[] | null>(null);
  useEffect(() => {
    api.ruleFires(portfolioId, ruleId).then(setFires).catch(() => setFires([]));
  }, [portfolioId, ruleId]);
  if (fires === null) return <p className="muted">Loading…</p>;
  if (fires.length === 0) return <p className="muted">Never fired.</p>;
  return (
    <table>
      <thead>
        <tr><th>Fired</th><th>Result</th><th>Detail</th></tr>
      </thead>
      <tbody>
        {fires.map((f) => (
          <tr key={f.id}>
            <td className="muted">{new Date(f.fired_at + (f.fired_at.endsWith("Z") ? "" : "Z")).toLocaleString()}</td>
            <td><span className={`badge ${f.result === "EXECUTED" || f.result === "NOTIFIED" ? "FILLED" : "REJECTED"}`}>{f.result}</span></td>
            <td className="muted">{f.detail}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

export default function AutomationPage() {
  const { id = "" } = useParams();
  const [portfolio, setPortfolio] = useState<PortfolioView | null>(null);
  const [rules, setRules] = useState<AutomationRuleView[]>([]);
  const [expanded, setExpanded] = useState<string | null>(null);
  const [error, setError] = useState("");

  // builder state
  const [name, setName] = useState("");
  const [combinator, setCombinator] = useState<"all" | "any">("all");
  const [conds, setConds] = useState<CondRow[]>([emptyCond()]);
  const [actionType, setActionType] = useState("NOTIFY");
  const [actSymbol, setActSymbol] = useState("");
  const [actSizing, setActSizing] = useState<"notional" | "quantity" | "percent">("notional");
  const [actAmount, setActAmount] = useState("");
  const [actMessage, setActMessage] = useState("");
  const [cooldown, setCooldown] = useState("3600");
  const [maxFires, setMaxFires] = useState("5");
  const [fireOnce, setFireOnce] = useState(false);

  const refresh = useCallback(() => {
    Promise.all([api.getPortfolio(id), api.listRules(id)])
      .then(([p, r]) => {
        setPortfolio(p);
        setRules(r);
      })
      .catch((e: Error) => setError(e.message));
  }, [id]);
  useEffect(refresh, [refresh]);

  function setCond(i: number, patch: Partial<CondRow>) {
    setConds(conds.map((c, j) => (j === i ? { ...c, ...patch } : c)));
  }

  async function create(e: FormEvent) {
    e.preventDefault();
    setError("");
    const nodes = conds.map(condToNode);
    const trigger = nodes.length === 1 ? nodes[0] : { [combinator]: nodes };
    const action_params: Record<string, unknown> =
      actionType === "NOTIFY"
        ? { message: actMessage }
        : { symbol: actSymbol, [actSizing]: actAmount };
    try {
      await api.createRule(id, {
        name,
        trigger,
        action_type: actionType,
        action_params,
        cooldown_seconds: Number(cooldown),
        max_fires_per_day: Number(maxFires),
        fire_once: fireOnce,
      });
      setName("");
      setConds([emptyCond()]);
      refresh();
    } catch (err) {
      setError((err as Error).message);
    }
  }

  const needsSymbol = (t: CondType) =>
    ["price", "pct_move", "indicator", "allocation", "dividend_event"].includes(t);
  const needsOpValue = (t: CondType) =>
    ["price", "pct_move", "indicator", "cash", "allocation"].includes(t);

  return (
    <div>
      <h1>
        Automation{portfolio && <> — <Link to={`/portfolios/${id}`}>{portfolio.name}</Link></>}
      </h1>
      {error && <div className="error">{error}</div>}

      <div className="card">
        <h2>Rules</h2>
        {rules.length === 0 && <p className="muted">No rules yet — build one below.</p>}
        {rules.map((r) => (
          <div key={r.id} style={{ borderBottom: "1px solid var(--border)", padding: "10px 0" }}>
            <div style={{ display: "flex", alignItems: "center", gap: 10, flexWrap: "wrap" }}>
              <strong>{r.name}</strong>
              <span className={`badge ${r.enabled ? "FILLED" : "CANCELLED"}`}>
                {r.enabled ? "ACTIVE" : "PAUSED"}
              </span>
              {r.fire_once && (
                <span className="badge" title="Pauses itself permanently after its first fire">
                  ONE-SHOT
                </span>
              )}
              <span className="muted">
                when {describeTrigger(r.trigger)} → {r.action_type}{" "}
                {JSON.stringify(r.action_params).replace(/[{}"]/g, " ")}
              </span>
              <span style={{ flex: 1 }} />
              <span className="muted">{r.fire_count} fires</span>
              <button className="ghost" onClick={() => setExpanded(expanded === r.id ? null : r.id)}>
                {expanded === r.id ? "Hide log" : "Fire log"}
              </button>
              <button
                className="ghost"
                onClick={async () => {
                  await api.updateRule(id, r.id, { enabled: !r.enabled });
                  refresh();
                }}
              >
                {r.enabled ? "Pause" : "Resume"}
              </button>
              <button
                className="ghost"
                onClick={async () => {
                  if (window.confirm(`Delete rule "${r.name}"?`)) {
                    await api.deleteRule(id, r.id);
                    refresh();
                  }
                }}
              >
                Delete
              </button>
            </div>
            {expanded === r.id && (
              <div style={{ marginTop: 8 }}>
                <RuleFires portfolioId={id} ruleId={r.id} />
              </div>
            )}
          </div>
        ))}
      </div>

      <form className="card" onSubmit={create}>
        <h2>New rule</h2>
        <div className="form-row" style={{ marginBottom: 10 }}>
          <div className="field">
            <label htmlFor="rule-name">Name</label>
            <input id="rule-name" value={name} onChange={(e) => setName(e.target.value)}
              required placeholder="Buy the dip" style={{ width: 220 }} />
          </div>
          {conds.length > 1 && (
            <div className="field">
              <label htmlFor="rule-comb">Conditions match</label>
              <select id="rule-comb" value={combinator}
                onChange={(e) => setCombinator(e.target.value as "all" | "any")}>
                <option value="all">ALL (and)</option>
                <option value="any">ANY (or)</option>
              </select>
            </div>
          )}
        </div>

        {conds.map((c, i) => (
          <div className="form-row" key={i} style={{ marginBottom: 8 }}>
            <div className="field">
              <label>Condition {i + 1}</label>
              <select value={c.type} onChange={(e) => setCond(i, { type: e.target.value as CondType })}>
                <option value="price">Price</option>
                <option value="pct_move">% move today</option>
                <option value="indicator">Indicator</option>
                <option value="cash">Cash balance</option>
                <option value="allocation">Allocation %</option>
                <option value="schedule">Schedule (UTC)</option>
                <option value="dividend_event">Dividend received</option>
              </select>
            </div>
            {needsSymbol(c.type) && (
              <div className="field">
                <label>Symbol</label>
                <input value={c.symbol} required style={{ width: 90 }}
                  onChange={(e) => setCond(i, { symbol: e.target.value.toUpperCase() })} />
              </div>
            )}
            {c.type === "indicator" && (
              <>
                <div className="field">
                  <label>Indicator</label>
                  <select value={c.name} onChange={(e) => setCond(i, { name: e.target.value })}>
                    <option>RSI</option>
                    <option>SMA</option>
                    <option>EMA</option>
                  </select>
                </div>
                <div className="field">
                  <label>Period</label>
                  <input type="number" min="1" value={c.period} style={{ width: 70 }}
                    onChange={(e) => setCond(i, { period: e.target.value })} />
                </div>
              </>
            )}
            {needsOpValue(c.type) && (
              <>
                <div className="field">
                  <label>Is</label>
                  <select value={c.op} onChange={(e) => setCond(i, { op: e.target.value })}>
                    <option value="<">&lt;</option>
                    <option value="<=">&le;</option>
                    <option value=">">&gt;</option>
                    <option value=">=">&ge;</option>
                  </select>
                </div>
                <div className="field">
                  <label>Value</label>
                  <input type="number" step="any" value={c.value} required style={{ width: 100 }}
                    onChange={(e) => setCond(i, { value: e.target.value })} />
                </div>
              </>
            )}
            {c.type === "schedule" && (
              <div className="field">
                <label>At (HH:MM UTC)</label>
                <input value={c.at} pattern="\d{2}:\d{2}" style={{ width: 90 }}
                  onChange={(e) => setCond(i, { at: e.target.value })} />
              </div>
            )}
            {c.type === "dividend_event" && (
              <div className="field">
                <label>Within days</label>
                <input type="number" min="1" value={c.within_days} style={{ width: 80 }}
                  onChange={(e) => setCond(i, { within_days: e.target.value })} />
              </div>
            )}
            {conds.length > 1 && (
              <button type="button" className="ghost"
                onClick={() => setConds(conds.filter((_, j) => j !== i))}>
                Remove
              </button>
            )}
          </div>
        ))}
        <button type="button" className="ghost" onClick={() => setConds([...conds, emptyCond()])}>
          + Add condition
        </button>

        <div className="form-row" style={{ marginTop: 14 }}>
          <div className="field">
            <label htmlFor="rule-action">Then</label>
            <select id="rule-action" value={actionType} onChange={(e) => setActionType(e.target.value)}>
              <option value="NOTIFY">Notify only</option>
              <option value="BUY">Buy</option>
              <option value="SELL">Sell</option>
            </select>
          </div>
          {actionType === "NOTIFY" ? (
            <div className="field" style={{ flex: 1 }}>
              <label htmlFor="rule-msg">Message</label>
              <input id="rule-msg" value={actMessage} style={{ width: "100%" }}
                onChange={(e) => setActMessage(e.target.value)} placeholder="Condition met!" />
            </div>
          ) : (
            <>
              <div className="field">
                <label>Symbol</label>
                <input value={actSymbol} required style={{ width: 90 }}
                  onChange={(e) => setActSymbol(e.target.value.toUpperCase())} />
              </div>
              <div className="field">
                <label>Size by</label>
                <select value={actSizing}
                  onChange={(e) => setActSizing(e.target.value as typeof actSizing)}>
                  <option value="notional">Amount ($)</option>
                  <option value="quantity">Shares</option>
                  <option value="percent">{actionType === "SELL" ? "% of position" : "% of cash"}</option>
                </select>
              </div>
              <div className="field">
                <label>Size</label>
                <input type="number" step="any" min="0" value={actAmount} required
                  style={{ width: 100 }} onChange={(e) => setActAmount(e.target.value)} />
              </div>
            </>
          )}
          <div className="field">
            <label htmlFor="rule-cd">Cooldown (s)</label>
            <input id="rule-cd" type="number" min="0" value={cooldown} style={{ width: 90 }}
              onChange={(e) => setCooldown(e.target.value)} />
          </div>
          <div className="field">
            <label htmlFor="rule-max">Max fires/day</label>
            <input id="rule-max" type="number" min="1" max="100" value={maxFires} style={{ width: 80 }}
              onChange={(e) => setMaxFires(e.target.value)} />
          </div>
          <div className="field">
            <label htmlFor="rule-once"
              title="After the first fire, the rule pauses itself permanently — resume it to arm it again">
              Fire once ever
            </label>
            <input id="rule-once" type="checkbox" checked={fireOnce}
              onChange={(e) => setFireOnce(e.target.checked)} />
          </div>
          <button type="submit">Create rule</button>
        </div>
        <div className="muted" style={{ marginTop: 8 }}>
          Rules are edge-triggered (fire once per condition transition), respect cooldowns and
          daily caps, and run 24/7 in server mode. Every fire is logged.
        </div>
      </form>
    </div>
  );
}
