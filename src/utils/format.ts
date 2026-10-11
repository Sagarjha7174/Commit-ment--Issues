/**
 * Display formatting only. Nothing here derives a new quantity from engine numbers:
 * values are rounded for display, and missing values are shown as their status, never as 0.
 */
import type { ValueStatus } from '../api/schema';

const nf0 = new Intl.NumberFormat('en-GB', { maximumFractionDigits: 0 });
const nf1 = new Intl.NumberFormat('en-GB', { maximumFractionDigits: 1, minimumFractionDigits: 1 });
const gbp = new Intl.NumberFormat('en-GB', { style: 'currency', currency: 'GBP', maximumFractionDigits: 0 });

export type Missing = ValueStatus | 'unknown' | 'not_applicable' | string;

const MISSING_TEXT: Record<string, string> = {
  unavailable: 'Unavailable',
  not_estimated: 'Not estimated',
  blocked: 'Blocked (infeasible)',
  unknown: 'Unknown',
  not_applicable: 'Not applicable',
};

export function missingText(status?: Missing | null): string {
  return (status && MISSING_TEXT[status]) || 'Unavailable';
}

export function isNum(v: unknown): v is number {
  return typeof v === 'number' && Number.isFinite(v);
}

/** Number with a minus sign that is a real minus (−), so negative savings are unmistakable. */
export function fmtNumber(v: number | null | undefined, digits = 0, status?: Missing | null): string {
  if (!isNum(v)) return missingText(status);
  const s = (digits === 1 ? nf1 : nf0).format(Math.abs(v));
  return v < 0 && s !== '0' ? `−${s}` : s;
}

export function fmtKwh(v: number | null | undefined, status?: Missing | null): string {
  return isNum(v) ? `${fmtNumber(v)} kWh/yr` : missingText(status);
}

export function fmtKg(v: number | null | undefined, status?: Missing | null): string {
  return isNum(v) ? `${fmtNumber(v)} kg CO₂e/yr` : missingText(status);
}

export function fmtTonnes(v: number | null | undefined, status?: Missing | null): string {
  return isNum(v) ? `${fmtNumber(v, 1)} t CO₂e/yr` : missingText(status);
}

export function fmtGbp(v: number | null | undefined, status?: Missing | null): string {
  if (!isNum(v)) return missingText(status);
  const s = gbp.format(Math.abs(v));
  return v < 0 ? `−${s}` : s;
}

export function fmtPct(v: number | null | undefined, digits = 0, status?: Missing | null): string {
  return isNum(v) ? `${fmtNumber(v, digits)}%` : missingText(status);
}

/** Signed form for engine "saving" values (saving = before − after; negative = use rises). */
export function fmtSigned(v: number | null | undefined, unit: string, status?: Missing | null): string {
  if (!isNum(v)) return missingText(status);
  const s = nf0.format(Math.abs(v));
  if (s === '0') return `0 ${unit}`;
  return `${v > 0 ? '+' : '−'}${s} ${unit}`;
}

export type Direction = 'reduction' | 'increase' | 'none' | 'unknown';

/** Direction of an engine saving value: positive = reduction, negative = increase. */
export function savingDirection(v: number | null | undefined): Direction {
  if (!isNum(v)) return 'unknown';
  if (Math.abs(v) < 0.5) return 'none';
  return v > 0 ? 'reduction' : 'increase';
}

export const DIRECTION_TEXT: Record<Direction, string> = {
  reduction: 'reduction',
  increase: 'increase',
  none: 'no change',
  unknown: 'not available',
};

export function fmtDate(iso: string | null | undefined): string {
  if (!iso) return 'Unknown date';
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return d.toLocaleString('en-GB', { day: 'numeric', month: 'short', year: 'numeric', hour: '2-digit', minute: '2-digit', timeZone: 'UTC' }) + ' UTC';
}

export function shortId(id: string | null | undefined, n = 8): string {
  return id ? id.slice(0, n) : '—';
}

export function humanise(code: string | null | undefined): string {
  if (!code) return '';
  const s = code.replace(/_/g, ' ').trim();
  return s.charAt(0).toUpperCase() + s.slice(1);
}

/** Bar width in [0, 100] for a value against the largest value shown in the same chart (presentational geometry). */
export function barPct(v: number | null | undefined, max: number): number {
  if (!isNum(v) || !isNum(max) || max <= 0) return 0;
  return Math.max(0, Math.min(100, (Math.abs(v) / max) * 100));
}
