/** One error type for every API failure, so components can render a specific, honest state. */
export type ApiErrorKind =
  | 'network'       // backend unreachable / offline
  | 'http'          // unexpected HTTP status
  | 'not_found'     // unknown home or route
  | 'validation'    // response does not match the contract (or request rejected with 422)
  | 'unavailable'   // service exists in the contract but is not running (e.g. LLM)
  | 'fixture_miss'  // offline snapshot does not contain this request
  | 'stale'         // response belongs to a different scenario than the one requested
  | 'aborted';      // superseded by a newer request

export class ApiError extends Error {
  readonly kind: ApiErrorKind;
  readonly status?: number;
  readonly detail?: unknown;

  constructor(kind: ApiErrorKind, message: string, opts: { status?: number; detail?: unknown } = {}) {
    super(message);
    this.name = 'ApiError';
    this.kind = kind;
    this.status = opts.status;
    this.detail = opts.detail;
  }
}

export function toApiError(e: unknown): ApiError {
  if (e instanceof ApiError) return e;
  if (e instanceof DOMException && (e.name === 'AbortError' || e.name === 'TimeoutError')) {
    return e.name === 'TimeoutError'
      ? new ApiError('network', 'The request timed out.')
      : new ApiError('aborted', 'Request superseded by a newer change.');
  }
  if (e instanceof TypeError) return new ApiError('network', 'The backend could not be reached.');
  return new ApiError('http', e instanceof Error ? e.message : 'Unexpected error.');
}

export const ERROR_TITLES: Record<ApiErrorKind, string> = {
  network: 'Backend unreachable',
  http: 'The backend returned an error',
  not_found: 'Not found',
  validation: 'Response did not match the scenario contract',
  unavailable: 'Service not available',
  fixture_miss: 'Not in the offline snapshot',
  stale: 'Out-of-date result discarded',
  aborted: 'Request superseded',
};
