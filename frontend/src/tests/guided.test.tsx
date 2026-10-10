/** The guided, plain-language flow: situation questions, three options, try changes, plan check. */
import { screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it } from 'vitest';
import { DEFAULT_SITUATION, resetSituationForTests, setSituation, type Situation } from '../hooks/useSituation';
import { resetSavedPlansForTests } from '../hooks/useSavedPlans';
import { permissionFor } from '../utils/permissions';
import { buildDecisionRecord } from '../utils/decisionRecord';
import { ScenarioResult } from '../api/schema';
import { HOME_A, HOME_B, HOME_C, renderApp, snapshotResult, stubFixtureFetch } from './helpers';

const T = { timeout: 4000 };
const TENANT: Situation = { role: 'tenant', horizon: '2to5', budgetGbp: 5000, budgetAnswered: true, priority: 'spend_least', change: 'more_people', done: true };

beforeEach(() => {
  window.localStorage.clear();
  resetSituationForTests();
  resetSavedPlansForTests();
});

async function open(id: string, tab = 'home') {
  stubFixtureFetch();
  renderApp(`/home/${id}?tab=${tab}`);
  await screen.findByRole('tablist', { name: 'Steps' }, T);
}

describe('your situation (optional questions)', () => {
  it('asks one question at a time, can be skipped, and is remembered', async () => {
    await open(HOME_A);
    expect(screen.getByRole('heading', { name: 'How are you connected to this home?' })).toBeInTheDocument();
    await userEvent.click(screen.getByRole('button', { name: 'I rent it' }));
    expect(screen.getByRole('heading', { name: 'How long do you expect to stay?' })).toBeInTheDocument();
    await userEvent.click(screen.getByRole('button', { name: 'Skip these questions' }));
    expect(screen.queryByRole('heading', { name: /How long do you expect/ })).not.toBeInTheDocument();
    expect(JSON.parse(window.localStorage.getItem('ghs.situation.v1')!)).toMatchObject({ role: 'tenant', done: true });
    expect(screen.getByRole('button', { name: /Tenant/ })).toBeInTheDocument(); // summary chip
  });

  it('never asks for income, employer or bank details', async () => {
    await open(HOME_A);
    expect(screen.getByText(/We never ask for income, employer or bank details/)).toBeInTheDocument();
  });
});

describe('step 1: your home', () => {
  it('explains the score in plain words from the engine’s class bands', async () => {
    setSituation({ ...DEFAULT_SITUATION, done: true });
    await open(HOME_A);
    expect(await screen.findByText('Homes scoring 30–49 are classed poor.', {}, T)).toBeInTheDocument();
    expect(screen.getByText('44')).toBeInTheDocument();
    expect(screen.getByText('Not checked yet')).toBeInTheDocument(); // flood / heat risk: honest gap
  });

  it('missing data stays missing (home C)', async () => {
    setSituation({ ...DEFAULT_SITUATION, done: true });
    await open(HOME_C);
    expect(screen.getByText(/we can’t score it fairly/)).toBeInTheDocument();
    expect(screen.getAllByText('Unavailable').length).toBeGreaterThan(0);
    expect(screen.queryByText(/^0 kWh/)).not.toBeInTheDocument();
  });
});

describe('step 2: your options', () => {
  it('the budget filters the plans: the engine re-picks within it', async () => {
    setSituation(TENANT);
    await open(HOME_A, 'options');
    expect(await screen.findByRole('heading', { name: 'Three ways to improve this home for £5,000 or less' }, T)).toBeInTheDocument();
    const biggest = screen.getByRole('heading', { name: 'Biggest carbon cut' }).closest('article')!;
    // engine budget search (services/packages.py) at £5,000: loft + cavity wall + thermostat, not the £29,350 six-measure plan
    expect(within(biggest).getByText('Loft + Cavity wall + Thermostat')).toBeInTheDocument();
    expect(within(biggest).getByText('Within your budget')).toBeInTheDocument();
    expect(within(biggest).getByText(/Without a budget limit: .*£29,350/)).toBeInTheDocument();
    expect(screen.queryByText(/Over your £5,000 budget/)).not.toBeInTheDocument();

    await userEvent.click(screen.getByRole('button', { name: 'Compare with no budget limit' }));
    expect(await screen.findByText('Over your £5,000 budget')).toBeInTheDocument();
    expect(screen.getByRole('heading', { name: 'Three ways to improve this home' })).toBeInTheDocument();

    await userEvent.click(screen.getByRole('button', { name: '£1,000' }));
    const biggest1k = (await screen.findByRole('heading', { name: 'Three ways to improve this home for £1,000 or less' }, T)) && screen.getByRole('heading', { name: 'Biggest carbon cut' }).closest('article')!;
    expect(within(biggest1k).getByText('Cavity wall')).toBeInTheDocument();
  });

  it('highlights the engine pick that matches the stated priority', async () => {
    setSituation(TENANT);
    await open(HOME_A, 'options');
    const match = await screen.findByText('Matches what matters to you', {}, T);
    const card = match.closest('article')!;
    expect(within(card).getByRole('heading', { name: 'Cheapest real improvement' })).toBeInTheDocument();
    expect(screen.getByText(/As a tenant, every one of these needs your landlord’s permission/)).toBeInTheDocument();
    expect(screen.getAllByText(/Needs landlord permission/).length).toBeGreaterThan(0);
  });

  it('choosing a plan recalculates it and opens the plan check', async () => {
    setSituation(TENANT);
    await open(HOME_A, 'options');
    const card = (await screen.findByText('Matches what matters to you', {}, T)).closest('article')!;
    await userEvent.click(within(card).getByRole('button', { name: 'Choose this plan' }));
    expect(await screen.findByRole('heading', { name: '1 improvement' }, T)).toBeInTheDocument();
    expect(screen.getByText(/About £1,000: within your £5,000 budget/)).toBeInTheDocument();
    expect(screen.getByText(/1 of 1 need permission from your landlord/)).toBeInTheDocument();
    expect(screen.getByLabelText('Request letter')).toHaveTextContent(/Dear landlord[\s\S]*Cavity-wall insulation/);
  });
});

