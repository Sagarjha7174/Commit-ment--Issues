/**
 * The single API client. Components never call fetch directly: they use a Transport,
 * which is either the live FastAPI backend or the offline engine snapshot.
 * Every response is validated against src/api/schema.ts before it reaches the UI.
 */
import type { z } from 'zod';
import { API_BASE, FIXTURE_BASE, LLM_TIMEOUT_MS, REQUEST_TIMEOUT_MS, type DataMode } from './config';
import { ApiError, toApiError } from './errors';
import {
  Assumptions, DemoHomes, Evidence, ExplainResponse, Health, LlmHealth, PackageSearch, Portfolio, ScenarioRequest,
  ScenarioResult, WhatIfResponse,
  type DemoHome, type Explanation, type MeasureId, type ScenarioRequest as Req,
  type ScenarioResult as Result, type WhatIfResponse as WhatIf,
} from './schema';

export interface PortfolioParams { top_n: number; split?: string | null }
/** request: the engine request of the scenario on screen, sent whole so the server explains exactly that scenario. */
export interface ExplainArgs { homeId: string; measures: MeasureId[] | null; scenarioId: string; templateMode: boolean; request?: Req }
/** Engine package search with a spending limit (services/api.py search(..., budget_gbp)). */
export interface BudgetSearchArgs {
  home_id: string;
  assumptions: z.infer<typeof Assumptions>;
  user_reading: Req['user_reading'];
  budget_gbp: number;
}
export interface WhatIfArgs { homeId: string; measures: MeasureId[] | null; scenarioId: string; question: string; request?: Req }

export interface Transport {
  readonly kind: DataMode;
  health(signal?: AbortSignal): Promise<z.infer<typeof Health>>;
  demoHomes(signal?: AbortSignal): Promise<DemoHome[]>;
  scenario(req: Req, signal?: AbortSignal): Promise<Result>;
  portfolio(params: PortfolioParams, signal?: AbortSignal): Promise<z.infer<typeof Portfolio>>;
  evidence(signal?: AbortSignal): Promise<z.infer<typeof Evidence>>;
  llmHealth(signal?: AbortSignal): Promise<z.infer<typeof LlmHealth>>;
  explain(args: ExplainArgs, signal?: AbortSignal): Promise<Explanation>;
  whatif(args: WhatIfArgs, signal?: AbortSignal): Promise<WhatIf>;
  packages(args: BudgetSearchArgs, signal?: AbortSignal): Promise<z.infer<typeof PackageSearch>>;
}

export function parseOrThrow<S extends z.ZodType>(schema: S, data: unknown, what: string): z.infer<S> {
  const r = schema.safeParse(data);
  if (!r.success) {
    const first = r.error.issues[0];
    const where = first ? `${first.path.join('.') || '(root)'}: ${first.message}` : 'unknown field';
    throw new ApiError('validation', `${what} does not match the contract (${where}).`, { detail: r.error.issues });
  }
  return r.data;
}

/** Normalise a request so equal requests compare equal (measures in engine order). */
export function normaliseRequest(req: Req): Req {
  return ScenarioRequest.parse(req);
}

function sameMeasures(a: readonly string[] | null, b: readonly string[] | null): boolean {
  if (a === null || b === null) return a === b;
  return a.length === b.length && [...a].sort().join('+') === [...b].sort().join('+');
}

/** True when a result is the answer to exactly this request (guards against stale or mixed-up responses). */
export function resultMatchesRequest(result: Result, req: Req): boolean {
  const r = result.request;
  return r.home_id === req.home_id
    && sameMeasures(r.measures, req.measures)
    && JSON.stringify(Assumptions.parse(r.assumptions)) === JSON.stringify(Assumptions.parse(req.assumptions))
    && JSON.stringify(r.user_reading) === JSON.stringify(req.user_reading)
    && r.include_packages === req.include_packages
    && r.include_sensitivity === req.include_sensitivity
    && r.include_uncertainty === req.include_uncertainty;
}

