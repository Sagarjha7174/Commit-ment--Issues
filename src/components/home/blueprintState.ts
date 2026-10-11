import type { FeasibilityItem } from '../../api/schema';

export type CalloutState = 'selected' | 'pending-add' | 'pending-remove' | 'available' | 'verify' | 'blocked';

export function calloutState(m: string, f: FeasibilityItem | undefined, selected: ReadonlySet<string>, applied: ReadonlySet<string>): CalloutState {
  if (f?.state === 'infeasible') return 'blocked';
  const s = selected.has(m);
  const a = applied.has(m);
  if (s && !a) return 'pending-add';
  if (!s && a) return 'pending-remove';
  if (s) return 'selected';
  return f?.state === 'needs_verification' ? 'verify' : 'available';
}
