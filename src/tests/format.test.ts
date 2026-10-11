import { describe, expect, it } from 'vitest';
import { barPct, fmtGbp, fmtKg, fmtKwh, fmtPct, fmtSigned, missingText, savingDirection } from '../utils/format';
import { packageIdFor, packageName, prettyText, tierOf } from '../utils/labels';

describe('units and sign conventions', () => {
  it('formats energy, carbon, money and percentages with units', () => {
    expect(fmtKwh(20957.358)).toBe('20,957 kWh/yr');
    expect(fmtKg(3291.69)).toBe('3,292 kg CO₂e/yr');
    expect(fmtGbp(17500)).toBe('£17,500');
    expect(fmtPct(68.08, 1)).toBe('68.1%');
  });

  it('keeps negative savings negative with a real minus sign', () => {
    expect(fmtSigned(-3675.19, 'kWh/yr')).toBe('−3,675 kWh/yr');
    expect(fmtSigned(20957, 'kWh/yr')).toBe('+20,957 kWh/yr');
    expect(fmtKwh(-5937.9)).toBe('−5,938 kWh/yr');
  });

  it('classifies direction by the engine convention (saving > 0 = reduction)', () => {
    expect(savingDirection(-3675)).toBe('increase');
    expect(savingDirection(694)).toBe('reduction');
    expect(savingDirection(0)).toBe('none');
    expect(savingDirection(null)).toBe('unknown');
  });

  it('never turns a missing value into zero', () => {
    expect(fmtKwh(null, 'unavailable')).toBe('Unavailable');
    expect(fmtKg(null, 'not_estimated')).toBe('Not estimated');
    expect(fmtSigned(undefined, 'kWh', 'blocked')).toBe('Blocked (infeasible)');
    expect(fmtGbp(null)).toBe('Unavailable');
    expect(missingText(undefined)).toBe('Unavailable');
    expect(barPct(null, 100)).toBe(0);
  });
});

describe('labels', () => {
  it('maps provenance to knowledge tiers', () => {
    expect(tierOf('observed')).toBe('known');
    expect(tierOf('user_provided')).toBe('known');
    expect(tierOf('population_benchmark')).toBe('estimated');
    expect(tierOf('modelled')).toBe('estimated');
    expect(tierOf('unavailable')).toBe('unknown');
    expect(tierOf(null)).toBe('unknown');
  });

  it('round-trips engine package ids', () => {
    expect(packageIdFor(['heat_pump', 'cavity_wall'])).toBe('cavity_wall+heat_pump');
    expect(packageIdFor([])).toBe('none');
    expect(packageName('cavity_wall+heat_pump')).toBe('Cavity-wall insulation + Air-source heat pump');
  });

  it('replaces raw measure ids in engine text', () => {
    expect(prettyText('double_glazing: impact not validated')).toBe('Double glazing: impact not validated');
  });
});
