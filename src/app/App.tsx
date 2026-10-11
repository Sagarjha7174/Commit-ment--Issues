import { lazy, Suspense } from 'react';
import { BrowserRouter, Navigate, Route, Routes } from 'react-router-dom';
import { QueryClientProvider, type QueryClient } from '@tanstack/react-query';
import { makeQueryClient } from './queryClient';
import { TransportProvider } from '../api/TransportProvider';
import type { Transport } from '../api/transport';
import { AppShell } from '../components/layout/AppShell';
import { EvidenceProvider } from '../components/common/EvidenceDrawer';
import { LoadingBlock } from '../components/common/States';
import MyHome from '../pages/MyHome';
import NotFound from '../pages/NotFound';

const HomesNeedingHelp = lazy(() => import('../pages/HomesNeedingHelp'));
const MethodEvidence = lazy(() => import('../pages/MethodEvidence'));

const defaultClient = makeQueryClient();

function Fallback() {
  return <div className="page" style={{ padding: '48px 0' }}><LoadingBlock label="Loading page" /></div>;
}

export function AppRoutes() {
  return (
    <AppShell>
      <Suspense fallback={<Fallback />}>
        <Routes>
          <Route path="/" element={<Navigate to="/home" replace />} />
          <Route path="/home" element={<MyHome />} />
          <Route path="/home/:homeId" element={<MyHome />} />
          <Route path="/homes-needing-help" element={<HomesNeedingHelp />} />
          <Route path="/method" element={<MethodEvidence />} />
          <Route path="/method-evidence" element={<Navigate to="/method" replace />} />
          <Route path="*" element={<NotFound />} />
        </Routes>
      </Suspense>
    </AppShell>
  );
}

export default function App({ client = defaultClient, transport }: { client?: QueryClient; transport?: Transport }) {
  return (
    <QueryClientProvider client={client}>
      <TransportProvider transport={transport}>
        <EvidenceProvider>
          <BrowserRouter>
            <AppRoutes />
          </BrowserRouter>
        </EvidenceProvider>
      </TransportProvider>
    </QueryClientProvider>
  );
}
