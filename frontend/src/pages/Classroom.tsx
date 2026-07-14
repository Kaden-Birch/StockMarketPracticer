import { FormEvent, useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import {
  api,
  AssignmentView,
  ClassroomProgress,
  ClassroomView,
  fmtMoney,
  ScenarioInfo,
} from "../api";

export default function ClassroomPage() {
  const [rooms, setRooms] = useState<ClassroomView[]>([]);
  const [selected, setSelected] = useState<string | null>(null);
  const [name, setName] = useState("");
  const [inviteCode, setInviteCode] = useState("");
  const [error, setError] = useState("");

  const refresh = useCallback(() => {
    api.classrooms().then(setRooms).catch((e: Error) => setError(e.message));
  }, []);
  useEffect(refresh, [refresh]);

  async function create(e: FormEvent) {
    e.preventDefault();
    setError("");
    try {
      const room = await api.createClassroom(name);
      setName("");
      refresh();
      setSelected(room.id);
    } catch (err) {
      setError((err as Error).message);
    }
  }

  async function join(e: FormEvent) {
    e.preventDefault();
    setError("");
    try {
      const room = await api.joinClassroom(inviteCode.trim());
      setInviteCode("");
      refresh();
      setSelected(room.id);
    } catch (err) {
      setError((err as Error).message);
    }
  }

  return (
    <div>
      <h1>Classroom</h1>
      {error && <div className="error">{error}</div>}
      <div className="card">
        <div style={{ display: "flex", gap: 24, flexWrap: "wrap" }}>
          <form onSubmit={create} style={{ display: "flex", gap: 8, alignItems: "center" }}>
            <input placeholder="New classroom name" value={name} required
              onChange={(e) => setName(e.target.value)} />
            <button type="submit">Create (as instructor)</button>
          </form>
          <form onSubmit={join} style={{ display: "flex", gap: 8, alignItems: "center" }}>
            <input placeholder="Invite code" value={inviteCode} required style={{ width: 140 }}
              onChange={(e) => setInviteCode(e.target.value)} />
            <button type="submit" className="ghost">Join as student</button>
          </form>
        </div>
        {rooms.length > 0 && (
          <div className="range-row" style={{ marginTop: 12 }}>
            {rooms.map((r) => (
              <button key={r.id} className={`ghost ${selected === r.id ? "active" : ""}`}
                onClick={() => setSelected(r.id)}>
                {r.name} {r.role === "instructor" ? "🎓" : ""}
              </button>
            ))}
          </div>
        )}
        {rooms.length === 0 && <p className="muted">No classrooms yet.</p>}
      </div>
      {selected && <ClassroomDetail id={selected} setError={setError}
        onGone={() => { setSelected(null); refresh(); }} />}
    </div>
  );
}

function ClassroomDetail({ id, setError, onGone }:
  { id: string; setError: (e: string) => void; onGone: () => void }) {
  const [room, setRoom] = useState<ClassroomView | null>(null);
  const [assignments, setAssignments] = useState<AssignmentView[]>([]);
  const [progress, setProgress] = useState<ClassroomProgress | null>(null);
  const [catalog, setCatalog] = useState<ScenarioInfo[]>([]);
  const [title, setTitle] = useState("");
  const [scenarioId, setScenarioId] = useState("");
  const [mandate, setMandate] = useState("");
  const [balance, setBalance] = useState("100000");

  const refresh = useCallback(() => {
    api.classroomDetail(id).then(setRoom).catch((e: Error) => setError(e.message));
    api.assignments(id).then(setAssignments).catch(() => undefined);
    api.classroomProgress(id).then(setProgress).catch(() => setProgress(null));
    api.scenarios().then((r) => setCatalog(r.catalog)).catch(() => undefined);
  }, [id, setError]);
  useEffect(refresh, [refresh]);

  if (!room) return null;

  async function createAssignment(e: FormEvent) {
    e.preventDefault();
    setError("");
    try {
      await api.createAssignment(id, {
        title, scenario_id: scenarioId, mandate, starting_balance: balance,
      });
      setTitle("");
      refresh();
    } catch (err) {
      setError((err as Error).message);
    }
  }

  async function start(a: AssignmentView) {
    setError("");
    try {
      await api.startAssignment(a.id);
      refresh();
    } catch (err) {
      setError((err as Error).message);
    }
  }

  async function remove() {
    if (!window.confirm(`Delete classroom "${room?.name}"?`)) return;
    try {
      await api.deleteClassroom(id);
      onGone();
    } catch (err) {
      setError((err as Error).message);
    }
  }

  return (
    <>
      <div className="card">
        <div style={{ display: "flex", alignItems: "baseline", gap: 10 }}>
          <h2 style={{ marginBottom: 0 }}>{room.name}</h2>
          <span className="muted">taught by {room.instructor}</span>
          <span style={{ flex: 1 }} />
          {room.is_instructor && (
            <button className="ghost" onClick={remove}>Delete classroom</button>
          )}
        </div>
        {room.invite_code && (
          <p className="muted">Student invite code: <code>{room.invite_code}</code></p>
        )}
        <p className="muted">
          {room.students?.length ?? 0} student(s):{" "}
          {room.students?.map((s) => s.username).join(", ") || "none yet"}
        </p>
      </div>

      {room.is_instructor && (
        <div className="card">
          <h3>New assignment</h3>
          <form onSubmit={createAssignment}
            style={{ display: "flex", gap: 8, flexWrap: "wrap", alignItems: "center" }}>
            <input placeholder="Title" value={title} required
              onChange={(e) => setTitle(e.target.value)} style={{ minWidth: 200 }} />
            <select value={scenarioId} onChange={(e) => setScenarioId(e.target.value)}>
              <option value="">Live market</option>
              {catalog.map((s) => (
                <option key={s.id} value={s.id}>Scenario: {s.name}</option>
              ))}
            </select>
            <select value={mandate} onChange={(e) => setMandate(e.target.value)}>
              <option value="">No mandate</option>
              <option value="retirement">Retirement Fund mandate</option>
              <option value="growth">Growth Fund mandate</option>
              <option value="dividend">Dividend Fund mandate</option>
              <option value="technology">Technology Fund mandate</option>
            </select>
            <input value={balance} title="Starting balance" style={{ width: 110 }}
              onChange={(e) => setBalance(e.target.value)} />
            <button type="submit">Assign</button>
          </form>
        </div>
      )}

      <div className="card">
        <h3>Assignments</h3>
        {assignments.length === 0 && <p className="muted">No assignments yet.</p>}
        {assignments.map((a) => (
          <div key={a.id}
            style={{ borderBottom: "1px solid var(--border)", padding: "8px 0",
                     display: "flex", gap: 10, alignItems: "center", flexWrap: "wrap" }}>
            <strong>{a.title}</strong>
            <span className="muted">
              {a.scenario_id ? `scenario: ${a.scenario_id}` : "live market"}
              {a.mandate && ` · mandate: ${a.mandate}`} · {fmtMoney(a.starting_balance)}
            </span>
            <span style={{ flex: 1 }} />
            {a.my_entry ? (
              a.my_entry.scenario_session_id ? (
                <Link to="/scenarios"><button className="ghost">Continue in Scenarios</button></Link>
              ) : (
                <Link to={`/portfolios/${a.my_entry.portfolio_id}`}>
                  <button className="ghost">Open portfolio</button>
                </Link>
              )
            ) : (
              <button onClick={() => start(a)}>Start</button>
            )}
          </div>
        ))}
      </div>

      {progress && (
        <div className="card">
          <h3>Progress dashboard</h3>
          {progress.progress.map((block) => (
            <div key={block.assignment.id} style={{ marginBottom: 14 }}>
              <strong>{block.assignment.title}</strong>
              <table style={{ marginTop: 6 }}>
                <thead>
                  <tr><th>Student</th><th>Started</th><th>Value</th><th>Return</th>
                      <th>Scenario</th><th>Mandate</th></tr>
                </thead>
                <tbody>
                  {block.students.map((s) => (
                    <tr key={s.username}>
                      <td>{s.username}</td>
                      <td>{s.started ? "✓" : "—"}</td>
                      <td>{s.value ? fmtMoney(s.value) : "—"}</td>
                      <td>{s.return_pct ? `${s.return_pct}%` : "—"}</td>
                      <td>
                        {s.scenario_day
                          ? `day ${s.scenario_day}/${s.scenario_total_days}${s.completed ? " ✓" : ""}`
                          : "—"}
                      </td>
                      <td>
                        {s.mandate_compliant === true ? "compliant"
                          : s.mandate_compliant === false ? "VIOLATION"
                          : "—"}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ))}
        </div>
      )}
    </>
  );
}
