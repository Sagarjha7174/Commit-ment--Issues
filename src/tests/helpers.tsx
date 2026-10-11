/** Test helpers: serve public/fixtures (real engine output) through a stubbed fetch, and render the app. */
import { readFileSync, existsSync } from 'node:fs';
import { resolve } from 'node:path';
import type { ReactNode } from 'react';
import { render } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { MemoryRouter } from 'react-router-dom';
import { vi } from 'vitest';
import { TransportContext } from '../api/transportContext';
import { createFixtureTransport, type Transport } from '../api/transport';
import { AppRoutes } from '../app/App';
import { EvidenceProvider } from '../components/common/EvidenceDrawer';
import type { ScenarioResult } from '../api/schema';

export const FIXTURES = resolve(__dirname, '../../public/fixtures');
export const HOME_A = 'U100050529765';
export const HOME_B = 'A012dcfda4e502be0';
export const HOME_C = 'U100050565716';

export function readFixture(rel: string): unknown {
  return JSON.parse(readFileSync(resolve(FIXTURES, rel), 'utf8'));
}

/** Stub fetch so that /fixtures/<path> is read from disk. Returns the mock for call assertions. */
export function stubFixtureFetch() {
  const fn = vi.fn(async (input: RequestInfo | URL) => {
    const url = String(input);
    const m = url.match(/fixtures\/(.+)$/);
    if (!m) return new Response('not found', { status: 404 });
    const file = resolve(FIXTURES, decodeURIComponent(m[1]));
    if (!existsSync(file)) return new Response('not found', { status: 404 });
    return new Response(readFileSync(file, 'utf8'), { status: 200, headers: { 'Content-Type': 'application/json' } });
  });
  vi.stubGlobal('fetch', fn);
  return fn;
}

/** A complete engine result from the snapshot (core file + shared packages/sensitivity). */
export function snapshotResult(homeId: string, variant = 'default', measuresKey = 'engine-default'): ScenarioResult {
  const manifest = readFixture('manifest.json') as { homes: Record<string, { variants: Record<string, { shared: string; scenarios: Record<string, string> }> }> };
  const v = manifest.homes[homeId].variants[variant];
  return { ...(readFixture(v.scenarios[measuresKey]) as object), ...(readFixture(v.shared) as object) } as ScenarioResult;
}

export function makeClient() {
  return new QueryClient({ defaultOptions: { queries: { retry: false, refetchOnWindowFocus: false } } });
}

export function Providers({ transport, children }: { transport: Transport; children: ReactNode }) {
  return (
    <QueryClientProvider client={makeClient()}>
      <TransportContext.Provider value={transport}>
        <EvidenceProvider>{children}</EvidenceProvider>
      </TransportContext.Provider>
    </QueryClientProvider>
  );
}

export function renderApp(path: string, transport: Transport = createFixtureTransport('/fixtures')) {
  return render(
    <Providers transport={transport}>
      <MemoryRouter initialEntries={[path]}>
        <AppRoutes />
      </MemoryRouter>
    </Providers>,
  );
}

export interface Deferred<T> { promise: Promise<T>; resolve(v: T): void; reject(e: unknown): void }
export function deferred<T>(): Deferred<T> {
  let resolve!: (v: T) => void;
  let reject!: (e: unknown) => void;
  const promise = new Promise<T>((res, rej) => { resolve = res; reject = rej; });
  return { promise, resolve, reject };
}
