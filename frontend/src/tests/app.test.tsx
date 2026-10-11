/** Integration: the real app rendered against the offline engine snapshot (real engine output). */
import { fireEvent, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it } from 'vitest';
import { ApiError } from '../api/errors';
import { createFixtureTransport, type Transport } from '../api/transport';
import type { Explanation, Portfolio } from '../api/schema';
import { HOME_A, HOME_B, HOME_C, readFixture, renderApp, snapshotResult, stubFixtureFetch } from './helpers';

const T = { timeout: 4000 };

/** The full detail view lives in the "Expert details" tab; the guided tabs have their own tests. */
async function openHome(id: string, transport?: Transport, tab = 'expert') {
  stubFixtureFetch();
  renderApp(`/home/${id}?tab=${tab}`, transport);
  await screen.findByRole('heading', { level: 1 }, T);
}

function withLlm(over: Partial<Transport>): Transport {
  return { ...createFixtureTransport('/fixtures'), kind: 'live', ...over } as Transport;
}

describe('My Home: demo home A (Poor gas house)', () => {
  it('shows the engine score, class, completeness and the main data limitation', async () => {
    await openHome(HOME_A);
    expect(screen.getByRole('heading', { level: 1 })).toHaveTextContent('Demo home A');
    expect(screen.getAllByText('Poor').length).toBeGreaterThan(0);
    expect(screen.getAllByText(/7\/7 parts recorded/).length).toBeGreaterThan(0);
    expect(screen.getByText(/NEED benchmark for similar homes, not this home’s meter/)).toBeInTheDocument();
  });

  it('shows the heat-pump electricity rise as a negative saving, in words as well as colour', async () => {
    await openHome(HOME_A);
    expect(document.querySelector('.callout-increase')).toHaveTextContent(/Electricity use rises/);
    expect(screen.getAllByText('−4,865').length).toBeGreaterThan(0);
    expect(screen.getAllByText('increase').length).toBeGreaterThan(0);
  });

  it('shows the three featured plans with the contract’s literal labels, never “best overall”', async () => {
    await openHome(HOME_A);
    const studio = document.getElementById('studio')!;
    for (const label of ['Lowest-cost package cutting emissions by at least 10%', 'Largest carbon saving', 'Most carbon saved per pound among packages cutting at least 10%']) {
      expect(within(studio).getByRole('heading', { name: label })).toBeInTheDocument();
    }
    within(studio).getAllByRole('heading').forEach((h) => expect(h.textContent).not.toMatch(/best overall/i));
    expect(within(studio).getAllByText(/sensitivity runs/).length).toBe(3);
  });

  it('shows the gated property-value range as an association, and the indicative EPC change', async () => {
    await openHome(HOME_A);
    expect(screen.getAllByText('+2.9% – 7.2%').length).toBeGreaterThan(0);
    expect(screen.getAllByText(/an association in York sales, not a promise/).length).toBeGreaterThan(0);
    expect(screen.getAllByText('E → C').length).toBeGreaterThan(0);
    expect(screen.getAllByText(/not an EPC re-assessment/).length).toBeGreaterThan(0);
  });

  it('shows bills at the price cap, grants, payback and the illustrative loan from the engine', async () => {
    await openHome(HOME_A);
    const money = document.querySelector('.money-panel') as HTMLElement;
    expect(within(money).getByText('£3,023 → £2,633')).toBeInTheDocument();
    expect(within(money).getByText('£16,537')).toBeInTheDocument();
    expect(within(money).getByText(/after £7,500 of grants \(from £24,037\)/)).toBeInTheDocument();
    expect(within(money).getByText('42 years')).toBeInTheDocument();
    expect(within(money).getByText(/Not a Lloyds product, rate or offer/)).toBeInTheDocument();
    expect(within(money).getByRole('table')).toHaveTextContent(/Carbon saving/);
  });

  it('recalculates a what-if: removing a measure gives a new confirmed scenario everywhere', async () => {
    await openHome(HOME_A);
    const before = snapshotResult(HOME_A).scenario_id.slice(0, 8);
    expect(screen.getAllByText(before).length).toBeGreaterThan(0);

    await userEvent.click(screen.getByRole('button', { name: 'Remove Solar PV from the scenario' }));
    // (the transient "recalculating" state is asserted in scenarioLab.test.tsx with controlled timing)
    await screen.findByText('What changed', {}, T);

    const after = snapshotResult(HOME_A, 'default', 'cavity_wall+double_glazing+heat_pump+smart_thermostat').scenario_id.slice(0, 8);
    await waitFor(() => expect(screen.getAllByText(after).length).toBeGreaterThanOrEqual(3), T); // dock, explanation, audit
    expect(screen.queryAllByText(before).filter((n) => n.closest('.dock'))).toHaveLength(0);
    expect(screen.getAllByText('Removed Solar PV').length).toBeGreaterThan(0);
    expect(screen.getByText(/All three featured picks are the same/)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Add Solar PV to the scenario' })).toBeInTheDocument();
  });

  it('loads a featured plan into the lab and recalculates', async () => {
    await openHome(HOME_A);
    const studio = document.getElementById('studio')!;
    await userEvent.click(within(studio).getAllByRole('button', { name: /Load into the lab/ })[0]);
    await waitFor(() => expect(screen.getAllByText('This is the confirmed scenario').length).toBeGreaterThan(0), T);
    const cavity = snapshotResult(HOME_A, 'default', 'cavity_wall').scenario_id.slice(0, 8);
    await waitFor(() => expect(screen.getAllByText(cavity).length).toBeGreaterThan(0), T);
  });

  it('uses a meter reading as a user-provided baseline (preset in the snapshot)', async () => {
    await openHome(HOME_A);
    await userEvent.click(screen.getByRole('button', { name: 'Fill it in' }));
    await userEvent.click(screen.getByRole('button', { name: 'Recalculate with my reading' }));
    await screen.findByText('Energy use comes from your meter reading.', {}, T);
    expect(screen.getAllByText('Your reading').length).toBeGreaterThan(0);
  });

  it('keeps the last confirmed scenario when a change cannot be calculated', async () => {
    await openHome(HOME_A);
    const id = snapshotResult(HOME_A).scenario_id.slice(0, 8);
    await userEvent.type(screen.getByLabelText('Gas, kWh per year'), '12345');
    await userEvent.click(screen.getByRole('button', { name: 'Recalculate with my reading' }));
    expect(await screen.findByText('Not in the offline snapshot', {}, T)).toBeInTheDocument();
    expect(screen.getByText(/Couldn’t update. You’re seeing the previous numbers/)).toBeInTheDocument();
    expect(screen.getAllByText(id).length).toBeGreaterThan(0);
    await userEvent.click(screen.getByRole('button', { name: 'Discard this change' }));
    await waitFor(() => expect(screen.queryByText('Not in the offline snapshot')).not.toBeInTheDocument());
  });

  it('validates the meter reading form', async () => {
    await openHome(HOME_A);
    await userEvent.type(screen.getByLabelText('Gas, kWh per year'), 'lots');
    await userEvent.click(screen.getByRole('button', { name: 'Recalculate with my reading' }));
    expect(screen.getByRole('alert')).toHaveTextContent(/Enter annual kWh as a number/);
  });

  it('opens “Why this number?” with inputs, provenance and the scenario id', async () => {
    await openHome(HOME_A);
    await userEvent.click(screen.getByRole('button', { name: /Why this score\?/ }));
    const dialog = await screen.findByRole('dialog', { hidden: true });
    expect(within(dialog).getByText('Inputs used')).toBeInTheDocument();
    expect(within(dialog).getByText('Validation status')).toBeInTheDocument();
    expect(within(dialog).getAllByText('Observed').length).toBeGreaterThan(0);
  });
});

describe('My Home: demo homes B and C', () => {
  it('B (flat): loft and solar are not suitable, with reasons, and cannot be added', async () => {
    await openHome(HOME_B);
    expect(screen.getByText('Another dwelling is above this home, so there is no loft to insulate.')).toBeInTheDocument();
    expect(screen.getAllByText('Not suitable').length).toBeGreaterThanOrEqual(5);
    expect(screen.getByRole('button', { name: 'Add Loft insulation to the scenario' })).toBeDisabled();
    // electric heating (D16): the thermostat and heat pump now have estimated savings, so packages exist
    expect(screen.queryByText(/no package can be estimated for this home/)).not.toBeInTheDocument();
  });

  it('C (missing data): score unavailable, never zero; every measure needs verification', async () => {
    await openHome(HOME_C);
    expect(screen.getByText(/The Green Home Score is unavailable: only 1\/7 parts are recorded/)).toBeInTheDocument();
    expect(screen.getAllByText('Needs verification')).toHaveLength(7);
    expect(screen.getAllByText(/^Missing:/).length).toBe(7);
    expect(screen.getByText(/Energy breakdown unavailable/)).toBeInTheDocument();
    expect(screen.queryByText('0 kWh/yr')).not.toBeInTheDocument();
    expect(screen.getAllByText(/baseline unavailable: no packages estimated/).length).toBeGreaterThan(0);
  });
});

describe('explanations stay bound to the scenario and work without the LLM', () => {
  const llmUp = { llmHealth: async () => ({ enabled: true, engine_configured: true, providers: [] }) };

  it('uses the deterministic template when the LLM is not available', async () => {
    await openHome(HOME_A);
    expect(screen.getByText('Deterministic template')).toBeInTheDocument();
    expect(screen.getByText(/Estimated grid electricity use rises by/)).toBeInTheDocument();
  });

  it('shows the LLM explanation when it matches the scenario id', async () => {
    const id = snapshotResult(HOME_A).scenario_id;
    const llm: Explanation = { scenario_id: id, sections: [{ id: 'score', title: 'Your Green Home Score', claims: [{ type: 'statement', text: 'LLM-written sentence.', keys: [], measures: [], spans: [] }] }], source: 'llm', provider: 'groq', model: 'm' };
    await openHome(HOME_A, withLlm({ ...llmUp, explain: async () => llm }));
    expect(await screen.findByText('LLM-written sentence.', {}, T)).toBeInTheDocument();
    expect(screen.getByText(/Written by the LLM/)).toBeInTheDocument();
  });

  it('falls back to the template when the LLM fails or answers for another scenario', async () => {
    await openHome(HOME_A, withLlm({ ...llmUp, explain: async () => { throw new ApiError('stale', 'The explanation belongs to a different scenario.'); } }));
    expect(await screen.findByText(/LLM explanation failed/, {}, T)).toBeInTheDocument();
    expect(screen.getByText('Deterministic template')).toBeInTheDocument();
  });

  it('template mode switch forces the template', async () => {
    const id = snapshotResult(HOME_A).scenario_id;
    await openHome(HOME_A, withLlm({ ...llmUp, explain: async () => ({ scenario_id: id, sections: [], source: 'llm' }) }));
    await userEvent.click(screen.getByLabelText('Template mode'));
    expect(await screen.findByText('Template mode is on.')).toBeInTheDocument();
  });
});

describe('navigation and supporting pages', () => {
  it('mobile menu toggle exposes its state', async () => {
    await openHome(HOME_A);
    const btn = screen.getByRole('button', { name: 'Open menu' });
    expect(btn).toHaveAttribute('aria-expanded', 'false');
    fireEvent.click(btn);
    expect(screen.getByRole('button', { name: 'Close menu' })).toHaveAttribute('aria-expanded', 'true');
  });

  it('Homes Needing Help lists engine portfolio rows, keeps unavailable potential as unavailable, and links to My Home', async () => {
    stubFixtureFetch();
    const real = readFixture('portfolio.json') as Portfolio;
    // test-only row: a flagged home whose potential the engine could not estimate
    const extra = { ...real.homes[0], home_id: 'TEST-NULL', display_label: 'Test home with no baseline', improvement_potential_pct: null, improvement_potential_status: 'unavailable', improvement_potential_reason: 'baseline_gas_unavailable', carbon_saving_kg: null, gas_saving_kwh: null, elec_saving_kwh: null };
    const t: Transport = { ...createFixtureTransport('/fixtures'), portfolio: async () => ({ ...real, homes: [...real.homes, extra] }) };
    renderApp('/homes-needing-help', t);
    expect(await screen.findByText(/not.*a lending, eligibility or credit decision/i, {}, T)).toBeInTheDocument();
    expect(await screen.findByText('1967-1975 house, YO31', {}, T)).toBeInTheDocument();
    expect(screen.getByText(/Unavailable: baseline_gas_unavailable/)).toBeInTheDocument();
    expect(screen.getByRole('link', { name: /Open 1967-1975 house, YO31 in My Home/ })).toHaveAttribute('href', `/home/${HOME_A}`);
    await userEvent.selectOptions(screen.getByLabelText('Improvement potential'), 'unavailable');
    expect(screen.queryByText('1967-1975 house, YO31')).not.toBeInTheDocument();
  });

  it('Method & Evidence shows engine evidence and marks unfinished evaluations as pending', async () => {
    stubFixtureFetch();
    renderApp('/method');
    expect(await screen.findByRole('heading', { name: 'Method & evidence' }, T)).toBeInTheDocument();
    expect(await screen.findByRole('heading', { name: 'Fixed checklist vs greedy vs full package search' }, T)).toBeInTheDocument();
    expect(screen.getAllByText('Evaluation pending').length).toBeGreaterThanOrEqual(2);
    expect(screen.getByText('Cavity Wall Insulation and Loft Insulation')).toBeInTheDocument();
  });
});
