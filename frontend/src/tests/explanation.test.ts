/** Explanation colour follows good/bad for the homeowner; the browser template reports engine bills and finance. */
import { describe, expect, it } from 'vitest';
import { ScenarioResult } from '../api/schema';
import { spanTone } from '../utils/spanTone';
import { templateExplanation } from '../utils/explainTemplate';
import { HOME_A, HOME_C, snapshotResult } from './helpers';

const sp = (o: Record<string, unknown>) => ({ key: 'k', display: '1', status: 'available', provenance: null, ...o });

describe('span colour (D45)', () => {
  it('a rising score or EPC is good, rising energy use is bad', () => {
    expect(spanTone(sp({ direction: 'up', sentiment: 'good' }))).toBe('good');     // SAP / score up
    expect(spanTone(sp({ direction: 'increase', sentiment: 'bad' }))).toBe('bad');  // electricity up
    expect(spanTone(sp({ direction: 'reduction', sentiment: 'good' }))).toBe('good');
    expect(spanTone(sp({ direction: 'no change', sentiment: 'neutral' }))).toBe('none');
  });
  it('without a sentiment, up/down are not guessed; energy directions keep their meaning', () => {
    expect(spanTone(sp({ direction: 'up' }))).toBe('none');
    expect(spanTone(sp({ direction: 'increase' }))).toBe('bad');
    expect(spanTone(sp({ direction: 'reduction' }))).toBe('good');
  });
});

describe('browser template reports engine money figures', () => {
  const text = (homeId: string) => {
    const r = ScenarioResult.parse(snapshotResult(homeId));
    const e = templateExplanation(r, null);
    return { r, all: e.sections.flatMap((s) => s.claims.map((c) => c.text)).join(' '), e };
  };
  it('home A: bill change, grants, payback and the illustrative loan, never "not estimated"', () => {
    const { r, all } = text(HOME_A);
    expect(r.bills?.status).toBe('ok');
    expect(all).not.toMatch(/Bills in pounds are not estimated/);
    expect(all).toMatch(/annual bill (falls|rises) by £/);
    expect(all).toMatch(/Simple payback .* years/);
    expect(all).toMatch(/not a Lloyds product/);
  });
  it('home C: bills not estimated is said, never shown as £0', () => {
    const { all } = text(HOME_C);
    expect(all).not.toMatch(/£0\b/);
  });
});
