import { useEffect, useState } from "react";
import { api, ModuleView } from "../api";

/** Fetches the active-module set once so the UI can assemble itself from
 * enabled modules (roadmap 6.11.12). Falls back to "everything running" if
 * the endpoint is unavailable, so the app never hides itself on a fetch error. */
export function useModules() {
  const [modules, setModules] = useState<ModuleView[] | null>(null);

  useEffect(() => {
    api.modules().then((r) => setModules(r.modules)).catch(() => setModules([]));
  }, []);

  const running = (id: string): boolean => {
    if (modules === null || modules.length === 0) return true; // unknown → show
    const m = modules.find((x) => x.id === id);
    return m ? m.state === "RUNNING" : true;
  };

  return { modules, running };
}