describe('step 3: try changes', () => {
  it('“more people at home” is recalculated by the engine (baseline_scale 1.15)', async () => {
    setSituation({ ...TENANT });
    await open(HOME_A, 'try');
    const expected = snapshotResult(HOME_A, 'occupancy-high', 'engine-default').scenario_id.slice(0, 8);
    await userEvent.click(screen.getByRole('button', { name: 'More people' }));
    await waitFor(() => expect(screen.getAllByText(expected).length).toBeGreaterThan(0), T);
  });

  it('adds and removes improvements with plain buttons', async () => {
    setSituation({ ...DEFAULT_SITUATION, done: true });
    await open(HOME_A, 'try');
    await userEvent.click(screen.getByRole('button', { name: 'Remove Solar PV' }));
    expect(await screen.findByRole('button', { name: 'Add Solar PV' }, T)).toBeInTheDocument();
    await screen.findByText('What changed', {}, T);
    expect(screen.getByRole('button', { name: 'Add Solid-wall insulation' })).toBeDisabled();
  });
});

describe('step 4: your plan', () => {
  it('answers the six questions, and says what is not known (home C)', async () => {
    setSituation({ ...DEFAULT_SITUATION, done: true });
    await open(HOME_C, 'plan');
    for (const q of ['Can I do it?', 'Can I afford it now?', 'Will it work for me?', 'What if things change?', 'How do I know it’s real?', 'What happens after installation?']) {
      expect(screen.getByText(q)).toBeInTheDocument();
    }
    expect(screen.getByText(/We don’t know this home’s energy use/)).toBeInTheDocument();
    expect(screen.getByText(/need a survey first/)).toBeInTheDocument();
  });

  it('saves a plan in this browser and reopens it by re-running the engine', async () => {
    setSituation({ ...DEFAULT_SITUATION, done: true });
    await open(HOME_A, 'plan');
    const original = snapshotResult(HOME_A).scenario_id.slice(0, 8);
    await userEvent.type(screen.getByLabelText('Plan name'), 'Everything');
    await userEvent.click(screen.getByRole('button', { name: 'Save' }));
    expect(screen.getByText('Saved “Everything”.')).toBeInTheDocument();
    expect(JSON.parse(window.localStorage.getItem('ghs.savedPlans.v1')!)[0]).toMatchObject({ name: 'Everything', homeId: HOME_A });

    await userEvent.click(screen.getByRole('tab', { name: /Try changes/ }));
    await userEvent.click(screen.getByRole('button', { name: 'Remove Solar PV' }));
    await waitFor(() => expect(screen.queryAllByText(original).filter((n) => n.closest('.dock'))).toHaveLength(0), T);

    await userEvent.click(screen.getByRole('tab', { name: /Your plan/ }));
    await userEvent.click(screen.getByRole('button', { name: 'Open saved plan Everything' }));
    await waitFor(() => expect(screen.queryAllByText(original).filter((n) => n.closest('.dock')).length).toBe(1), T);
  });
});

describe('permissions and the decision record', () => {
  const a = ScenarioResult.parse(snapshotResult(HOME_A));
  const b = ScenarioResult.parse(snapshotResult(HOME_B));
  const f = (r: typeof a, m: string) => r.feasibility.find((x) => x.measure === m);

  it('engine feasibility is a hard gate before any permission rule', () => {
    expect(permissionFor('solid_wall', f(a, 'solid_wall'), 'owner', a.home).state).toBe('not_feasible');
    expect(permissionFor('loft_insulation', f(b, 'loft_insulation'), 'tenant', b.home).state).toBe('not_feasible');
  });

  it('permission states depend on role and building, and are never “confirmed”', () => {
    expect(permissionFor('cavity_wall', f(a, 'cavity_wall'), 'tenant', a.home).state).toBe('needs_consent');
    expect(permissionFor('solar_pv', f(a, 'solar_pv'), 'leaseholder', a.home).state).toBe('needs_building_approval');
    expect(permissionFor('heat_pump', f(a, 'heat_pump'), 'owner', a.home).state).toBe('check_local_rules');
    expect(permissionFor('loft_insulation', f(a, 'loft_insulation'), 'owner', a.home).state).toBe('no_known_issue');
  });

  it('the decision record holds the scenario id, versions, situation and unknowns', () => {
    const rec = buildDecisionRecord(a, TENANT);
    expect(rec.scenario_id).toBe(a.scenario_id);
    expect(rec.versions).toEqual(a.versions);
    expect(rec.situation_user_provided.role).toBe('tenant');
    expect(rec.outcomes_estimated.score_before).toBe(44);
    expect(rec.not_modelled).toContain('energy bills and payback in £');
    expect(rec.feasibility.find((x) => x.measure === 'cavity_wall')?.permission_guidance).toBe('Needs landlord permission');
  });
});
