import '@testing-library/jest-dom/vitest';
import { afterEach, vi } from 'vitest';
import { cleanup } from '@testing-library/react';

// jsdom lacks these browser APIs used by Recharts' ResponsiveContainer and the drawer.
class RO { observe() {} unobserve() {} disconnect() {} }
(globalThis as unknown as { ResizeObserver: unknown }).ResizeObserver ??= RO;
if (!window.matchMedia) {
  window.matchMedia = (q: string) => ({ matches: false, media: q, onchange: null, addListener() {}, removeListener() {}, addEventListener() {}, removeEventListener() {}, dispatchEvent: () => false }) as MediaQueryList;
}

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  try { window.localStorage.clear(); } catch { /* ignore */ }
});
