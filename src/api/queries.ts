/** Server state: read-only data cached by TanStack Query, fetched through the context Transport. */
import { useQuery } from '@tanstack/react-query';
import { loadManifest, type BudgetSearchArgs, type PortfolioParams } from './transport';
import { ApiError } from './errors';
import { useTransport } from './transportContext';

export { useTransport };

const STATIC = { staleTime: Infinity, gcTime: Infinity } as const;
const noRetryOn = (kinds: ApiError['kind'][]) => (count: number, e: Error) =>
  !(e instanceof ApiError && kinds.includes(e.kind)) && count < 1;

export function useHealth() {
  const t = useTransport();
  return useQuery({ queryKey: [t.kind, 'health'], queryFn: ({ signal }) => t.health(signal), retry: false, staleTime: 30_000 });
}

export function useDemoHomes() {
  const t = useTransport();
  return useQuery({ queryKey: [t.kind, 'demo-homes'], queryFn: ({ signal }) => t.demoHomes(signal), ...STATIC, retry: noRetryOn(['validation', 'not_found']) });
}

export function useEvidence() {
  const t = useTransport();
  return useQuery({ queryKey: [t.kind, 'evidence'], queryFn: ({ signal }) => t.evidence(signal), ...STATIC, retry: noRetryOn(['validation', 'not_found']) });
}

export function usePortfolio(params: PortfolioParams) {
  const t = useTransport();
  return useQuery({
    queryKey: [t.kind, 'portfolio', params.top_n, params.split ?? null],
    queryFn: ({ signal }) => t.portfolio(params, signal),
    staleTime: 5 * 60_000,
    retry: noRetryOn(['validation', 'not_found']),
  });
}

/** LLM availability: true only when the LLM routes answer, the engine is wired and generation is enabled. */
export function useLlmHealth() {
  const t = useTransport();
  return useQuery({
    queryKey: [t.kind, 'llm-health'],
    queryFn: ({ signal }) => t.llmHealth(signal),
    retry: false,
    staleTime: 60_000,
  });
}

/** Offline snapshot manifest (fixtures mode only): which presets the snapshot can answer. */
export function useSnapshotManifest() {
  const t = useTransport();
  return useQuery({ queryKey: ['snapshot-manifest'], queryFn: () => loadManifest(), enabled: t.kind === 'fixtures', ...STATIC, retry: false });
}

/** The engine's package search re-run with a spending limit (null = no budget search). */
export function useBudgetSearch(args: BudgetSearchArgs | null) {
  const t = useTransport();
  return useQuery({
    queryKey: [t.kind, 'packages', args?.home_id, JSON.stringify(args?.assumptions ?? null), JSON.stringify(args?.user_reading ?? null), args?.budget_gbp],
    queryFn: ({ signal }) => t.packages(args!, signal),
    enabled: !!args,
    staleTime: Infinity,
    retry: false,
  });
}
