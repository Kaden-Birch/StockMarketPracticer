import { FormEvent, useCallback, useEffect, useState } from "react";
import { api, UserView } from "../api";

/** Admin user management (roadmap 7.1): invite players to this server.
 * Hidden in desktop mode / for non-admins (the API returns 403/409). */
export default function UsersCard() {
  const [users, setUsers] = useState<UserView[] | null>(null);
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [role, setRole] = useState("trader");
  const [error, setError] = useState("");

  const refresh = useCallback(() => {
    api.listUsers().then(setUsers).catch(() => setUsers(null));
  }, []);
  useEffect(refresh, [refresh]);

  if (users === null || users.length === 0) return null; // desktop mode or non-admin

  async function create(e: FormEvent) {
    e.preventDefault();
    setError("");
    try {
      await api.createUser({ username, password, role });
      setUsername("");
      setPassword("");
      refresh();
    } catch (err) {
      setError((err as Error).message);
    }
  }

  async function remove(name: string) {
    if (!window.confirm(`Delete user "${name}"? Their portfolios remain but become admin-only.`)) return;
    setError("");
    try {
      await api.deleteUser(name);
      refresh();
    } catch (err) {
      setError((err as Error).message);
    }
  }

  return (
    <div className="card">
      <h2>Users</h2>
      {error && <div className="error">{error}</div>}
      <table>
        <thead>
          <tr><th>Username</th><th>Role</th><th>Since</th><th></th></tr>
        </thead>
        <tbody>
          {users.map((u) => (
            <tr key={u.username}>
              <td>{u.username}</td>
              <td className="muted">{u.role}</td>
              <td className="muted">{new Date(u.created_at).toLocaleDateString()}</td>
              <td>
                <button className="ghost" onClick={() => remove(u.username)}>Delete</button>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      <form onSubmit={create} className="form-row" style={{ marginTop: 10, gap: 8, flexWrap: "wrap" }}>
        <input placeholder="Username" value={username} required minLength={3}
          onChange={(e) => setUsername(e.target.value)} />
        <input placeholder="Password (8+ chars)" type="password" value={password}
          required minLength={8} onChange={(e) => setPassword(e.target.value)} />
        <select value={role} onChange={(e) => setRole(e.target.value)}>
          <option value="trader">Trader</option>
          <option value="viewer">Viewer</option>
          <option value="admin">Admin</option>
        </select>
        <button type="submit">Add user</button>
      </form>
    </div>
  );
}
