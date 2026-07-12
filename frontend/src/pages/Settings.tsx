import { FormEvent, useCallback, useEffect, useState } from "react";
import { api } from "../api";

export default function SettingsPage() {
  const [providers, setProviders] = useState<{ stored_keys: string[]; active_chain: string[] } | null>(null);
  const [avKey, setAvKey] = useState("");
  const [note, setNote] = useState("");
  const [backups, setBackups] = useState<{ name: string; size_bytes: number; created_at: string }[]>([]);
  const [audit, setAudit] = useState<{ actor: string; action: string; entity: string; created_at: string }[]>([]);
  const [error, setError] = useState("");

  const refresh = useCallback(() => {
    api.adminProviders().then(setProviders).catch((e: Error) => setError(e.message));
    api.listBackups().then(setBackups).catch(() => undefined);
    api.auditLog().then(setAudit).catch(() => undefined);
  }, []);
  useEffect(refresh, [refresh]);

  async function saveKey(e: FormEvent) {
    e.preventDefault();
    setError("");
    setNote("");
    try {
      const res = await api.setProviderKey("alphavantage", avKey);
      setAvKey("");
      setNote(res.note);
      refresh();
    } catch (err) {
      setError((err as Error).message);
    }
  }

  async function backupNow() {
    setError("");
    try {
      const res = await api.runBackup();
      setNote(`Backup written: ${res.backup}`);
      refresh();
    } catch (err) {
      setError((err as Error).message);
    }
  }

  return (
    <div>
      <h1>Settings</h1>
      {error && <div className="error">{error}</div>}
      {note && <div className="card" style={{ borderColor: "var(--gain)" }}>{note}</div>}

      <div className="card">
        <h2>Market data providers</h2>
        {providers && (
          <p className="muted">
            Active chain: {providers.active_chain.join(" → ")}
            {providers.stored_keys.length > 0 &&
              ` · stored keys: ${providers.stored_keys.join(", ")}`}
          </p>
        )}
        <form className="form-row" onSubmit={saveKey}>
          <div className="field" style={{ flex: 1, maxWidth: 420 }}>
            <label htmlFor="av-key">Alpha Vantage API key</label>
            <input id="av-key" type="password" value={avKey} required
              placeholder="stored encrypted at rest"
              onChange={(e) => setAvKey(e.target.value)} style={{ width: "100%" }} />
          </div>
          <button type="submit">Save key</button>
          {providers?.stored_keys.includes("alphavantage") && (
            <button type="button" className="ghost"
              onClick={async () => { await api.deleteProviderKey("alphavantage"); refresh(); }}>
              Remove stored key
            </button>
          )}
        </form>
      </div>

      <div className="card">
        <h2>Backups</h2>
        <button onClick={backupNow}>Back up now</button>
        <span className="muted" style={{ marginLeft: 10 }}>
          Automatic backups run daily; the newest 7 are kept.
        </span>
        {backups.length > 0 && (
          <table style={{ marginTop: 10 }}>
            <thead>
              <tr><th>File</th><th className="num">Size</th><th>Created</th></tr>
            </thead>
            <tbody>
              {backups.map((b) => (
                <tr key={b.name}>
                  <td>{b.name}</td>
                  <td className="num">{(b.size_bytes / 1024).toFixed(0)} KB</td>
                  <td className="muted">{new Date(b.created_at).toLocaleString()}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      <div className="card">
        <h2>Audit log</h2>
        {audit.length === 0 ? (
          <p className="muted">No audited events yet.</p>
        ) : (
          <table>
            <thead>
              <tr><th>When</th><th>Actor</th><th>Action</th><th>Entity</th></tr>
            </thead>
            <tbody>
              {audit.map((a, i) => (
                <tr key={i}>
                  <td className="muted">{new Date(a.created_at + (a.created_at.endsWith("Z") ? "" : "Z")).toLocaleString()}</td>
                  <td>{a.actor}</td>
                  <td>{a.action}</td>
                  <td className="muted">{a.entity}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
}
