import { FormEvent, useEffect, useState } from "react";
import { useSearchParams } from "react-router-dom";
import {
  api,
  ConceptDetail,
  ConceptSummary,
  LearnProgress,
  LearnSuggestion,
  PathView,
  QuizResult,
} from "../api";

const LEVELS = ["beginner", "intermediate", "advanced"] as const;

export default function LearnPage() {
  const [params, setParams] = useSearchParams();
  const tab = params.get("tab") ?? "dictionary";
  const conceptId = params.get("concept");
  const [suggestions, setSuggestions] = useState<LearnSuggestion[]>([]);

  useEffect(() => {
    api.learnSuggestions().then(setSuggestions).catch(() => undefined);
  }, []);

  return (
    <div>
      <h1>Learn</h1>
      {suggestions.length > 0 && !conceptId && (
        <div className="card" style={{ borderColor: "var(--gain)" }}>
          <h2>Suggested for you</h2>
          <p className="muted">
            Spotted in your actual portfolio and mentor notes — not generic tips.
          </p>
          {suggestions.map((s) => (
            <p key={s.concept_id}>
              💡 {s.why}{" "}
              <button className="ghost"
                onClick={() => setParams({ concept: s.concept_id })}>
                Learn: {s.term ?? s.concept_id}
              </button>
            </p>
          ))}
        </div>
      )}
      {conceptId ? (
        <ConceptView id={conceptId} onBack={() => setParams({ tab })}
          onOpen={(cid) => setParams({ concept: cid })} />
      ) : (
        <>
          <div className="range-row" role="tablist" aria-label="Learn sections">
            {[["dictionary", "Dictionary"], ["paths", "Learning paths"],
              ["simulators", "Simulators"], ["progress", "My progress"]].map(([id, label]) => (
              <button key={id} className={`ghost ${tab === id ? "active" : ""}`}
                role="tab" aria-selected={tab === id}
                onClick={() => setParams({ tab: id })}>
                {label}
              </button>
            ))}
          </div>
          {tab === "dictionary" && (
            <Dictionary onOpen={(cid) => setParams({ concept: cid })} />
          )}
          {tab === "paths" && (
            <Paths onOpen={(cid) => setParams({ concept: cid })} />
          )}
          {tab === "simulators" && <Simulators />}
          {tab === "progress" && <Progress />}
        </>
      )}
    </div>
  );
}

/* ------------------------------------------------------------- dictionary */

function Dictionary({ onOpen }: { onOpen: (id: string) => void }) {
  const [q, setQ] = useState("");
  const [category, setCategory] = useState("");
  const [categories, setCategories] = useState<{ id: string; name: string }[]>([]);
  const [concepts, setConcepts] = useState<ConceptSummary[]>([]);

  useEffect(() => {
    const t = setTimeout(() => {
      api.learnConcepts(q, category)
        .then((r) => { setCategories(r.categories); setConcepts(r.concepts); })
        .catch(() => undefined);
    }, 150);
    return () => clearTimeout(t);
  }, [q, category]);

  return (
    <>
      <div style={{ display: "flex", gap: 8, margin: "12px 0", flexWrap: "wrap" }}>
        <input placeholder="Search terms, concepts, strategies…" value={q}
          onChange={(e) => setQ(e.target.value)} style={{ minWidth: 260 }} />
        <button className={`ghost ${category === "" ? "active" : ""}`}
          onClick={() => setCategory("")}>All</button>
        {categories.map((c) => (
          <button key={c.id} className={`ghost ${category === c.id ? "active" : ""}`}
            onClick={() => setCategory(c.id)}>{c.name}</button>
        ))}
      </div>
      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(300px, 1fr))", gap: 12 }}>
        {concepts.map((c) => (
          <div key={c.id} className="card" style={{ cursor: "pointer" }}
            onClick={() => onOpen(c.id)}>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline" }}>
              <strong>{c.term}</strong>
              <span className="muted" style={{ fontSize: 12 }}>{c.category_name}</span>
            </div>
            <p className="muted" style={{ margin: "6px 0 0" }}>{c.beginner}</p>
            <p style={{ margin: "6px 0 0", fontSize: 12 }}>
              {c.viewed && <span className="badge FILLED">viewed</span>}{" "}
              {c.quiz_passed && <span className="badge FILLED">quiz ✓</span>}
              {c.has_quiz && !c.quiz_passed && <span className="badge PENDING">quiz</span>}
            </p>
          </div>
        ))}
      </div>
    </>
  );
}

/* ---------------------------------------------------------- concept detail */

