import type { ExplanationClaim } from '../api/schema';

export type SpanT = ExplanationClaim['spans'][number];

/** Colour follows what is good or bad for the homeowner (engine-provided sentiment), not the arithmetic direction:
 * a score or EPC going up is good, energy use or a bill going up is bad. Without a sentiment (older server), only an
 * energy/carbon/bill direction is coloured; "up"/"down" stay neutral rather than guessed. */
export function spanTone(s: SpanT): 'good' | 'bad' | 'none' {
  if (s.sentiment === 'good' || s.sentiment === 'bad') return s.sentiment;
  if (s.sentiment === 'neutral') return 'none';
  return s.direction === 'reduction' ? 'good' : s.direction === 'increase' ? 'bad' : 'none';
}
