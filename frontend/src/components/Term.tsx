import { ReactNode, useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { api, ConceptSummary } from "../api";

/** Universal glossary (roadmap 10.10): wrap any investing term to make it
 * clickable — a popover shows the beginner explanation with a link to the
 * full three-level entry. Uses the cached dictionary list, so popovers are
 * instant and don't farm view-XP. */

let cache: Promise<Map<string, ConceptSummary>> | null = null;

function dictionary(): Promise<Map<string, ConceptSummary>> {
  cache = cache ?? api
    .learnConcepts()
    .then((r) => new Map(r.concepts.map((c) => [c.id, c])))
    .catch(() => {
      cache = null; // retry next time (e.g. knowledge module disabled)
      return new Map<string, ConceptSummary>();
    });
  return cache;
}

export default function Term({ id, children }:
  { id: string; children: ReactNode }) {
  const [open, setOpen] = useState(false);
  const [concept, setConcept] = useState<ConceptSummary | null>(null);
  const [alignRight, setAlignRight] = useState(false);
  const ref = useRef<HTMLSpanElement>(null);

  useEffect(() => {
    if (!open) return;
    dictionary().then((d) => setConcept(d.get(id) ?? null));
    const close = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener("mousedown", close);
    return () => document.removeEventListener("mousedown", close);
  }, [open, id]);

  return (
    <span ref={ref} style={{ position: "relative", display: "inline-block" }}>
      <button type="button" className="term"
        onClick={() => {
          const rect = ref.current?.getBoundingClientRect();
          setAlignRight(!!rect && rect.left + 300 > window.innerWidth - 24);
          setOpen(!open);
        }}
        aria-expanded={open}
        style={{ background: "none", border: "none", padding: 0, margin: 0,
                 font: "inherit", color: "inherit", cursor: "help",
                 borderBottom: "1px dotted currentColor" }}>
        {children}
        <sup style={{ opacity: 0.6, fontSize: "0.7em" }}> ?</sup>
      </button>
      {open && (
        <span role="tooltip" style={{
          position: "absolute", zIndex: 40, top: "125%",
          left: alignRight ? "auto" : 0, right: alignRight ? 0 : "auto",
          width: 300, padding: 12, borderRadius: 8,
          background: "var(--card-bg, var(--bg, #1c1e26))",
          border: "1px solid var(--border, #444)",
          boxShadow: "0 6px 24px rgba(0,0,0,.35)",
          display: "block", textAlign: "left", fontWeight: "normal",
          fontSize: 13, lineHeight: 1.45, whiteSpace: "normal",
        }}>
          {concept ? (
            <>
              <strong>{concept.term}</strong>
              <span style={{ display: "block", margin: "6px 0" }}>
                {concept.beginner}
              </span>
              <Link to={`/learn?concept=${concept.id}`}
                onClick={() => setOpen(false)}>
                Full explanation →
              </Link>
            </>
          ) : (
            <span className="muted">Loading…</span>
          )}
        </span>
      )}
    </span>
  );
}
