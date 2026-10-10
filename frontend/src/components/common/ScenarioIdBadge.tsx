import { useState } from 'react';
import { Check, Copy } from 'lucide-react';
import { shortId } from '../../utils/format';

/** Short scenario id with the full SHA-256 available on hover and copy. */
export function ScenarioIdBadge({ id, label = 'Scenario' }: { id: string | null | undefined; label?: string }) {
  const [copied, setCopied] = useState(false);
  if (!id) return <span className="sid sid-empty">{label} —</span>;
  const copy = async () => {
    try {
      await navigator.clipboard.writeText(id);
      setCopied(true);
      setTimeout(() => setCopied(false), 1400);
    } catch {
      setCopied(false);
    }
  };
  return (
    <span className="sid" title={`Full scenario ID: ${id}`}>
      <span className="sid-label">{label}</span>
      <code className="mono">{shortId(id)}</code>
      <button type="button" onClick={copy} aria-label={`Copy full scenario ID ${id}`} className="sid-copy">
        {copied ? <Check size={12} aria-hidden="true" /> : <Copy size={12} aria-hidden="true" />}
      </button>
      <span className="sr-only" aria-live="polite">{copied ? 'Copied' : ''}</span>
    </span>
  );
}