function ConceptView({ id, onBack, onOpen }:
  { id: string; onBack: () => void; onOpen: (id: string) => void }) {
  const [concept, setConcept] = useState<ConceptDetail | null>(null);
  const [level, setLevel] = useState<(typeof LEVELS)[number]>("beginner");
  const [answers, setAnswers] = useState<number[]>([]);
  const [result, setResult] = useState<QuizResult | null>(null);
  const [aiAnswer, setAiAnswer] = useState("");
  const [error, setError] = useState("");

  useEffect(() => {
    setResult(null);
    setAiAnswer("");
    setAnswers([]);
    api.learnConcept(id).then(setConcept).catch((e: Error) => setError(e.message));
  }, [id]);

  if (!concept) return error ? <div className="error">{error}</div> : null;

  async function submitQuiz(e: FormEvent) {
    e.preventDefault();
    setError("");
    try {
      setResult(await api.submitQuiz(id, answers));
    } catch (err) {
      setError((err as Error).message);
    }
  }

  async function ask(mode: string) {
    setError("");
    setAiAnswer("…thinking…");
    try {
      const r = await api.askConcept(id, mode);
      setAiAnswer(r.answer);
    } catch (err) {
      setAiAnswer("");
      setError((err as Error).message);
    }
  }

  return (
    <div>
      <button className="ghost" onClick={onBack}>← Dictionary</button>
      <div className="card" style={{ marginTop: 10 }}>
        <div style={{ display: "flex", alignItems: "baseline", gap: 10 }}>
          <h2 style={{ marginBottom: 0 }}>{concept.term}</h2>
          <span className="muted">{concept.category_name}</span>
        </div>
        <div className="range-row" role="tablist" style={{ margin: "10px 0" }}>
          {LEVELS.map((l) => (
            <button key={l} className={`ghost ${level === l ? "active" : ""}`}
              role="tab" aria-selected={level === l} onClick={() => setLevel(l)}>
              {l[0].toUpperCase() + l.slice(1)}
            </button>
          ))}
        </div>
        <p style={{ fontSize: 15, lineHeight: 1.6 }}>{concept[level]}</p>
        {concept.related.length > 0 && (
          <p className="muted">
            Related:{" "}
            {concept.related.map((r) => (
              <button key={r} className="ghost" onClick={() => onOpen(r)}>{r}</button>
            ))}
          </p>
        )}
        <div style={{ display: "flex", gap: 8, flexWrap: "wrap", marginTop: 8 }}>
          <span className="muted">Ask the AI:</span>
          <button className="ghost" onClick={() => ask("simple")}>Explain simply</button>
          <button className="ghost" onClick={() => ask("examples")}>Give examples</button>
        </div>
        {aiAnswer && <p style={{ whiteSpace: "pre-wrap", marginTop: 8 }}>{aiAnswer}</p>}
        {error && <div className="error">{error}</div>}
      </div>

      {concept.quiz && concept.quiz.length > 0 && (
        <div className="card">
          <h3>Check your understanding {concept.quiz_passed && "✓ (passed)"}</h3>
          <form onSubmit={submitQuiz}>
            {concept.quiz.map((qz, qi) => (
              <div key={qi} style={{ marginBottom: 12 }}>
                <strong>{qz.question}</strong>
                {qz.options.map((opt, oi) => (
                  <label key={oi} style={{ display: "block", margin: "4px 0 0 12px" }}>
                    <input type="radio" name={`q${qi}`} required
                      checked={answers[qi] === oi}
                      onChange={() => {
                        const next = [...answers];
                        next[qi] = oi;
                        setAnswers(next);
                      }} />{" "}
                    {opt}
                    {result && oi === result.results[qi]?.answer && " ✅"}
                  </label>
                ))}
                {result && (
                  <p className="muted" style={{ marginLeft: 12 }}>
                    {result.results[qi].correct ? "Correct — " : "Not quite — "}
                    {result.results[qi].why}
                  </p>
                )}
              </div>
            ))}
            <button type="submit">Submit answers</button>
            {result && (
              <span style={{ marginLeft: 10 }}
                className={result.passed ? "gain" : "loss"}>
                Score: {result.score}% {result.passed ? "— passed!" : "— try again"}
              </span>
            )}
          </form>
        </div>
      )}
    </div>
  );
}

/* ------------------------------------------------------------------ paths */

