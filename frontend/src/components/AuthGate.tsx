import { FormEvent, ReactNode, useCallback, useEffect, useState } from "react";
import { api, AuthStatus } from "../api";

/** Blocks the app behind setup/login when the server runs with
 * AIPTP_AUTH=required; transparent in desktop (disabled) mode. */
export default function AuthGate({ children }: { children: ReactNode }) {
  const [status, setStatus] = useState<AuthStatus | null>(null);
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  const check = useCallback(() => {
    api.authStatus().then(setStatus).catch(() => {
      // API unreachable — render the app shell; requests will surface errors
      setStatus({ mode: "disabled", state: "authenticated" });
    });
  }, []);
  useEffect(check, [check]);

  useEffect(() => {
    const handler = () => check();
    window.addEventListener("aiptp-auth-required", handler);
    return () => window.removeEventListener("aiptp-auth-required", handler);
  }, [check]);

  if (status === null) return null;
  if (status.state === "authenticated") return <>{children}</>;

  const isSetup = status.state === "setup_required";

  async function submit(e: FormEvent) {
    e.preventDefault();
    setError("");
    setBusy(true);
    try {
      if (isSetup) await api.authSetup(username, password);
      else await api.authLogin(username, password);
      setPassword("");
      check();
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <main className="content" style={{ margin: "10vh auto", maxWidth: 420 }}>
      <div className="card">
        <h1>{isSetup ? "Welcome to AIPTP" : "Sign in"}</h1>
        <p className="muted">
          {isSetup
            ? "This server requires an administrator account. Create one to finish setup."
            : "Enter your credentials to continue."}
        </p>
        <form onSubmit={submit}>
          <div className="field" style={{ marginBottom: 10 }}>
            <label htmlFor="auth-user">Username</label>
            <input id="auth-user" value={username} required minLength={3}
              autoComplete="username" onChange={(e) => setUsername(e.target.value)} />
          </div>
          <div className="field" style={{ marginBottom: 14 }}>
            <label htmlFor="auth-pass">Password {isSetup && <span className="muted">(min 8 chars)</span>}</label>
            <input id="auth-pass" type="password" value={password} required minLength={8}
              autoComplete={isSetup ? "new-password" : "current-password"}
              onChange={(e) => setPassword(e.target.value)} />
          </div>
          <button type="submit" disabled={busy} style={{ width: "100%" }}>
            {busy ? "…" : isSetup ? "Create account" : "Sign in"}
          </button>
        </form>
        {error && <div className="error">{error}</div>}
        <p className="muted" style={{ marginTop: 12 }}>
          Paper trading only — simulated funds, real market data.
        </p>
      </div>
    </main>
  );
}
