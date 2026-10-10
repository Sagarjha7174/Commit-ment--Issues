/**
 * Explanation for the confirmed scenario. Uses the LLM layer (POST /llm/explain) when it is available; the whole engine
 * request is sent, so the server explains exactly the scenario on screen (assumptions and readings included).
 * Otherwise, or on any failure, the deterministic template. An explanation is only ever shown for the scenario ID it
 * was generated for.
 */
import { useQuery } from '@tanstack/react-query';
import type { Explanation, ScenarioResult } from '../api/schema';
import { useLlmHealth, useTransport } from '../api/queries';
import { toApiError } from '../api/errors';
import { templateExplanation } from '../utils/explainTemplate';

export interface ExplanationState {
  explanation: Explanation | null;
  /** LLM text is being generated; the template is shown meanwhile. */
  loading: boolean;
  llmAvailable: boolean;
  /** Why the template is shown instead of the LLM, if it is. */
  reason: string | null;
}

/** Why the LLM cannot explain this scenario, or null. The routes take the full engine request, so nothing blocks it. */
export function llmCanExplain(_r: ScenarioResult): string | null {
  return null;
}

export function useExplanation(result: ScenarioResult | null, templateMode: boolean): ExplanationState {
  const t = useTransport();
  const health = useLlmHealth();
  const llmAvailable = !!health.data?.enabled && !!health.data?.engine_configured;
  const blocker = result ? llmCanExplain(result) : null;
  const useLlm = !!result && llmAvailable && !templateMode && !blocker;

  const q = useQuery({
    queryKey: [t.kind, 'explain', result?.scenario_id],
    enabled: useLlm,
    queryFn: ({ signal }) => t.explain({
      homeId: result!.home.home_id, measures: result!.request.measures, scenarioId: result!.scenario_id, templateMode: false,
      request: result!.request,
    }, signal),
    retry: false,
    staleTime: Infinity,
  });

  if (!result) return { explanation: null, loading: false, llmAvailable, reason: null };

  let reason: string | null = null;
  if (templateMode) reason = 'Template mode is on.';
  else if (!llmAvailable) reason = health.error ? toApiError(health.error).message : health.isPending ? 'Checking the LLM service…' : 'The LLM service is disabled or has no engine configured.';
  else if (blocker) reason = blocker;
  else if (q.error) reason = `LLM explanation failed (${toApiError(q.error).message}); deterministic template shown.`;

  if (useLlm && q.data && q.data.scenario_id === result.scenario_id) {
    return { explanation: q.data, loading: false, llmAvailable, reason: null };
  }
  return {
    explanation: templateExplanation(result, reason),
    loading: useLlm && q.isFetching,
    llmAvailable,
    reason: reason ?? (useLlm && q.isFetching ? 'Generating the LLM explanation; template shown meanwhile.' : null),
  };
}
