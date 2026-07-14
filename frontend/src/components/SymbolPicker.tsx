import { useEffect, useRef, useState } from "react";
import { api, SymbolMatch } from "../api";

/** Symbol input with company-name autocomplete: type "Microsoft" and pick
 * "Microsoft Corporation — MSFT"; brands resolve to their parent (typing
 * "Google" suggests Alphabet). Picking from the list is also how
 * international listings get their correct suffix (Samsung → 005930.KS). */
export default function SymbolPicker({ value, onChange, width = 160, id }: {
  value: string;
  onChange: (symbol: string) => void;
  width?: number;
  id?: string;
}) {
  const [text, setText] = useState(value);
  const [results, setResults] = useState<SymbolMatch[]>([]);
  const [open, setOpen] = useState(false);
  const timer = useRef<number>();
  const box = useRef<HTMLDivElement>(null);

  useEffect(() => setText(value), [value]);

  useEffect(() => {
    const close = (e: MouseEvent) => {
      if (box.current && !box.current.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener("mousedown", close);
    return () => document.removeEventListener("mousedown", close);
  }, []);

  function edit(next: string) {
    setText(next);
    onChange(next.toUpperCase().trim());
    window.clearTimeout(timer.current);
    if (next.trim().length < 1) {
      setResults([]);
      return;
    }
    timer.current = window.setTimeout(() => {
      api.search(next)
        .then((r) => {
          setResults(r.slice(0, 8));
          setOpen(true);
        })
        .catch(() => setResults([]));
    }, 250);
  }

  function pick(m: SymbolMatch) {
    setText(m.symbol);
    onChange(m.symbol);
    setOpen(false);
    setResults([]);
  }

  return (
    <div ref={box} style={{ position: "relative", display: "inline-block" }}>
      <input id={id} value={text} required style={{ width }}
        placeholder="Symbol or company name"
        onChange={(e) => edit(e.target.value)}
        onFocus={() => results.length > 0 && setOpen(true)}
        autoComplete="off" />
      {open && results.length > 0 && (
        <div className="search-results" style={{ minWidth: 280 }}>
          {results.map((m) => (
            <div key={m.symbol} onClick={() => pick(m)} style={{ cursor: "pointer" }}>
              {m.name ? `${m.name} — ` : ""}<strong>{m.symbol}</strong>{" "}
              <span className="muted">{m.exchange}</span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
