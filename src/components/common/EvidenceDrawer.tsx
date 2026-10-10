/** "Why this number?" — one drawer for every major result, filled from the scenario that produced the number. */
import { useCallback, useEffect, useRef, useState, type ReactNode } from 'react';
import { HelpCircle, X } from 'lucide-react';
import type { EvidenceEntry } from '../../utils/evidence';
import { fmtDate } from '../../utils/format';
import { DirectionTag, ProvenanceChip } from './Knowledge';
import { ScenarioIdBadge } from './ScenarioIdBadge';
import { EvidenceCtx as Ctx, useOpenEvidence } from './evidenceContext';
import './evidence.css';


export function EvidenceProvider({ children }: { children: ReactNode }) {
  const [entry, setEntry] = useState<EvidenceEntry | null>(null);
  const ref = useRef<HTMLDialogElement>(null);
  const returnFocus = useRef<HTMLElement | null>(null);

  const open = useCallback((e: EvidenceEntry) => {
    returnFocus.current = document.activeElement as HTMLElement | null;
    setEntry(e);
  }, []);

  useEffect(() => {
    const d = ref.current;
    if (!d || !entry) return;
    if (typeof d.showModal === 'function' && !d.open) d.showModal();
    else d.setAttribute('open', '');
  }, [entry]);

  const close = () => {
    const d = ref.current;
    if (d?.open && typeof d.close === 'function') d.close();
    setEntry(null);
    returnFocus.current?.focus?.();
  };

  return (
    <Ctx.Provider value={open}>
      {children}
      <dialog
        ref={ref}
        className="evidence"
        aria-labelledby="evidence-title"
        onClose={() => entry && close()}
        onClick={(ev) => { if (ev.target === ref.current) close(); }}
      >
        {entry && (
          <div className="evidence-inner">
            <header className="evidence-head">
              <p className="kicker">Why this number?</p>
              <button className="evidence-close" onClick={close} aria-label="Close evidence"><X size={20} /></button>
              <h2 id="evidence-title">{entry.title}</h2>
              <p className="evidence-value serif num">{entry.value}</p>
              {entry.direction && entry.direction !== 'unknown' && <DirectionTag direction={entry.direction} />}
              {entry.summary && <p className="lead">{entry.summary}</p>}
            </header>

            {entry.inputs.length > 0 && (
              <section>
                <h3>Inputs used</h3>
                <dl className="evidence-inputs">
                  {entry.inputs.map((i, k) => (
                    <div key={k}>
                      <dt>{i.label}</dt>
                      <dd><span className="num">{i.value}</span>{i.provenance && <ProvenanceChip provenance={i.provenance} />}</dd>
                    </div>
                  ))}
                </dl>
              </section>
            )}
            {entry.method && <section><h3>How it is calculated</h3><p>{entry.method}</p></section>}
            {entry.assumptions.length > 0 && <section><h3>Assumptions</h3><ul>{entry.assumptions.map((a) => <li key={a}>{a}</li>)}</ul></section>}
            <section>
              <h3>Missing information</h3>
              {entry.missing.length ? <ul>{entry.missing.map((a) => <li key={a}>{a}</li>)}</ul> : <p className="muted">None reported by the engine.</p>}
            </section>
            <section><h3>Validation status</h3><p>{entry.validation}</p></section>
            {entry.limitations.length > 0 && <section><h3>Limitations</h3><ul>{entry.limitations.map((a) => <li key={a}>{a}</li>)}</ul></section>}
            {entry.sources.length > 0 && <section><h3>Sources</h3><ul>{entry.sources.map((a) => <li key={a}>{a}</li>)}</ul></section>}
            <section className="evidence-meta">
              <h3>Scenario</h3>
              <ScenarioIdBadge id={entry.scenarioId} />
              <p className="xsmall muted">Calculated {fmtDate(entry.dataTimestamp)}</p>
              <p className="xsmall muted">{Object.entries(entry.versions).map(([k, v]) => `${k} ${v}`).join(' · ')}</p>
            </section>
          </div>
        )}
      </dialog>
    </Ctx.Provider>
  );
}

export function WhyButton({ build, label = 'Why?' }: { build: () => EvidenceEntry; label?: string }) {
  const open = useOpenEvidence();
  return (
    <button type="button" className="why" onClick={() => open(build())} aria-haspopup="dialog">
      <HelpCircle size={13} aria-hidden="true" />
      {label}
      <span className="sr-only"> Why this number?</span>
    </button>
  );
}
