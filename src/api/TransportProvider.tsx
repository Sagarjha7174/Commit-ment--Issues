import { useMemo, type ReactNode } from 'react';
import { createTransport, type Transport } from './transport';
import { useDataMode } from './config';
import { TransportContext } from './transportContext';

/** Provides the transport for the current data mode (or an injected one in tests). */
export function TransportProvider({ transport, children }: { transport?: Transport; children: ReactNode }) {
  const mode = useDataMode();
  const value = useMemo(() => transport ?? createTransport(mode), [transport, mode]);
  return <TransportContext.Provider value={value}>{children}</TransportContext.Provider>;
}
