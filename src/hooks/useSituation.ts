/**
 * "Your situation": optional answers that change how results are presented (never the engine's numbers).
 * Stored only in this browser. No salary, employer or bank data is ever asked for.
 */
import { useSyncExternalStore } from 'react';
import type { Objective } from '../api/schema';

export type Role = 'owner' | 'tenant' | 'landlord' | 'leaseholder' | 'manager' | 'unknown';
export type Horizon = 'lt2' | '2to5' | '5to10' | '10plus' | 'unknown';
export type Priority = 'spend_least' | 'cut_most' | 'best_value' | 'unknown';
export type Change = 'more_people' | 'fewer_people' | 'moving' | 'none' | 'unknown';

export interface Situation {
  role: Role;
  horizon: Horizon;
  /** Upfront spend the user is comfortable with now, in £. null = no limit or not sure. */
  budgetGbp: number | null;
  budgetAnswered: boolean;
  priority: Priority;
  change: Change;
  /** The user has finished or skipped the intake card. */
  done: boolean;
}

export const DEFAULT_SITUATION: Situation = {
  role: 'unknown', horizon: 'unknown', budgetGbp: null, budgetAnswered: false, priority: 'unknown', change: 'unknown', done: false,
};

export const ROLE_TEXT: Record<Role, string> = {
  owner: 'I own and live in it',
  tenant: 'I rent it',
  landlord: 'I rent it out',
  leaseholder: 'I own a flat in a shared building',
  manager: 'I manage it for others',
  unknown: 'Not sure',
};
export const ROLE_SHORT: Record<Role, string> = {
  owner: 'Homeowner', tenant: 'Tenant', landlord: 'Landlord', leaseholder: 'Flat owner', manager: 'Manager', unknown: 'Anyone',
};
export const HORIZON_TEXT: Record<Horizon, string> = {
  lt2: 'Under 2 years', '2to5': '2–5 years', '5to10': '5–10 years', '10plus': '10+ years', unknown: 'Not sure',
};
export const PRIORITY_TEXT: Record<Priority, string> = {
  spend_least: 'Spend as little as possible', cut_most: 'Cut the most carbon', best_value: 'Best value for money', unknown: 'Not sure',
};
export const CHANGE_TEXT: Record<Change, string> = {
  more_people: 'More people at home', fewer_people: 'Fewer people at home', moving: 'I may move soon', none: 'No big changes', unknown: 'Not sure',
};
export const BUDGET_CHOICES: { label: string; value: number | null }[] = [
  { label: '£0 — nothing now', value: 0 },
  { label: 'Up to £1,000', value: 1000 },
  { label: 'Up to £5,000', value: 5000 },
  { label: 'Up to £15,000', value: 15000 },
  { label: 'No fixed limit', value: null },
];

/** The user's priority names one of the engine's three objectives; the engine still picks the package. */
export const PRIORITY_OBJECTIVE: Record<Priority, Objective | null> = {
  spend_least: 'lowest_cost_meeting_threshold',
  cut_most: 'largest_carbon_saving',
  best_value: 'best_carbon_per_pound',
  unknown: null,
};

const KEY = 'ghs.situation.v1';

function load(): Situation {
  try {
    const raw = window.localStorage.getItem(KEY);
    if (!raw) return DEFAULT_SITUATION;
    return { ...DEFAULT_SITUATION, ...(JSON.parse(raw) as Partial<Situation>) };
  } catch {
    return DEFAULT_SITUATION;
  }
}

let current: Situation = typeof window !== 'undefined' ? load() : DEFAULT_SITUATION;
const listeners = new Set<() => void>();

export function setSituation(next: Situation): void {
  current = next;
  try {
    window.localStorage.setItem(KEY, JSON.stringify(next));
  } catch {
    /* storage unavailable: answers last for this page only */
  }
  listeners.forEach((l) => l());
}

/** Test helper: reload from storage. */
export function resetSituationForTests(): void {
  current = load();
  listeners.forEach((l) => l());
}

export function useSituation(): [Situation, (patch: Partial<Situation>) => void] {
  const s = useSyncExternalStore(
    (l) => { listeners.add(l); return () => listeners.delete(l); },
    () => current,
    () => current,
  );
  return [s, (patch) => setSituation({ ...current, ...patch })];
}

export function situationSummary(s: Situation): string {
  const parts: string[] = [];
  if (s.role !== 'unknown') parts.push(ROLE_SHORT[s.role]);
  if (s.horizon !== 'unknown') parts.push(`staying ${HORIZON_TEXT[s.horizon].toLowerCase()}`);
  if (s.budgetAnswered) parts.push(s.budgetGbp === null ? 'no fixed budget' : `budget £${s.budgetGbp.toLocaleString('en-GB')}`);
  if (s.priority !== 'unknown') parts.push(PRIORITY_TEXT[s.priority].toLowerCase());
  return parts.length ? parts.join(' · ') : 'Not set — answers are optional';
}