function Paths({ onOpen }: { onOpen: (id: string) => void }) {
  const [paths, setPaths] = useState<PathView[]>([]);
  useEffect(() => {
    api.learnPaths().then(setPaths).catch(() => undefined);
  }, []);
  return (
    <>
      {paths.map((p) => (
        <div className="card" key={p.id}>
          <div style={{ display: "flex", alignItems: "baseline", gap: 10 }}>
            <h2 style={{ marginBottom: 0 }}>{p.name}</h2>
            <span className="muted">{p.done}/{p.total}</span>
            {p.completed && <span className="badge FILLED">COMPLETED</span>}
          </div>
          <p className="muted">{p.description}</p>
          <div style={{ display: "flex", gap: 6, flexWrap: "wrap" }}>
            {p.steps.map((s, i) => (
              <button key={s.concept_id} className="ghost"
                onClick={() => onOpen(s.concept_id)}
                title={s.has_quiz ? "Pass the quiz to complete this step" : "Read to complete"}>
                {s.complete ? "✅" : `${i + 1}.`} {s.term}
              </button>
            ))}
          </div>
        </div>
      ))}
    </>
  );
}

/* -------------------------------------------------------------- simulators */

function Simulators() {
  return (
    <>
      <CompoundSim />
      <DiversificationSim />
      <CrashSim />
    </>
  );
}

function CompoundSim() {
  const [principal, setPrincipal] = useState("1000");
  const [monthly, setMonthly] = useState("200");
  const [rate, setRate] = useState("7");
  const [years, setYears] = useState("30");
  const [out, setOut] = useState<Record<string, unknown> | null>(null);
  async function run() {
    setOut(await api.simulate("compound_growth", {
      principal, monthly, annual_rate_pct: rate, years,
    }).catch(() => null));
  }
  const points = (out?.points ?? []) as { year: number; value: number; contributed: number }[];
  const last = points[points.length - 1];
  const peak = last?.value ?? 1;
  return (
    <div className="card">
      <h2>Compound growth simulator</h2>
      <div style={{ display: "flex", gap: 8, flexWrap: "wrap", alignItems: "center" }}>
        <label>Start $<input value={principal} style={{ width: 80 }}
          onChange={(e) => setPrincipal(e.target.value)} /></label>
        <label>Monthly $<input value={monthly} style={{ width: 70 }}
          onChange={(e) => setMonthly(e.target.value)} /></label>
        <label>Rate %<input value={rate} style={{ width: 50 }}
          onChange={(e) => setRate(e.target.value)} /></label>
        <label>Years <input value={years} style={{ width: 50 }}
          onChange={(e) => setYears(e.target.value)} /></label>
        <button onClick={run}>Simulate</button>
      </div>
      {out && (
        <>
          <p>
            Final value <strong>${Number(out.final_value).toLocaleString()}</strong>{" "}
            — you contributed ${Number(out.total_contributed).toLocaleString()};{" "}
            <strong className="gain">{String(out.growth_share_pct)}%</strong> of the
            final value is growth.
          </p>
          <div style={{ display: "flex", alignItems: "flex-end", gap: 2, height: 120 }}>
            {points.map((p) => (
              <div key={p.year} title={`year ${p.year}: $${p.value.toLocaleString()}`}
                style={{ flex: 1, display: "flex", flexDirection: "column",
                         justifyContent: "flex-end", height: "100%" }}>
                <div style={{ height: `${(p.contributed / peak) * 100}%`,
                              background: "var(--muted, #888)", opacity: 0.5 }} />
                <div style={{ height: `${((p.value - p.contributed) / peak) * 100}%`,
                              background: "var(--gain, #22a06b)" }} />
              </div>
            ))}
          </div>
          <p className="muted">Grey = contributed · green = compounding. {String(out.assumption)}</p>
        </>
      )}
    </div>
  );
}

function DiversificationSim() {
  const [corr, setCorr] = useState("0.3");
  const [out, setOut] = useState<Record<string, unknown> | null>(null);
  async function run() {
    setOut(await api.simulate("diversification", { correlation: corr })
      .catch(() => null));
  }
  const points = (out?.points ?? []) as { holdings: number; portfolio_volatility_pct: number }[];
  return (
    <div className="card">
      <h2>Diversification simulator</h2>
      <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
        <label>Avg correlation between stocks{" "}
          <input value={corr} style={{ width: 60 }}
            onChange={(e) => setCorr(e.target.value)} /></label>
        <button onClick={run}>Simulate</button>
      </div>
      {out && (
        <>
          <div style={{ display: "flex", alignItems: "flex-end", gap: 3, height: 110, marginTop: 8 }}>
            {points.map((p) => (
              <div key={p.holdings}
                title={`${p.holdings} holdings → ${p.portfolio_volatility_pct}% volatility`}
                style={{ flex: 1, height: `${(p.portfolio_volatility_pct / 40) * 100}%`,
                         background: "var(--loss, #d9534f)", opacity: 0.8 }} />
            ))}
          </div>
          <p className="muted">Portfolio volatility from 1 → 30 holdings. {String(out.lesson)}</p>
        </>
      )}
    </div>
  );
}

