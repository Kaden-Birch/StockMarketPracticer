import { useCallback, useEffect, useState } from "react";
import { api, ModelView } from "../api";

const FIT_LABEL: Record<string, { text: string; cls: string }> = {
  fits: { text: "Fits your hardware", cls: "FILLED" },
  marginal: { text: "Marginal fit", cls: "PENDING" },
  too_large: { text: "Too large", cls: "REJECTED" },
  unknown: { text: "Fit unknown", cls: "" },
};

export default function ModelsPage() {
  const [models, setModels] = useState<ModelView[]>([]);
  const [defaultModel, setDefaultModel] = useState("");
  const [disclaimer, setDisclaimer] = useState("");
  const [hardware, setHardware] = useState<Awaited<ReturnType<typeof api.aiHardware>> | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [bench, setBench] = useState<Record<string, string>>({});
  const [error, setError] = useState("");

  const refresh = useCallback(() => {
    api.aiModels().then((res) => {
      setModels(res.models);
      setDefaultModel(res.default_model);
      setDisclaimer(res.disclaimer);
    }).catch((e: Error) => setError(e.message));
    api.aiHardware().then(setHardware).catch(() => undefined);
  }, []);
  useEffect(refresh, [refresh]);

  // While a download is running, poll so the progress bar moves.
  const downloading = models.some((m) => m.download) || busy !== null;
  useEffect(() => {
    if (!downloading) return;
    const t = window.setInterval(() => {
      api.aiModels().then((res) => setModels(res.models)).catch(() => undefined);
    }, 1500);
    return () => window.clearInterval(t);
  }, [downloading]);

  async function act(modelId: string, fn: () => Promise<unknown>) {
    setBusy(modelId);
    setError("");
    try {
      await fn();
      refresh();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(null);
    }
  }

  return (
    <div>
      <h1>AI Models</h1>
      {error && <div className="error">{error}</div>}

      {hardware && (
        <div className="cards-row">
          <div className="card stat">
            <div className="label">CPU cores</div>
            <div className="value">{hardware.cpu_count}</div>
          </div>
          <div className="card stat">
            <div className="label">System RAM</div>
            <div className="value">{hardware.ram_gb !== null ? `${hardware.ram_gb} GB` : "—"}</div>
          </div>
          <div className="card stat">
            <div className="label">GPU</div>
            <div className="value" style={{ fontSize: 16 }}>
              {hardware.gpus.length > 0
                ? hardware.gpus.map((g) => `${g.name} (${g.vram})`).join(", ")
                : "None detected — CPU inference"}
            </div>
          </div>
          <div className="card stat">
            <div className="label">Inference runtime</div>
            <div className="value" style={{ fontSize: 16 }}>
              {hardware.runtime_available ? "llama.cpp ready" : "not installed"}
            </div>
            {!hardware.runtime_available && (
              <div className="sub">pip install "aiptp[ai]" to enable local models</div>
            )}
          </div>
        </div>
      )}

      {models.map((m) => {
        const fit = FIT_LABEL[m.hardware_fit] ?? FIT_LABEL.unknown;
        return (
          <div className="card" key={m.id}>
            <div style={{ display: "flex", gap: 10, alignItems: "center", flexWrap: "wrap" }}>
              <h2 style={{ margin: 0 }}>{m.name}</h2>
              <span className={`badge ${fit.cls}`}>{fit.text}</span>
              {m.loaded && <span className="badge FILLED">LOADED</span>}
              {defaultModel === m.id && <span className="badge PENDING">DEFAULT</span>}
              <span style={{ flex: 1 }} />
              {!m.installed ? (
                <button disabled={busy === m.id} onClick={() => act(m.id, () => api.aiInstall(m.id))}>
                  {busy === m.id ? "Downloading…" : `Install (${m.disk_gb} GB)`}
                </button>
              ) : (
                <>
                  {!m.loaded && (
                    <button className="ghost" disabled={busy === m.id}
                      onClick={() => act(m.id, () => api.aiLoad(m.id))}>
                      {busy === m.id ? "Loading…" : "Load"}
                    </button>
                  )}
                  <button className="ghost" disabled={busy === m.id}
                    onClick={() =>
                      act(m.id, async () => {
                        const b = await api.aiBenchmark(m.id);
                        setBench({ ...bench, [m.id]: `${b.tokens_per_second ?? "?"} tok/s (${b.completion_tokens} tokens in ${b.elapsed_seconds}s)` });
                      })}>
                    {busy === m.id ? "Benchmarking…" : "Benchmark"}
                  </button>
                  <button className="ghost" onClick={() => act(m.id, () => api.aiSetDefault(m.id))}>
                    Set default
                  </button>
                  <button className="ghost" disabled={busy === m.id}
                    onClick={() => act(m.id, () => api.aiRemove(m.id))}>
                    Remove
                  </button>
                </>
              )}
            </div>
            {m.download && m.download.total > 0 && (
              <div style={{ marginTop: 10 }}>
                <div style={{ background: "var(--border, #333)", height: 10,
                              borderRadius: 5, overflow: "hidden" }}>
                  <div style={{ width: `${Math.min(100, (m.download.done / m.download.total) * 100)}%`,
                                height: "100%", background: "var(--gain, #22a06b)",
                                transition: "width .8s linear" }} />
                </div>
                <div className="muted" style={{ marginTop: 4 }}>
                  {((m.download.done / m.download.total) * 100).toFixed(1)}% ·{" "}
                  {(m.download.done / 1e9).toFixed(2)} / {(m.download.total / 1e9).toFixed(2)} GB
                  {m.download.speed_bps ? <> · {(m.download.speed_bps / 1e6).toFixed(1)} MB/s
                    {" · ~"}{Math.max(1, Math.round((m.download.total - m.download.done) /
                      m.download.speed_bps))}s left</> : null}
                </div>
              </div>
            )}
            <table style={{ marginTop: 10 }}>
              <tbody>
                <tr>
                  <th>Parameters</th><td>{m.parameters}</td>
                  <th>Quantization</th><td>{m.quantization}</td>
                  <th>Disk</th><td>{m.disk_gb} GB</td>
                </tr>
                <tr>
                  <th>Min RAM</th><td>{m.min_ram_gb} GB</td>
                  <th>Recommended RAM</th><td>{m.recommended_ram_gb} GB</td>
                  <th>GPU VRAM (full offload)</th>
                  <td>{m.gpu_vram_gb > 0 ? `${m.gpu_vram_gb} GB` : "runs well on CPU"}</td>
                </tr>
                <tr>
                  <th>Estimated speed</th><td>{m.est_speed}</td>
                  <th>Features</th><td colSpan={3}>{m.features.join(", ")}</td>
                </tr>
              </tbody>
            </table>
            {bench[m.id] && <div className="muted" style={{ marginTop: 6 }}>Benchmark: {bench[m.id]}</div>}
          </div>
        );
      })}
      {disclaimer && <p className="muted">{disclaimer} Models run entirely on your hardware.</p>}
    </div>
  );
}
