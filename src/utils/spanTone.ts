import type { ExplanationClaim } from '../api/schema';

export type SpanT = ExplanationClaim['spans'][number];

/** Colour follows what is beneficial or adverse for the homeowner (engine-provided sentiment), not purely arithmetic direction:
 * a score or EPC improving is beneficial, energy bills increasing is adverse. Without a sentiment, only
 * energy/carbon/bill directions are coloured; "up"/"down" stay neutral rather than guessed. */
export function spanTone(s: SpanT): 'good' | 'bad' | 'none' {
  if (s.sentiment === 'good' || s.sentiment === 'bad') return s.sentiment;
  if (s.sentiment === 'neutral') return 'none';
  return s.direction === 'reduction' ? 'good' : s.direction === 'increase' ? 'bad' : 'none';
}
