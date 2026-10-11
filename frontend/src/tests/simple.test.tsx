/** A simpler first view: questions after the home summary, background folded away, no raw keys on screen. */
import { screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it } from 'vitest';
import { DEFAULT_SITUATION, resetSituationForTests, setSituation } from '../hooks/useSituation';
import { SENSITIVITY_RUN_LABEL } from '../utils/labels';
import { HOME_A, renderApp, snapshotResult, stubFixtureFetch } from './helpers';

const T = { timeout: 5000 };
const QUESTION = { name: 'How are you connected to this home?' };

async function open(tab: string) {
  stubFixtureFetch();
  renderApp(`/home/${HOME_A}?tab=${tab}`);
  await screen.findByRole('tablist', { name: 'Steps' }, T);
}

beforeEach(() => {
  window.localStorage.clear();
  resetSituationForTests();
});

describe('a simpler first view', () => {
  it('asks the situation questions after the home summary, only on step 1', async () => {
    await open('home');
    const question = screen.getByRole('heading', QUESTION);
    const score = screen.getByText('44');
    expect(score.compareDocumentPosition(question) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    await userEvent.click(screen.getByRole('tab', { name: /Your options/ }));
    expect(screen.queryByRole('heading', QUESTION)).not.toBeInTheDocument();
  });

  it('the situation chip still opens the questions on any step', async () => {
    await open('options');
    expect(screen.queryByRole('heading', QUESTION)).not.toBeInTheDocument();
    await userEvent.click(screen.getByRole('button', { name: /Edit your situation/ }));
    expect(screen.getByRole('heading', QUESTION)).toBeInTheDocument();
  });

  it('shows three plan checks and folds the other three away', async () => {
    setSituation({ ...DEFAULT_SITUATION, done: true });
    await open('plan');
    const more = screen.getByText(/^3 more checks/).closest('details')!;
    expect(more.open).toBe(false);
    expect(more).toHaveTextContent('What if things change?');
    expect(screen.getByText('Can I afford it now?').closest('details')).toBeNull();
  });

  it('every sensitivity test the engine runs has a plain label', () => {
    const runs = (snapshotResult(HOME_A).sensitivity as { runs?: { name: string }[] } | null)?.runs ?? [];
    expect(runs.length).toBeGreaterThan(0);
    for (const run of runs) expect(SENSITIVITY_RUN_LABEL[run.name], run.name).toBeTruthy();
  });
});