function CrashSim() {
  const [scenario, setScenario] = useState("gfc_2008");
  const [value, setValue] = useState("10000");
  const [out, setOut] = useState<Record<string, unknown> | null>(null);
  const [error, setError] = useState("");
  async function run() {
    setError("");
    try {
      setOut(await api.simulate("market_crash",
        { scenario_id: scenario, starting_value: value }));
    } catch (e) {
      setOut(null);
      setError((e as Error).message);
    }
  }
  const points = (out?.points ?? []) as { ts: number; value: number }[];
  const peak = Math.max(1, ...points.map((p) => p.value));
  return (
    <div className="card">
      <h2>Market crash simulator</h2>
      <p className="muted">
        Replays a real historical index path against your number — genuine
        closes, not a model.
      </p>
      <div style={{ display: "flex", gap: 8, alignItems: "center", flexWrap: "wrap" }}>
        <select value={scenario} onChange={(e) => setScenario(e.target.value)}>
          <option value="dotcom_crash">Dot-com crash (1999-2002)</option>
          <option value="gfc_2008">2008 financial crisis</option>
          <option value="covid_crash">COVID crash (2020)</option>
          <option value="inflation_cycle">Inflation cycle (2021-23)</option>
        </select>
        <label>Invested $<input value={value} style={{ width: 90 }}
          onChange={(e) => setValue(e.target.value)} /></label>
        <button onClick={run}>Simulate</button>
      </div>
      {error && <div className="error">{error}</div>}
      {out && (
        <>
          <p>
            Worst point: <strong className="loss">
              ${Number(out.worst_value).toLocaleString()}</strong>{" "}
            ({String(out.max_drawdown_pct)}%) · end of period:{" "}
            <strong className={out.recovered ? "gain" : "loss"}>
              ${Number(out.end_value).toLocaleString()}</strong>{" "}
            ({out.recovered ? "recovered" : "still under water"})
          </p>
          <div style={{ display: "flex", alignItems: "flex-end", gap: 1, height: 110 }}>
            {points.filter((_, i) => i % Math.ceil(points.length / 160) === 0).map((p) => (
              <div key={p.ts} style={{ flex: 1, height: `${(p.value / peak) * 100}%`,
                background: "var(--accent, #4a7dff)", opacity: 0.85 }} />
            ))}
          </div>
          <p className="muted">{String(out.scenario)} · {String(out.period)} ·
            {" "}{String(out.benchmark)} · {String(out.source)}</p>
        </>
      )}
    </div>
  );
}

/* ---------------------------------------------------------------- progress */

function Progress() {
  const [progress, setProgress] = useState<LearnProgress | null>(null);
  useEffect(() => {
    api.learnProgress().then(setProgress).catch(() => undefined);
  }, []);
  if (!progress) return null;
  return (
    <>
      <div className="card">
        <h2>Knowledge tracking</h2>
        <p>
          <strong>{progress.concepts_viewed}</strong> of {progress.concepts_total}{" "}
          concepts studied · <strong>{progress.quizzes_passed}</strong> quizzes passed
          {progress.paths_completed.length > 0 &&
            <> · paths completed: {progress.paths_completed.join(", ")}</>}
        </p>
        {Object.entries(progress.categories).map(([id, c]) => (
          <div key={id} style={{ margin: "6px 0" }}>
            <span style={{ display: "inline-block", width: 200 }}>{c.name}</span>
            <span className="muted">{c.viewed}/{c.total}</span>
            <div style={{ background: "var(--border, #333)", height: 6, borderRadius: 3,
                          width: 240, display: "inline-block", marginLeft: 10 }}>
              <div style={{ width: `${(c.viewed / Math.max(1, c.total)) * 100}%`,
                            height: "100%", borderRadius: 3,
                            background: "var(--gain, #22a06b)" }} />
            </div>
          </div>
        ))}
      </div>
      <div className="card">
        <h2>Learning achievements</h2>
        {progress.achievements.map((a) => (
          <p key={a.id}>
            {a.earned ? "🏆" : "🔒"} <strong>{a.name}</strong>{" "}
            <span className="muted">— {a.description}</span>
          </p>
        ))}
      </div>
    </>
  );
}
