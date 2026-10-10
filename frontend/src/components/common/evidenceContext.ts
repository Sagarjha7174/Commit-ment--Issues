import { createContext, useContext } from 'react';
import type { EvidenceEntry } from '../../utils/evidence';

export const EvidenceCtx = createContext<(e: EvidenceEntry) => void>(() => {});

/** Opens the "Why this number?" drawer with an entry built from the scenario that produced the number. */
export function useOpenEvidence() {
  return useContext(EvidenceCtx);
}
