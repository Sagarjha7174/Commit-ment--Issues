import { describe, expect, it, vi } from 'vitest';
import { ApiError } from '../api/errors';
import { createFixtureTransport, createLiveTransport } from '../api/transport';
import { Assumptions, type ScenarioRequest } from '../api/schema';
import { HOME_A, HOME_B, snapshotResult, stubFixtureFetch } from './helpers';

const req = (over: Partial<ScenarioRequest> = {}): ScenarioRequest => ({
  home_id: HOME_A, measures: null, assumptions: Assumptions.parse({}), user_reading: null,
  include_packages: true, include_sensitivity: true, include_uncertainty: true, use_modelled_epc: false,
  use_model_baseline: false, ...over,
});

function stubResponse(status: number, body: unknown) {
  vi.stubGlobal('fetch', vi.fn(async () => new Response(typeof body === 'string' ? body : JSON.stringify(body), { status })));
}

async function kindOf(p: Promise<unknown>): Promise<string> {
  try {
    await p;
    return 'ok';
  } catch (e) {
    return e instanceof ApiError ? e.kind : 'other';
  }
}

describe('live transport (routes from docs/API_CONTRACT.md, mocked fetch)', () => {
  const live = createLiveTransport();

  it('posts the request to /api/scenario and accepts a matching, valid result', async () => {
    const body = snapshotResult(HOME_A);
    const fn = vi.fn(async () => new Response(JSON.stringify(body), { status: 200 }));
    vi.stubGlobal('fetch', fn);
    const r = await live.scenario(req());
    expect(r.scenario_id).toBe(body.scenario_id);
    const [url, init] = fn.mock.calls[0] as unknown as [string, RequestInit];
    expect(url).toBe('/api/scenario');
    expect(init.method).toBe('POST');
    expect(JSON.parse(String(init.body)).home_id).toBe(HOME_A);
  });

  it('rejects a result that answers a different request as stale', async () => {
    stubResponse(200, snapshotResult(HOME_A)); // engine default
    expect(await kindOf(live.scenario(req({ measures: ['heat_pump'] })))).toBe('stale');
  });

  it('rejects a response that breaks the contract', async () => {
    const bad = { ...snapshotResult(HOME_A), score_before: { status: 'ok', total: 'forty-four' } };
    stubResponse(200, bad);
    expect(await kindOf(live.scenario(req()))).toBe('validation');
  });

  it('maps HTTP and network failures to typed errors', async () => {
    stubResponse(404, { detail: 'unknown home_id' });
    expect(await kindOf(live.scenario(req()))).toBe('not_found');
    stubResponse(422, { detail: [{ msg: 'bad' }] });
    expect(await kindOf(live.scenario(req()))).toBe('validation');
    stubResponse(503, { detail: 'llm_unavailable' });
    expect(await kindOf(live.llmHealth())).toBe('unavailable');
    stubResponse(500, 'boom');
    expect(await kindOf(live.evidence())).toBe('http');
    vi.stubGlobal('fetch', vi.fn(async () => { throw new TypeError('Failed to fetch'); }));
    expect(await kindOf(live.health())).toBe('network');
  });

  it('treats an explanation for another scenario, or HTTP 409, as stale', async () => {
    const expl = { explanation: { scenario_id: 'other', sections: [], source: 'llm' } };
    stubResponse(200, expl);
    expect(await kindOf(live.explain({ homeId: HOME_A, measures: null, scenarioId: 'mine', templateMode: false }))).toBe('stale');
    stubResponse(409, { detail: { error: 'stale_scenario' } });
    expect(await kindOf(live.explain({ homeId: HOME_A, measures: null, scenarioId: 'mine', templateMode: false }))).toBe('stale');
  });

  it('sends the whole engine request to the LLM routes, so the server explains the scenario on screen', async () => {
    const shown = req({ measures: ['cavity_wall', 'heat_pump'], assumptions: Assumptions.parse({ gas_price_p: 6 }), user_reading: { gas_kwh: 15000, elec_kwh: null } });
    const fn = vi.fn(async () => new Response(JSON.stringify({ explanation: { scenario_id: 'mine', sections: [], source: 'template' } }), { status: 200 }));
    vi.stubGlobal('fetch', fn);
    await live.explain({ homeId: HOME_A, measures: shown.measures, scenarioId: 'mine', templateMode: false, request: shown });
    const [url, init] = fn.mock.calls[0] as unknown as [string, RequestInit];
    expect(url).toBe('/llm/explain');
    expect(JSON.parse(String(init.body))).toMatchObject({
      property_id: HOME_A, measures: ['cavity_wall', 'heat_pump'], expected_scenario_id: 'mine',
      assumptions: { gas_price_p: 6 }, user_reading: { gas_kwh: 15000, elec_kwh: null },
      include_packages: true, include_sensitivity: true, include_uncertainty: true,
    });
  });

  it('accepts what-if outcomes that change assumptions or are refused', async () => {
    const outcome = { kind: 'change_assumptions', parser: 'keywords', requested_add: [], requested_remove: [], unsupported: [], added: [], removed: [], blocked: [], conditional: [], new_measures: [],
      request_changes: { gas_price_p: 6 }, invalid_reason: null, new_request: req({ assumptions: Assumptions.parse({ gas_price_p: 6 }) }) };
    const body = { outcome, scenario_id: 'new', recalculated: true, explanation: { scenario_id: 'new', sections: [], source: 'template' } };
    stubResponse(200, body);
    const w = await live.whatif({ homeId: HOME_A, measures: null, scenarioId: 'mine', question: 'gas at 6p', request: req() });
    expect(w.outcome.kind).toBe('change_assumptions');
    expect(w.outcome.new_request?.assumptions.gas_price_p).toBe(6);
    stubResponse(200, { ...body, recalculated: false, outcome: { ...outcome, kind: 'invalid_request', invalid_reason: 'a partial heat pump needs a share', new_request: null } });
    expect((await live.whatif({ homeId: HOME_A, measures: null, scenarioId: 'mine', question: 'partial heat pump', request: req() })).outcome.invalid_reason).toMatch(/share/);
  });
});

