/** Optional synchronized chart ranges (PRD §13): when sync is on, changing
 * the range on any chart updates every other chart. */

import { useEffect, useState } from "react";

const RANGE_KEY = "aiptp-range";
const SYNC_KEY = "aiptp-range-sync";
const listeners = new Set<(range: string) => void>();

export function isSyncEnabled(): boolean {
  return localStorage.getItem(SYNC_KEY) === "1";
}

export function setSyncEnabled(on: boolean): void {
  localStorage.setItem(SYNC_KEY, on ? "1" : "0");
}

export function getSharedRange(fallback: string): string {
  return localStorage.getItem(RANGE_KEY) ?? fallback;
}

export function publishRange(range: string): void {
  localStorage.setItem(RANGE_KEY, range);
  if (isSyncEnabled()) listeners.forEach((fn) => fn(range));
}

/** Range state that participates in global sync when enabled. */
export function useChartRange(defaultRange: string): [string, (r: string) => void, boolean, (on: boolean) => void] {
  const [range, setRangeState] = useState(
    isSyncEnabled() ? getSharedRange(defaultRange) : defaultRange,
  );
  const [sync, setSyncState] = useState(isSyncEnabled());

  useEffect(() => {
    const fn = (r: string) => setRangeState(r);
    listeners.add(fn);
    return () => {
      listeners.delete(fn);
    };
  }, []);

  const setRange = (r: string) => {
    setRangeState(r);
    publishRange(r);
  };
  const setSync = (on: boolean) => {
    setSyncEnabled(on);
    setSyncState(on);
    if (on) {
      const shared = getSharedRange(range);
      setRangeState(shared);
    }
  };
  return [range, setRange, sync, setSync];
}
