/** Live Scenario Lab state: stale responses, failures and atomic swaps. */
import type { ReactNode } from 'react';
import { act, renderHook, waitFor } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { TransportContext } from '../api/transportContext';
import { ApiError } from '../api/errors';
import type { Transport } from '../api/transport';
import type { ScenarioRequest, ScenarioResult } from '../api/schema';
import { useScenarioLab } from '../hooks/useScenarioLab';
import { deferred, HOME_A, snapshotResult, type Deferred } from './helpers';

/** A transport whose scenario() calls are resolved by the test, in any order. */
function controllable() {
  const calls: { req: ScenarioRequest; d: Deferred<ScenarioResult> }[] = [];
  const t = {
    kind: 'live',
    scenario: (req: ScenarioRequest) => {
      const d = deferred<ScenarioResult>();
      calls.push({ req, d });
      return d.promise;
    },
  } as unknown as Transport;
  return { t, calls };
}

const wrap = (t: Transport) => ({ children }: { children: ReactNode }) => <TransportContext.Provider value={t}>{children}</TransportContext.Provider>;

const BASE = snapshotResult(HOME_A);
const HP_ONLY = snapshotResult(HOME_A, 'default', 'heat_pump');
const GLZ_HP = snapshotResult(HOME_A, 'default', 'double_glazing+heat_pump');
const GLZ_ONLY = snapshotResult(HOME_A, 'default', 'double_glazing');

async function loaded(t: Transport, calls: ReturnType<typeof controllable>['calls']) {
  const h = renderHook(() => useScenarioLab(HOME_A, { debounceMs: 0, transport: t }), { wrapper: wrap(t) });
  await waitFor(() => expect(calls).toHaveLength(1));
  expect(calls[0].req.measures).toBeNull();
  await act(async () => calls[0].d.resolve(BASE));
  await waitFor(() => expect(h.result.current.status).toBe('ready'));
  return h;
}

describe('useScenarioLab', () => {
  it('loads the engine default, then recalculates a what-if and swaps atomically', async () => {
    const { t, calls } = controllable();
    const h = await loaded(t, calls);
    expect(h.result.current.state.confirmed?.scenario_id).toBe(BASE.scenario_id);

    act(() => h.result.current.setMeasures(['heat_pump']));
    await waitFor(() => expect(calls).toHaveLength(2));
    expect(h.result.current.status).toBe('recalculating');
    expect(h.result.current.pending).toBe(true);
    // the confirmed scenario is still the old one while pending
    expect(h.result.current.state.confirmed?.scenario_id).toBe(BASE.scenario_id);
    expect(calls[1].req.measures).toEqual(['heat_pump']);

    await act(async () => calls[1].d.resolve(HP_ONLY));
    await waitFor(() => expect(h.result.current.status).toBe('ready'));
    expect(h.result.current.state.confirmed?.scenario_id).toBe(HP_ONLY.scenario_id);
    expect(h.result.current.state.previous?.scenario_id).toBe(BASE.scenario_id);
    expect(h.result.current.state.confirmedChange.join(' ')).toMatch(/Removed/);
    expect(h.result.current.pending).toBe(false);
  });

  it('never lets an older response overwrite a newer one (out-of-order responses)', async () => {
    const { t, calls } = controllable();
    const h = await loaded(t, calls);
    act(() => h.result.current.setMeasures(['heat_pump']));
    await waitFor(() => expect(calls).toHaveLength(2));
    act(() => h.result.current.setMeasures(['double_glazing', 'heat_pump']));
    await waitFor(() => expect(calls).toHaveLength(3));

    await act(async () => calls[2].d.resolve(GLZ_HP)); // newest first
    await waitFor(() => expect(h.result.current.state.confirmed?.scenario_id).toBe(GLZ_HP.scenario_id));
    await act(async () => calls[1].d.resolve(HP_ONLY)); // stale arrives late
    await new Promise((r) => setTimeout(r, 10));
    expect(h.result.current.state.confirmed?.scenario_id).toBe(GLZ_HP.scenario_id);
    expect(h.result.current.status).toBe('ready');
  });

  it('keeps the last confirmed scenario when a recalculation fails, and can retry', async () => {
    const { t, calls } = controllable();
    const h = await loaded(t, calls);
    act(() => h.result.current.toggleMeasure('solar_pv'));
    await waitFor(() => expect(calls).toHaveLength(2));
    await act(async () => calls[1].d.reject(new ApiError('network', 'down')));
    await waitFor(() => expect(h.result.current.status).toBe('failed'));
    expect(h.result.current.state.confirmed?.scenario_id).toBe(BASE.scenario_id);
    expect(h.result.current.state.failure?.change.join(' ')).toMatch(/Removed Solar PV/);
    expect(h.result.current.state.failure?.error.kind).toBe('network');

    act(() => h.result.current.retry());
    await waitFor(() => expect(calls).toHaveLength(3));
    await act(async () => calls[2].d.resolve(snapshotResult(HOME_A, 'default', 'cavity_wall+double_glazing+heat_pump+smart_thermostat')));
    await waitFor(() => expect(h.result.current.status).toBe('ready'));
    expect(h.result.current.state.failure).toBeNull();
  });

  it('revert discards a pending change without recording a failure', async () => {
    const { t, calls } = controllable();
    const h = await loaded(t, calls);
    act(() => h.result.current.setMeasures(['double_glazing']));
    await waitFor(() => expect(calls).toHaveLength(2));
    act(() => h.result.current.revert());
    await waitFor(() => expect(h.result.current.status).toBe('ready'));
    await act(async () => calls[1].d.resolve(GLZ_ONLY)); // arrives after revert: ignored
    await new Promise((r) => setTimeout(r, 10));
    expect(h.result.current.state.confirmed?.scenario_id).toBe(BASE.scenario_id);
    expect(h.result.current.state.failure).toBeNull();
  });

  it('records each confirmed scenario in the timeline', async () => {
    const { t, calls } = controllable();
    const h = await loaded(t, calls);
    act(() => h.result.current.setMeasures(['heat_pump']));
    await waitFor(() => expect(calls).toHaveLength(2));
    await act(async () => calls[1].d.resolve(HP_ONLY));
    await waitFor(() => expect(h.result.current.state.history).toHaveLength(2));
    expect(h.result.current.state.history[0].scenarioId).toBe(HP_ONLY.scenario_id);
  });
});
