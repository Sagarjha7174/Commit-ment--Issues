/** Saved plans (concept doc pattern 38): kept in this browser only; reopening re-runs the engine. */
import { useSyncExternalStore } from 'react';
import type { Draft } from './useScenarioLab';

export interface SavedPlan {
  id: string;
  name: string;
  homeId: string;
  draft: Draft;
  scenarioId: string;
  measures: string[];
  savedAt: string;
}

const KEY = 'ghs.savedPlans.v1';

function load(): SavedPlan[] {
  try {
    const raw = window.localStorage.getItem(KEY);
    return raw ? (JSON.parse(raw) as SavedPlan[]) : [];
  } catch {
    return [];
  }
}

let plans: SavedPlan[] = typeof window !== 'undefined' ? load() : [];
const listeners = new Set<() => void>();

function write(next: SavedPlan[]) {
  plans = next;
  try {
    window.localStorage.setItem(KEY, JSON.stringify(next));
  } catch {
    /* storage unavailable: plans last for this page only */
  }
  listeners.forEach((l) => l());
}

export function resetSavedPlansForTests(): void {
  plans = load();
  listeners.forEach((l) => l());
}

export function useSavedPlans(homeId: string) {
  const all = useSyncExternalStore(
    (l) => { listeners.add(l); return () => listeners.delete(l); },
    () => plans,
    () => plans,
  );
  return {
    plans: all.filter((p) => p.homeId === homeId),
    save: (p: Omit<SavedPlan, 'id' | 'savedAt'>) =>
      write([{ ...p, id: `${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 6)}`, savedAt: new Date().toISOString() }, ...plans].slice(0, 30)),
    remove: (id: string) => write(plans.filter((p) => p.id !== id)),
  };
}
