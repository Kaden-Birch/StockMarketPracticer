import { FormEvent, useCallback, useEffect, useState } from "react";
import { api, ModuleView } from "../api";

export default function SettingsPage() {
  const [providers, setProviders] = useState<{ stored_keys: string[]; active_chain: string[] } | null>(null);
  const [avKey, setAvKey] = useState("");
  const [note, setNote] = useState("");
  const [backups, setBackups] = useState<{ name: string; size_bytes: number; created_at: string }[]>([]);
  const [audit, setAudit] = useState<{ actor: string; action: string; entity: string; created_at: string }[]>([]);
  const [modules, setModules] = useState<ModuleView[]>([]);
  const [error, setError] = useState("");

  const refresh = useCallback(() => {
    api.adminProviders().then(setProviders).catch((e: Error) => setError(e.message));
    api.listBackups().then(setBackups).catch(() => undefined);
    api.auditLog().then(setAudit).catch(() => undefined);
    api.modules().then((r) => setModules(r.modules)).catch(() => undefined);
  }, []);

  async function toggleModule(m: ModuleView) {
    setError("");
    try {
      const res = await api.setModule(m.id, m.state !== "RUNNING");
      const affected = res.dependents_affected.length
        ? ` Dependent modules also affected: ${res.dependents_affected.join(", ")}.`
        : "";
      setNote(`${m.name} will be ${m.state === "RUNNING" ? "disabled" : "enabled"} ${res.applies}.${affected}`);
      refresh();
    } catch (e) {
      setError((e as Error).message);
    }
  }
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
        <h2>Modules</h2>
        <p className="muted">
          Optional features run as independent modules. Disabling one removes its
          tabs, API routes, and background jobs on the next restart; the core trading
          engine is unaffected. Modules that depend on a disabled one auto-disable.
        </p>
        <table>
          <thead>
            <tr><th>Module</th><th>Version</th><th>Depends on</th><th>State</th><th></th></tr>
          </thead>
          <tbody>
            {modules.map((m) => (
              <tr key={m.id}>
                <td>
                  <strong>{m.name}</strong>
                  <div className="muted">{m.description}</div>
                  {m.error && <div className="error">Failed to start: {m.error.split("\n")[0]}</div>}
                  {m.disabled_reason && <div className="muted">{m.disabled_reason}</div>}
                </td>
                <td className="muted">{m.version}</td>
                <td className="muted">{m.dependencies.join(", ") || "—"}</td>
                <td>
                  <span className={`badge ${m.state === "RUNNING" ? "FILLED" : m.state === "FAILED" ? "REJECTED" : "CANCELLED"}`}>
                    {m.state}
                  </span>
                  {m.pending_change && <div className="muted" style={{ fontSize: 11 }}>{m.pending_change}</div>}
                </td>
                <td>
                  <button className="ghost" onClick={() => toggleModule(m)}>
                    {m.state === "RUNNING" ? "Disable" : "Enable"}
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

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
