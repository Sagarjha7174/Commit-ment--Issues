/** The offline snapshot is real engine output: every file must satisfy the scenario contract. */
import { readdirSync, readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { describe, expect, it } from 'vitest';
import { DemoHomes, Evidence, Portfolio, ScenarioResult } from '../api/schema';
import { resultMatchesRequest } from '../api/transport';
import { FIXTURES, HOME_A, HOME_B, HOME_C, readFixture, snapshotResult } from './helpers';

type Manifest = { homes: Record<string, { variants: Record<string, { shared: string; scenarios: Record<string, string> }>; user_reading?: { shared: string; scenarios: Record<string, string> } }> };
const manifest = readFixture('manifest.json') as Manifest;
/** The engine's hand-calculated acceptance values (tests/fixtures/hand_calc_demo.py, no engine imports). */
const handCalc = (c: 'a' | 'b' | 'c') => JSON.parse(readFileSync(resolve(__dirname, `../../../tests/fixtures/scenario_${c}.json`), 'utf8')).expect;

describe('offline snapshot satisfies the scenario contract', () => {
  it('validates every scenario file once stitched with its shared packages', () => {
    let n = 0;
    for (const [hid, home] of Object.entries(manifest.homes)) {
      const variants = [...Object.values(home.variants), ...(home.user_reading ? [home.user_reading] : [])];
      for (const v of variants) {
        const shared = readFixture(v.shared) as object;
        for (const file of Object.values(v.scenarios)) {
          const parsed = ScenarioResult.safeParse({ ...(readFixture(file) as object), ...shared });
          if (!parsed.success) throw new Error(`${file}: ${parsed.error.issues[0]?.path.join('.')} ${parsed.error.issues[0]?.message}`);
          expect(parsed.data.home.home_id).toBe(hid);
          expect(resultMatchesRequest(parsed.data, parsed.data.request)).toBe(true);
          n++;
        }
      }
    }
    const onDisk = readdirSync(resolve(FIXTURES, 'scenarios')).flatMap((d) => readdirSync(resolve(FIXTURES, 'scenarios', d)));
    expect(n).toBe(onDisk.length);
  });

  it('validates demo homes, portfolio and evidence', () => {
    expect(DemoHomes.parse(readFixture('demo-homes.json'))).toHaveLength(3);
    expect(Portfolio.safeParse(readFixture('portfolio.json')).success).toBe(true);
    const ev = Evidence.safeParse(readFixture('evidence.json'));
    expect(ev.success ? 'ok' : JSON.stringify(ev.error.issues.slice(0, 3))).toBe('ok');
  });

  it('scenario ids are unique per request (no two calculations share an id)', () => {
    const ids = new Set<string>();
    for (const home of Object.values(manifest.homes)) {
      for (const v of Object.values(home.variants)) {
        for (const f of Object.values(v.scenarios)) ids.add((readFixture(f) as { scenario_id: string }).scenario_id);
      }
    }
    const count = Object.values(manifest.homes).reduce((s, h) => s + Object.values(h.variants).reduce((t, v) => t + Object.keys(v.scenarios).length, 0), 0);
    expect(ids.size).toBe(count);
  });
});

describe('demo homes match the engine’s hand-calculated acceptance values', () => {
  it('A: Poor gas house scores 44, heat pump raises electricity (negative saving)', () => {
    const a = ScenarioResult.parse(snapshotResult(HOME_A));
    const e = handCalc('a');
    expect(a.score_before.total).toBe(44);
    expect(a.score_before.total).toBe(e.score_before);
    expect(a.score_before.classification).toBe('Poor');
    expect(a.measures_applied).toEqual(e.feasible);
    expect(a.score_after?.total).toBe(70);
    expect(a.score_after?.total).toBe(e.score_after);
    expect(a.simulation.elec_saving_kwh!).toBeLessThan(0);
    expect(a.simulation.gas_saving_kwh!).toBeGreaterThan(0);
    expect(a.simulation.gas_saving_kwh!).toBeCloseTo(e.package_gas_saving_kwh, 6);
    expect(a.simulation.elec_saving_kwh!).toBeCloseTo(e.package_elec_saving_kwh, 6);
    expect(a.carbon.total_kg!).toBeCloseTo(e.carbon_saving_kg, 6);
    expect(a.carbon.total_kg!).toBeCloseTo(3120.41, 1);
    const infeasible = a.feasibility.filter((f) => f.state === 'infeasible').map((f) => f.measure);
    expect(infeasible).toEqual(e.infeasible);   // flat roof: no loft (D20); cavity walls: no solid-wall insulation
  });

  it('B: flat — loft and solar infeasible; electric heating savings estimated on electricity (D16)', () => {
    const b = ScenarioResult.parse(snapshotResult(HOME_B));
    expect(b.score_before.total).toBe(61);
    expect(b.score_before.total).toBe(handCalc('b').score_before);
    const state = Object.fromEntries(b.feasibility.map((f) => [f.measure, f.state]));
    expect(state.loft_insulation).toBe('infeasible');
    expect(state.solar_pv).toBe('infeasible');
    const hc = handCalc('b') as unknown as { package_elec_saving_kwh: number; improvement_potential_pct: number };
    expect(b.simulation.improvement_potential_status).toBe('ok');
    expect(b.simulation.elec_saving_kwh).toBeCloseTo(hc.package_elec_saving_kwh, 6);
    expect(b.simulation.improvement_potential_pct).toBeCloseTo(hc.improvement_potential_pct, 6);
    expect(b.simulation.measures.find((m) => m.measure === 'heat_pump')?.status).toBe('ok');
  });

  it('C: missing data — score unavailable, baselines null (never 0), all measures need verification', () => {
    const c = ScenarioResult.parse(snapshotResult(HOME_C));
    expect(c.score_before.status).toBe('unavailable');
    expect(c.score_before.total).toBeNull();
    expect(c.score_before.completeness).toBe('1/7');
    expect(c.baseline.gas_kwh).toBeNull();
    expect(c.baseline.elec_kwh).toBeNull();
    expect(c.feasibility.every((f) => f.state === 'needs_verification')).toBe(true);
    expect(c.feasibility.every((f) => f.missing_inputs.length > 0)).toBe(true);
  });
});
