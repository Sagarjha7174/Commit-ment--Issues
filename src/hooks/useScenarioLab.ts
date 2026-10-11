/**
 * Live Scenario Lab state.
 *
 * Kept deliberately separate:
 *   confirmed  – the last scenario the engine returned successfully (everything on screen comes from it)
 *   draft      – the user's pending changes (what the controls show)
 *   inflight   – the request being calculated, with its sequence number
 *   failure    – the last failed change; the confirmed scenario is kept
 *
 * A response is accepted only if it is the latest request (sequence number) AND its echoed request
 * matches the draft that was sent (checked in the transport). The swap is atomic: previous ← confirmed ← result.
 */
import { useCallback, useEffect, useReducer, useRef } from 'react';
import { toApiError, type ApiError } from '../api/errors';
import { Assumptions, MEASURE_ORDER, type MeasureId, type Objective, type ScenarioRequest, type ScenarioResult, type UserReading } from '../api/schema';
import { useTransport } from '../api/queries';
import type { Transport } from '../api/transport';
import { measureLabel } from '../utils/labels';

export interface Draft {
  measures: MeasureId[] | null; // null = engine default (every measure that is not infeasible)
  assumptions: Assumptions;
  user_reading: UserReading | null;
}

export interface HistoryEntry { scenarioId: string; change: string[]; at: number }

export interface LabState {
  homeId: string;
  draft: Draft;
  confirmed: ScenarioResult | null;
  previous: ScenarioResult | null;
  confirmedChange: string[];
  inflight: { seq: number; draft: Draft; change: string[] } | null;
  failure: { error: ApiError; draft: Draft; change: string[] } | null;
  selectedObjective: Objective;
  history: HistoryEntry[];
}

export const DEFAULT_ASSUMPTIONS: Assumptions = Assumptions.parse({});

export function initialDraft(): Draft {
  return { measures: null, assumptions: { ...DEFAULT_ASSUMPTIONS }, user_reading: null };
}

export function initialState(homeId: string): LabState {
  return {
    homeId, draft: initialDraft(), confirmed: null, previous: null, confirmedChange: [],
    inflight: null, failure: null, selectedObjective: 'lowest_cost_meeting_threshold', history: [],
  };
}

export function orderMeasures(ms: readonly string[]): MeasureId[] {
  const s = new Set(ms);
  return MEASURE_ORDER.filter((m) => s.has(m));
}

export function draftOf(result: ScenarioResult): Draft {
  return {
    measures: result.request.measures === null ? null : orderMeasures(result.request.measures),
    assumptions: Assumptions.parse(result.request.assumptions),
    user_reading: result.request.user_reading,
  };
}

export function draftEquals(a: Draft | null | undefined, b: Draft | null | undefined): boolean {
  if (!a || !b) return false;
  const ma = a.measures === null ? null : orderMeasures(a.measures).join('+');
  const mb = b.measures === null ? null : orderMeasures(b.measures).join('+');
  return ma === mb
    && JSON.stringify(Assumptions.parse(a.assumptions)) === JSON.stringify(Assumptions.parse(b.assumptions))
    && JSON.stringify(a.user_reading ?? null) === JSON.stringify(b.user_reading ?? null);
}

export function toRequest(homeId: string, d: Draft): ScenarioRequest {
  return {
    home_id: homeId,
    measures: d.measures === null ? null : orderMeasures(d.measures),
    assumptions: d.assumptions,
    user_reading: d.user_reading,
    include_packages: true,
    include_sensitivity: true,
  };
}

const ASSUMPTION_LABEL: Partial<Record<keyof Assumptions, string>> = {
  impact_level: 'Measure impacts',
  heat_pump_scop: 'Heat-pump SCOP',
  heat_pump_mode: 'Heat-pump mode',
  space_share_of_heat_water_gas: 'Space-heating share of gas',
  baseline_scale: 'People at home',
  gas_price_p: 'Gas price',
  elec_price_p: 'Electricity price',
  apply_grants: 'Grants',
};

const ASSUMPTION_VALUE: Partial<Record<keyof Assumptions, (v: unknown) => string>> = {
  baseline_scale: (v) => (v === 1 ? 'as recorded' : Number(v) > 1 ? 'more' : 'fewer'),
  heat_pump_scop: (v) => (v === null ? 'typical' : `SCOP ${v}`),
  gas_price_p: (v) => (v === null ? 'price cap' : `${v}p/kWh`),
  elec_price_p: (v) => (v === null ? 'price cap' : `${v}p/kWh`),
  apply_grants: (v) => (v ? 'included' : 'left out'),
};

