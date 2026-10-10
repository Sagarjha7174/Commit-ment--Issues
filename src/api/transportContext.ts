import { createContext, useContext } from 'react';
import type { Transport } from './transport';

export const TransportContext = createContext<Transport | null>(null);

export function useTransport(): Transport {
  const t = useContext(TransportContext);
  if (!t) throw new Error('useTransport must be used inside <TransportProvider>');
  return t;
}