/** The rest of the engine request, for the LLM routes (they rerun exactly this request). */
function engineFields(req: Req | undefined): Record<string, unknown> {
  if (!req) return {};
  const r = normaliseRequest(req);
  return {
    assumptions: r.assumptions, user_reading: r.user_reading, include_packages: r.include_packages,
    include_sensitivity: r.include_sensitivity, include_uncertainty: r.include_uncertainty,
  };
}

// ---------------------------------------------------------------- live

function withTimeout(signal: AbortSignal | undefined, ms: number): AbortSignal {
  const t = AbortSignal.timeout(ms);
  return signal ? AbortSignal.any([signal, t]) : t;
}

async function http(path: string, init: RequestInit & { timeoutMs?: number } = {}): Promise<unknown> {
  let res: Response;
  try {
    res = await fetch(`${API_BASE}${path}`, {
      ...init,
      headers: { Accept: 'application/json', ...(init.body ? { 'Content-Type': 'application/json' } : {}), ...init.headers },
      signal: withTimeout(init.signal ?? undefined, init.timeoutMs ?? REQUEST_TIMEOUT_MS),
    });
  } catch (e) {
    throw toApiError(e);
  }
  let body: unknown = null;
  const text = await res.text();
  if (text) {
    try {
      body = JSON.parse(text);
    } catch {
      body = text;
    }
  }
  if (res.ok) return body;
  const detail = (body && typeof body === 'object' && 'detail' in body) ? (body as { detail: unknown }).detail : body;
  const msg = typeof detail === 'string' ? detail : `HTTP ${res.status} from ${path}`;
  if (res.status === 404) throw new ApiError('not_found', msg, { status: 404, detail });
  if (res.status === 409) throw new ApiError('stale', 'The server is showing a different scenario.', { status: 409, detail });
  if (res.status === 422) throw new ApiError('validation', 'The backend rejected the request as invalid.', { status: 422, detail });
  if (res.status === 503 || res.status === 501) throw new ApiError('unavailable', msg, { status: res.status, detail });
  throw new ApiError('http', msg, { status: res.status, detail });
}

export function createLiveTransport(): Transport {
  return {
    kind: 'live',
    async health(signal) {
      return parseOrThrow(Health, await http('/api/health', { signal }), 'Health');
    },
    async demoHomes(signal) {
      return parseOrThrow(DemoHomes, await http('/api/demo-homes', { signal }), 'Demo homes');
    },
    async scenario(req, signal) {
      const body = normaliseRequest(req);
      const result = parseOrThrow(ScenarioResult, await http('/api/scenario', { method: 'POST', body: JSON.stringify(body), signal }), 'Scenario result');
      if (!resultMatchesRequest(result, body)) throw new ApiError('stale', 'The backend answered a different request.');
      return result;
    },
    async portfolio(params, signal) {
      const q = new URLSearchParams({ top_n: String(params.top_n) });
      if (params.split) q.set('split', params.split);
      return parseOrThrow(Portfolio, await http(`/api/portfolio?${q}`, { signal, timeoutMs: 60000 }), 'Portfolio');
    },
    async evidence(signal) {
      return parseOrThrow(Evidence, await http('/api/evidence', { signal }), 'Evidence');
    },
    async llmHealth(signal) {
      return parseOrThrow(LlmHealth, await http('/llm/health', { signal }), 'LLM health');
    },
    async explain(args, signal) {
      const body = {
        property_id: args.homeId, measures: args.measures, expected_scenario_id: args.scenarioId,
        template_mode: args.templateMode, prefetch_llm: args.templateMode, ...engineFields(args.request),
      };
      const data = await http('/llm/explain', { method: 'POST', body: JSON.stringify(body), signal, timeoutMs: LLM_TIMEOUT_MS });
      const expl = parseOrThrow(ExplainResponse, data, 'Explanation').explanation;
      if (expl.scenario_id !== args.scenarioId) throw new ApiError('stale', 'The explanation belongs to a different scenario.');
      return expl;
    },
    async packages(args, signal) {
      const body = { ...args, assumptions: Assumptions.parse(args.assumptions) };
      const ps = parseOrThrow(PackageSearch, await http('/api/packages', { method: 'POST', body: JSON.stringify(body), signal }), 'Package search');
      if (ps.budget_gbp !== args.budget_gbp) throw new ApiError('stale', 'The backend answered for a different budget.');
      return ps;
    },
    async whatif(args, signal) {
      const body = {
        property_id: args.homeId, measures: args.measures, question: args.question, expected_scenario_id: args.scenarioId,
        ...engineFields(args.request),
      };
      return parseOrThrow(WhatIfResponse, await http('/llm/whatif', { method: 'POST', body: JSON.stringify(body), signal, timeoutMs: LLM_TIMEOUT_MS }), 'What-if');
    },
  };
}

