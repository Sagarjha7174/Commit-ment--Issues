/**
 * Where data comes from. Two modes, one contract:
 *  - "fixtures": the offline snapshot in public/fixtures/, produced by the real engine via
 *    scripts/generate_fixtures.py. Default until the backend routes exist.
 *  - "live": the FastAPI routes in docs/API_CONTRACT.md (/api/*) and the LLM routes (/llm/*).
 * The mode can be switched at runtime (e.g. when the live backend is unreachable during a demo).
 */
import { useSyncExternalStore } from 'react';

export type DataMode = 'fixtures' | 'live';

const ENV_MODE: DataMode = import.meta.env.VITE_DATA_MODE === 'live' ? 'live' : 'fixtures';
/** Base URL of the FastAPI app; empty = same origin (the Vite dev server proxies /api and /llm). */
export const API_BASE = String(import.meta.env.VITE_API_BASE_URL ?? '').replace(/\/+$/, '');
export const FIXTURE_BASE = `${import.meta.env.BASE_URL ?? '/'}fixtures`;
export const REQUEST_TIMEOUT_MS = 15000;
export const LLM_TIMEOUT_MS = 25000;

const STORAGE_KEY = 'ghs.dataMode';

function readStored(): DataMode | null {
  try {
    const v = window.localStorage.getItem(STORAGE_KEY);
    return v === 'live' || v === 'fixtures' ? v : null;
  } catch {
    return null;
  }
}

let mode: DataMode = (typeof window !== 'undefined' && readStored()) || ENV_MODE;
const listeners = new Set<() => void>();

export function getDataMode(): DataMode {
  return mode;
}

export function setDataMode(next: DataMode): void {
  if (next === mode) return;
  mode = next;
  try {
    window.localStorage.setItem(STORAGE_KEY, next);
  } catch {
    /* storage unavailable: the choice lasts for this page only */
  }
  listeners.forEach((l) => l());
}

export function envDataMode(): DataMode {
  return ENV_MODE;
}

function subscribe(l: () => void) {
  listeners.add(l);
  return () => listeners.delete(l);
}

export function useDataMode(): DataMode {
  return useSyncExternalStore(subscribe, getDataMode, getDataMode);
}