/** Human description of what changed between two drafts. Uses the engine's applied list for "engine default". */
export function describeChange(from: Draft | null, to: Draft, fromApplied?: readonly string[] | null): string[] {
  if (!from) return ['Loaded the engine’s default scenario'];
  const out: string[] = [];
  if (to.measures === null && from.measures !== null) out.push('Back to the engine’s default selection');
  else if (to.measures !== null) {
    const before = new Set(from.measures ?? fromApplied ?? []);
    const after = new Set(to.measures);
    MEASURE_ORDER.forEach((m) => {
      if (after.has(m) && !before.has(m)) out.push(`Added ${measureLabel(m)}`);
      if (!after.has(m) && before.has(m)) out.push(`Removed ${measureLabel(m)}`);
    });
  }
  const fa = Assumptions.parse(from.assumptions);
  const ta = Assumptions.parse(to.assumptions);
  (Object.keys(ta) as (keyof Assumptions)[]).forEach((k) => {
    if (JSON.stringify(fa[k]) !== JSON.stringify(ta[k])) {
      const show = (v: unknown) => ASSUMPTION_VALUE[k]?.(v) ?? (v === null ? 'catalogue value' : String(v));
      out.push(`${ASSUMPTION_LABEL[k] ?? k}: ${show(fa[k])} → ${show(ta[k])}`);
    }
  });
  const fr = JSON.stringify(from.user_reading ?? null);
  const tr = JSON.stringify(to.user_reading ?? null);
  if (fr !== tr) out.push(to.user_reading ? 'Used your meter reading as the baseline' : 'Removed your meter reading');
  return out.length ? out : ['No change'];
}

type Action =
  | { type: 'reset'; homeId: string }
  | { type: 'draft'; draft: Draft }
  | { type: 'request'; seq: number; draft: Draft; change: string[] }
  | { type: 'success'; seq: number; result: ScenarioResult }
  | { type: 'failure'; seq: number; error: ApiError }
  | { type: 'cancel' }
  | { type: 'select'; objective: Objective };

export function labReducer(s: LabState, a: Action): LabState {
  switch (a.type) {
    case 'reset':
      return initialState(a.homeId);
    case 'draft':
      return { ...s, draft: a.draft };
    case 'request':
      return { ...s, inflight: { seq: a.seq, draft: a.draft, change: a.change }, failure: null };
    case 'success': {
      if (!s.inflight || s.inflight.seq !== a.seq) return s; // superseded: never overwrite newer state
      const change = s.inflight.change;
      const entry = { scenarioId: a.result.scenario_id, change, at: Date.now() };
      return {
        ...s,
        previous: s.confirmed,
        confirmed: a.result,
        confirmedChange: change,
        inflight: null,
        failure: null,
        history: [entry, ...s.history.filter((h) => h.scenarioId !== entry.scenarioId)].slice(0, 8),
      };
    }
    case 'failure': {
      if (!s.inflight || s.inflight.seq !== a.seq) return s;
      return { ...s, failure: { error: a.error, draft: s.inflight.draft, change: s.inflight.change }, inflight: null };
    }
    case 'cancel':
      return { ...s, inflight: null, failure: null };
    case 'select':
      return { ...s, selectedObjective: a.objective };
  }
}

export interface ScenarioLab {
  state: LabState;
  status: 'loading' | 'ready' | 'recalculating' | 'failed' | 'error';
  /** The user has changes that are not yet reflected in the confirmed scenario. */
  pending: boolean;
  selectedMeasures: MeasureId[];
  toggleMeasure(m: MeasureId): void;
  setMeasures(ms: readonly string[] | null): void;
  setAssumptions(patch: Partial<Assumptions>): void;
  setReading(r: UserReading | null): void;
  /** Replace the whole draft (e.g. reopening a saved plan); the engine recalculates it. */
  restore(d: Draft): void;
  /** Apply a validated engine request (e.g. from a what-if): measures, assumptions and reading in one change. */
  applyRequest(r: ScenarioRequest): void;
  revert(): void;
  retry(): void;
  selectObjective(o: Objective): void;
}

