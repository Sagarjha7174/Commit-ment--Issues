import type { ReactNode } from 'react';
import { KNOWLEDGE_TEXT, PROVENANCE_INFO, tierOf, type Knowledge } from '../../utils/labels';
import type { Provenance } from '../../api/schema';
import { DIRECTION_TEXT, type Direction } from '../../utils/format';
import { ArrowDownRight, ArrowUpRight, Minus } from 'lucide-react';

export function KnowledgeMark({ tier }: { tier: Knowledge }) {
  return <span className={`k-mark k-${tier}`} aria-hidden="true" />;
}

/** Provenance label with its knowledge tier mark. The text is always present, so meaning never relies on colour. */
export function ProvenanceChip({ provenance, compact = false }: { provenance: string | null | undefined; compact?: boolean }) {
  const info = provenance ? PROVENANCE_INFO[provenance as Provenance] : undefined;
  const tier = tierOf(provenance);
  const label = info?.label ?? (provenance ? provenance.replace(/_/g, ' ') : 'Unknown');
  return (
    <span className="prov" title={info?.text}>
      <KnowledgeMark tier={tier} />
      {compact ? <span className="sr-only">{label}</span> : label}
    </span>
  );
}

/** A displayed value styled by what the system knows about it. */
export function Val({ children, provenance, tier }: { children: ReactNode; provenance?: string | null; tier?: Knowledge }) {
  const t = tier ?? tierOf(provenance);
  return <span className={`v-${t}`} title={KNOWLEDGE_TEXT[t].text}>{children}</span>;
}

export function KnowledgeLegend() {
  return (
    <ul className="k-legend" aria-label="How to read values">
      {(['known', 'estimated', 'unknown'] as const).map((t) => (
        <li key={t}>
          <KnowledgeMark tier={t} />
          <span><b>{KNOWLEDGE_TEXT[t].label}</b> <span className="muted">{KNOWLEDGE_TEXT[t].text}</span></span>
        </li>
      ))}
    </ul>
  );
}

export function DirectionTag({ direction, label }: { direction: Direction; label?: string }) {
  const Icon = direction === 'reduction' ? ArrowDownRight : direction === 'increase' ? ArrowUpRight : Minus;
  return (
    <span className={`dir dir-${direction}`}>
      <Icon size={14} aria-hidden="true" />
      {label ?? DIRECTION_TEXT[direction]}
    </span>
  );
}
