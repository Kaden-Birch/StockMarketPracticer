import { FormEvent, useCallback, useEffect, useState } from "react";
import { api, DiscordConfigView } from "../api";

/** Discord integration settings (roadmap 7.5) — configured entirely here,
 * never on the command line. Secrets are stored encrypted and not echoed. */
export default function DiscordCard() {
  const [config, setConfig] = useState<DiscordConfigView | null>(null);
  const [webhook, setWebhook] = useState("");
  const [token, setToken] = useState("");
  const [note, setNote] = useState("");
  const [error, setError] = useState("");
  const [preview, setPreview] = useState("");
  const [previewCmd, setPreviewCmd] = useState("portfolio");

  const refresh = useCallback(() => {
    api.discordConfig().then(setConfig).catch(() => setConfig(null));
  }, []);
  useEffect(refresh, [refresh]);

  if (config === null) return null; // discord module disabled

  async function save(e: FormEvent) {
    e.preventDefault();
    setError("");
    setNote("");
    try {
      const body: Record<string, unknown> = {};
      if (webhook) body.webhook_url = webhook;
      if (token) body.bot_token = token;
      const res = await api.setDiscordConfig(body);
      setWebhook("");
      setToken("");
      setNote(res.note || "Saved.");
      refresh();
    } catch (err) {
      setError((err as Error).message);
    }
  }

  async function toggleEvent(ev: string) {
    if (!config) return;
    const events = config.events.includes(ev)
      ? config.events.filter((e) => e !== ev)
      : [...config.events, ev];
    try {
      await api.setDiscordConfig({ events });
      refresh();
    } catch (err) {
      setError((err as Error).message);
    }
  }

  async function test() {
    setError("");
    setNote("");
    try {
      await api.discordTest();
      setNote("Test message delivered to Discord ✓");
    } catch (err) {
      setError((err as Error).message);
    }
  }

  async function runPreview() {
    setError("");
    try {
      const r = await api.discordPreview(previewCmd);
      setPreview(r.reply);
    } catch (err) {
      setError((err as Error).message);
    }
  }

  return (
    <div className="card">
      <h2>Discord integration</h2>
      {error && <div className="error">{error}</div>}
      {note && <p className="muted">{note}</p>}
      <p className="muted">
        Webhook: {config.webhook_configured ? "configured ✓" : "not configured"} ·
        Bot token: {config.bot_token_configured ? "stored ✓" : "not stored"} ·
        Slash commands: {config.gateway_available
          ? "available (bot starts when a token is stored)"
          : "need the optional discord.py dependency; webhook notifications work without it"}
      </p>
      <form onSubmit={save} className="form-row" style={{ flexWrap: "wrap", gap: 8 }}>
        <div className="field" style={{ flex: 1, minWidth: 260 }}>
          <label htmlFor="dc-webhook">Webhook URL (notifications)</label>
          <input id="dc-webhook" type="password" value={webhook}
            placeholder="https://discord.com/api/webhooks/… (stored encrypted)"
            onChange={(e) => setWebhook(e.target.value)} style={{ width: "100%" }} />
        </div>
        <div className="field" style={{ flex: 1, minWidth: 260 }}>
          <label htmlFor="dc-token">Bot token (slash commands, optional)</label>
          <input id="dc-token" type="password" value={token}
            placeholder="stored encrypted"
            onChange={(e) => setToken(e.target.value)} style={{ width: "100%" }} />
        </div>
        <button type="submit">Save</button>
        {config.webhook_configured && (
          <button type="button" className="ghost" onClick={test}>Send test message</button>
        )}
      </form>
      <h3 style={{ marginTop: 12 }}>Notify Discord about</h3>
      <div style={{ display: "flex", gap: 14, flexWrap: "wrap" }}>
        {config.available_events.map((ev) => (
          <label key={ev} style={{ display: "flex", gap: 4, alignItems: "center" }}>
            <input type="checkbox" checked={config.events.includes(ev)}
              onChange={() => toggleEvent(ev)} />
            {ev.replace(/_/g, " ")}
          </label>
        ))}
      </div>
      <h3 style={{ marginTop: 12 }}>Try a slash command</h3>
      <div style={{ display: "flex", gap: 8, alignItems: "center", flexWrap: "wrap" }}>
        <select value={previewCmd} onChange={(e) => setPreviewCmd(e.target.value)}>
          {Object.entries(config.commands).map(([cmd, desc]) => (
            <option key={cmd} value={cmd}>/{cmd} — {desc}</option>
          ))}
        </select>
        <button className="ghost" onClick={runPreview}>Preview reply</button>
      </div>
      {preview && (
        <pre style={{ marginTop: 8, whiteSpace: "pre-wrap" }}>{preview}</pre>
      )}
    </div>
  );
}