// ---------------------------------------------------------------- offline snapshot

interface ManifestVariant { overrides: Record<string, unknown>; shared: string; scenarios: Record<string, string>; budgets?: Record<string, string> }
interface ManifestHome {
  case: string;
  selectable: string[];
  variants: Record<string, ManifestVariant>;
  user_reading?: { reading: { gas_kwh: number | null; elec_kwh: number | null }; shared: string; scenarios: Record<string, string>; budgets?: Record<string, string> };
}
export interface Manifest {
  kind: string;
  engine_branch: string;
  engine_commit: string;
  generated_at: string;
  generator: string;
  home_inputs: string;
  parity: string;
  assumption_presets: Record<string, Record<string, unknown>>;
  homes: Record<string, ManifestHome>;
}

export function measuresKey(measures: readonly string[] | null): string {
  if (measures === null) return 'engine-default';
  if (measures.length === 0) return 'none';
  return [...measures].sort().join('+');
}

const DEFAULT_ASSUMPTIONS = Assumptions.parse({});

/** Which assumption preset a request corresponds to, or null if it is not a snapshot preset. */
export function presetFor(manifest: Manifest, assumptions: z.infer<typeof Assumptions>): string | null {
  const diff: Record<string, unknown> = {};
  for (const [k, v] of Object.entries(Assumptions.parse(assumptions))) {
    if (JSON.stringify(v) !== JSON.stringify(DEFAULT_ASSUMPTIONS[k as keyof typeof DEFAULT_ASSUMPTIONS])) diff[k] = v;
  }
  for (const [key, overrides] of Object.entries(manifest.assumption_presets)) {
    if (JSON.stringify(Object.entries(overrides).sort()) === JSON.stringify(Object.entries(diff).sort())) return key;
  }
  return null;
}