describe('fixture transport (offline snapshot)', () => {
  it('serves engine results for snapshot requests, including explicit measure sets', async () => {
    stubFixtureFetch();
    const t = createFixtureTransport('/fixtures');
    const base = await t.scenario(req());
    const hp = await t.scenario(req({ measures: ['heat_pump'] }));
    expect(hp.measures_applied).toEqual(['heat_pump']);
    expect(hp.scenario_id).not.toBe(base.scenario_id);
    expect(hp.simulation.elec_saving_kwh!).toBeLessThan(0);
  });

  it('serves assumption presets and the preset meter reading', async () => {
    stubFixtureFetch();
    const t = createFixtureTransport('/fixtures');
    const low = await t.scenario(req({ assumptions: Assumptions.parse({ heat_pump_scop: 2.44 }) }));
    expect(low.assumptions.heat_pump_scop).toBe(2.44);
    const reading = await t.scenario(req({ user_reading: { gas_kwh: 18500, elec_kwh: 3400 } }));
    expect(reading.baseline.source).toBe('user_provided');
    expect(reading.baseline.gas_provenance).toBe('user_provided');
  });

  it('says honestly when a request needs the live engine', async () => {
    stubFixtureFetch();
    const t = createFixtureTransport('/fixtures');
    expect(await kindOf(t.scenario(req({ user_reading: { gas_kwh: 1, elec_kwh: 2 } })))).toBe('fixture_miss');
    expect(await kindOf(t.scenario(req({ measures: ['heat_pump'], assumptions: Assumptions.parse({ impact_level: 'low' }) })))).toBe('fixture_miss');
    expect(await kindOf(t.scenario(req({ home_id: 'NOT-A-HOME' })))).toBe('not_found');
    expect(await kindOf(t.llmHealth())).toBe('unavailable');
    expect(await kindOf(t.scenario(req({ home_id: HOME_B, measures: ['heat_pump'] })))).toBe('ok');
  });
});

describe('budget package search (engine search with budget_gbp)', () => {
  const args = { home_id: HOME_A, assumptions: Assumptions.parse({}), user_reading: null, budget_gbp: 5000 };

  it('offline: returns the engine’s within-budget picks over the same package list', async () => {
    stubFixtureFetch();
    const ps = await createFixtureTransport('/fixtures').packages(args);
    expect(ps.budget_gbp).toBe(5000);
    const largest = ps.featured.find((f) => f.objective === 'largest_carbon_saving')!;
    expect(largest.package_id).toBe('cavity_wall+double_glazing+smart_thermostat');
    const pkg = ps.packages.find((p) => p.package_id === largest.package_id)!;
    expect(pkg.cost_gbp!).toBeLessThanOrEqual(5000);
    expect(ps.packages.length).toBe(snapshotResult(HOME_A).packages!.packages.length);
  });

  it('offline: an unsupported budget is an honest miss', async () => {
    stubFixtureFetch();
    expect(await kindOf(createFixtureTransport('/fixtures').packages({ ...args, budget_gbp: 2500 }))).toBe('fixture_miss');
  });

  it('live: POSTs to /api/packages and checks the echoed budget', async () => {
    const shared = snapshotResult(HOME_A).packages!;
    const fn = vi.fn(async () => new Response(JSON.stringify({ ...shared, budget_gbp: 5000 }), { status: 200 }));
    vi.stubGlobal('fetch', fn);
    const ps = await createLiveTransport().packages(args);
    expect(ps.budget_gbp).toBe(5000);
    const [url, init] = fn.mock.calls[0] as unknown as [string, RequestInit];
    expect(url).toBe('/api/packages');
    expect(JSON.parse(String(init.body))).toMatchObject({ home_id: HOME_A, budget_gbp: 5000 });
    stubResponse(200, { ...shared, budget_gbp: 1000 });
    expect(await kindOf(createLiveTransport().packages(args))).toBe('stale');
  });
});