export function useScenarioLab(homeId: string, opts: { debounceMs?: number; transport?: Transport } = {}): ScenarioLab {
  const ctxTransport = useTransport();
  const transport = opts.transport ?? ctxTransport;
  const debounceMs = opts.debounceMs ?? 250;
  const [state, dispatch] = useReducer(labReducer, homeId, initialState);
  const seqRef = useRef(0);
  const ctrlRef = useRef<AbortController | null>(null);
  const stateRef = useRef(state);
  useEffect(() => {
    stateRef.current = state;
  });

  // New home or new data source: start over.
  useEffect(() => {
    ctrlRef.current?.abort();
    dispatch({ type: 'reset', homeId });
  }, [homeId, transport]);

  const submit = useCallback((draft: Draft) => {
    const s = stateRef.current;
    const seq = ++seqRef.current;
    ctrlRef.current?.abort();
    const ctrl = new AbortController();
    ctrlRef.current = ctrl;
    const confirmedDraft = s.confirmed ? draftOf(s.confirmed) : null;
    dispatch({ type: 'request', seq, draft, change: describeChange(confirmedDraft, draft, s.confirmed?.measures_applied) });
    transport.scenario(toRequest(s.homeId, draft), ctrl.signal).then(
      (result) => {
        if (seq === seqRef.current) dispatch({ type: 'success', seq, result });
      },
      (e: unknown) => {
        const err = toApiError(e);
        if (seq === seqRef.current && err.kind !== 'aborted') dispatch({ type: 'failure', seq, error: err });
      },
    );
  }, [transport]);

  // Submit whenever the draft differs from what is confirmed, in flight, or just failed.
  useEffect(() => {
    if (state.homeId !== homeId) return;
    const confirmedDraft = state.confirmed ? draftOf(state.confirmed) : null;
    if (draftEquals(state.draft, confirmedDraft)) {
      if (state.inflight || state.failure) { // user went back to the confirmed state: drop the obsolete request
        ctrlRef.current?.abort();
        seqRef.current++;
        dispatch({ type: 'cancel' });
      }
      return;
    }
    if (draftEquals(state.draft, state.inflight?.draft) || draftEquals(state.draft, state.failure?.draft)) return;
    const wait = state.confirmed ? debounceMs : 0;
    const t = setTimeout(() => submit(state.draft), wait);
    return () => clearTimeout(t);
  }, [state.draft, state.confirmed, state.inflight, state.failure, state.homeId, homeId, debounceMs, submit]);

  useEffect(() => () => ctrlRef.current?.abort(), []);

  const base = (): MeasureId[] => {
    const s = stateRef.current;
    if (s.draft.measures) return s.draft.measures;
    return s.confirmed ? orderMeasures(s.confirmed.measures_applied) : [];
  };
  const setDraft = (patch: Partial<Draft>) => dispatch({ type: 'draft', draft: { ...stateRef.current.draft, ...patch } });

  const selectedMeasures = state.draft.measures ?? (state.confirmed ? orderMeasures(state.confirmed.measures_applied) : []);
  const pending = !!state.confirmed && !draftEquals(state.draft, draftOf(state.confirmed));
  const status: ScenarioLab['status'] = state.inflight
    ? (state.confirmed ? 'recalculating' : 'loading')
    : state.failure
      ? (state.confirmed ? 'failed' : 'error')
      : state.confirmed ? 'ready' : 'loading';

  return {
    state,
    status,
    pending,
    selectedMeasures,
    toggleMeasure: (m) => {
      const cur = base();
      setDraft({ measures: orderMeasures(cur.includes(m) ? cur.filter((x) => x !== m) : [...cur, m]) });
    },
    setMeasures: (ms) => setDraft({ measures: ms === null ? null : orderMeasures(ms) }),
    setAssumptions: (patch) => setDraft({ assumptions: Assumptions.parse({ ...stateRef.current.draft.assumptions, ...patch }) }),
    setReading: (r) => setDraft({ user_reading: r }),
    restore: (d) => dispatch({ type: 'draft', draft: { measures: d.measures === null ? null : orderMeasures(d.measures), assumptions: Assumptions.parse(d.assumptions), user_reading: d.user_reading } }),
    applyRequest: (r) => dispatch({ type: 'draft', draft: { measures: r.measures === null ? null : orderMeasures(r.measures), assumptions: Assumptions.parse(r.assumptions), user_reading: r.user_reading ?? null } }),
    revert: () => {
      const c = stateRef.current.confirmed;
      dispatch({ type: 'draft', draft: c ? draftOf(c) : initialDraft() });
    },
    retry: () => {
      const f = stateRef.current.failure;
      if (f) submit(f.draft);
    },
    selectObjective: (o) => dispatch({ type: 'select', objective: o }),
  };
}
