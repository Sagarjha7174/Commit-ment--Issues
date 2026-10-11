import type { Evidence } from '../api/schema';

export interface ScopRange { low: number; mid: number; high: number }

/** The heat-pump SCOP range the engine uses (field evidence, D24), from /api/evidence; null until it has loaded. */
export function scopRange(ev?: Evidence | null): ScopRange | null {
  const s = ev?.catalogue?.global?.heat_pump_scop as Record<string, unknown> | undefined;
  const n = (k: string) => (typeof s?.[k] === 'number' ? (s[k] as number) : null);
  const low = n('low'), mid = n('mid'), high = n('high');
  return low != null && mid != null && high != null ? { low, mid, high } : null;
}