export function createFixtureTransport(base = FIXTURE_BASE): Transport {
  const cache = new Map<string, Promise<unknown>>();
  const get = (path: string, signal?: AbortSignal): Promise<unknown> => {
    if (!cache.has(path)) {
      const p = fetch(`${base}/${path}`, { signal: withTimeout(undefined, REQUEST_TIMEOUT_MS) })
        .then(async (res) => {
          if (!res.ok) throw new ApiError(res.status === 404 ? 'fixture_miss' : 'http', `Snapshot file ${path} could not be loaded (HTTP ${res.status}).`);
          return res.json();
        })
        .catch((e) => {
          cache.delete(path);
          throw toApiError(e);
        });
      cache.set(path, p);
    }
    const p = cache.get(path)!;
    if (!signal) return p;
    return new Promise((resolve, reject) => {
      if (signal.aborted) return reject(new ApiError('aborted', 'Request superseded by a newer change.'));
      signal.addEventListener('abort', () => reject(new ApiError('aborted', 'Request superseded by a newer change.')), { once: true });
      p.then(resolve, reject);
    });
  };
  const manifest = (signal?: AbortSignal) => get('manifest.json', signal) as Promise<Manifest>;
  const llmOff = () => new ApiError('unavailable', 'The LLM service is not part of the offline snapshot; explanations use the deterministic template.');

  return {
    kind: 'fixtures',
    async health(signal) {
      const m = await manifest(signal);
      const ev = parseOrThrow(Evidence, await get('evidence.json', signal), 'Evidence');
      return { status: 'ok', data_mode: `offline_snapshot@${m.engine_commit}`, versions: ev.versions };
    },
    async demoHomes(signal) {
      return parseOrThrow(DemoHomes, await get('demo-homes.json', signal), 'Demo homes');
    },
    async scenario(req, signal) {
      const body = normaliseRequest(req);
      const m = await manifest(signal);
      const home = m.homes[body.home_id];
      if (!home) {
        throw new ApiError('not_found', `Home ${body.home_id} is not in the offline snapshot (it contains the three public demo homes only).`);
      }
      if (!body.include_packages || !body.include_sensitivity || !body.include_uncertainty) {
        throw new ApiError('fixture_miss', 'The snapshot stores results with packages, sensitivity and uncertainty included.');
      }
      let variant: { shared: string; scenarios: Record<string, string> } | undefined;
      if (body.user_reading) {
        const ur = home.user_reading;
        const same = ur && ur.reading.gas_kwh === body.user_reading.gas_kwh && ur.reading.elec_kwh === body.user_reading.elec_kwh;
        if (!same || presetFor(m, body.assumptions) !== 'default') {
          const hint = ur ? ` The snapshot holds one preset reading for this home (gas ${ur.reading.gas_kwh} kWh, electricity ${ur.reading.elec_kwh} kWh).` : '';
          throw new ApiError('fixture_miss', `Recalculating with your own meter reading needs the live engine.${hint}`);
        }
        variant = ur;
      } else {
        const preset = presetFor(m, body.assumptions);
        variant = preset ? home.variants[preset] : undefined;
        if (!variant) throw new ApiError('fixture_miss', 'This assumption combination needs the live engine; the snapshot holds the presets shown.');
      }
      const file = variant.scenarios[measuresKey(body.measures)];
      if (!file) {
        throw new ApiError('fixture_miss', 'Offline, these settings are available for the engine’s suggested set and its three plans. Choose one of those, or use the live engine for your own mix.');
      }
      const [core, shared] = await Promise.all([get(file, signal), get(variant.shared, signal)]);
      const result = parseOrThrow(ScenarioResult, { ...(core as object), ...(shared as object) }, 'Scenario result');
      if (!resultMatchesRequest(result, body)) throw new ApiError('stale', 'Snapshot file does not match the request.');
      return result;
    },
    async portfolio(_params, signal) {
      return parseOrThrow(Portfolio, await get('portfolio.json', signal), 'Portfolio');
    },
    async evidence(signal) {
      return parseOrThrow(Evidence, await get('evidence.json', signal), 'Evidence');
    },
    async packages(args, signal) {
      const m = await manifest(signal);
      const home = m.homes[args.home_id];
      if (!home) throw new ApiError('not_found', `Home ${args.home_id} is not in the offline snapshot.`);
      const preset = presetFor(m, args.assumptions);
      const ur = home.user_reading;
      const variant = args.user_reading
        ? (ur && preset === 'default' && ur.reading.gas_kwh === args.user_reading.gas_kwh && ur.reading.elec_kwh === args.user_reading.elec_kwh ? ur : undefined)
        : preset ? home.variants[preset] : undefined;
      const file = variant?.budgets?.[String(args.budget_gbp)];
      if (!variant || !file) {
        const offered = Object.keys(home.variants.default?.budgets ?? {}).map((b) => `£${Number(b).toLocaleString('en-GB')}`).join(', ');
        throw new ApiError('fixture_miss', `Offline, budget plans are available for ${offered || 'no budgets'} with these settings only; other budgets need the live engine.`);
      }
      const [picks, shared] = await Promise.all([get(file, signal), get(variant.shared, signal)]);
      const ps = parseOrThrow(PackageSearch, { ...(shared as { packages: object }).packages, ...(picks as object) }, 'Package search');
      if (ps.budget_gbp !== args.budget_gbp) throw new ApiError('stale', 'Snapshot file is for a different budget.');
      return ps;
    },
    async llmHealth() {
      throw llmOff();
    },
    async explain() {
      throw llmOff();
    },
    async whatif() {
      throw llmOff();
    },
  };
}

export async function loadManifest(base = FIXTURE_BASE): Promise<Manifest> {
  const res = await fetch(`${base}/manifest.json`);
  if (!res.ok) throw new ApiError('fixture_miss', 'Offline snapshot manifest missing.');
  return res.json();
}

export function createTransport(mode: DataMode): Transport {
  return mode === 'live' ? createLiveTransport() : createFixtureTransport();
}
