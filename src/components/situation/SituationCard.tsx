/** Optional "Your situation" questions: one at a time, big buttons, skippable. */
import { useState } from 'react';
import { Check, ChevronLeft, Lock, X } from 'lucide-react';
import {
  BUDGET_CHOICES, CHANGE_TEXT, HORIZON_TEXT, PRIORITY_TEXT, ROLE_TEXT, situationSummary, useSituation,
  type Change, type Horizon, type Priority, type Role, type Situation,
} from '../../hooks/useSituation';
import './situation.css';

interface Step {
  key: string;
  question: string;
  why: string;
  options: { label: string; apply: Partial<Situation>; selected: (s: Situation) => boolean }[];
}

const STEPS: Step[] = [
  {
    key: 'role', question: 'How are you connected to this home?',
    why: 'Tenants usually need the landlord’s permission; flats need building approval for roofs and walls.',
    options: (Object.keys(ROLE_TEXT) as Role[]).map((r) => ({ label: ROLE_TEXT[r], apply: { role: r }, selected: (s) => s.role === r })),
  },
  {
    key: 'horizon', question: 'How long do you expect to stay?',
    why: 'Big permanent upgrades mostly help whoever lives there next if you move soon.',
    options: (Object.keys(HORIZON_TEXT) as Horizon[]).map((h) => ({ label: HORIZON_TEXT[h], apply: { horizon: h }, selected: (s) => s.horizon === h })),
  },
  {
    key: 'budget', question: 'How much could you spend now?',
    why: 'We mark which plans fit. Spending later, or paying monthly, is a different question we don’t judge.',
    options: [
      ...BUDGET_CHOICES.map((b) => ({ label: b.label, apply: { budgetGbp: b.value, budgetAnswered: true }, selected: (s: Situation) => s.budgetAnswered && s.budgetGbp === b.value })),
      { label: 'Prefer not to say', apply: { budgetGbp: null, budgetAnswered: false }, selected: (s: Situation) => !s.budgetAnswered },
    ],
  },
  {
    key: 'priority', question: 'What matters most to you?',
    why: 'The engine always offers three plans; we highlight the one that matches.',
    options: (Object.keys(PRIORITY_TEXT) as Priority[]).map((p) => ({ label: PRIORITY_TEXT[p], apply: { priority: p }, selected: (s) => s.priority === p })),
  },
  {
    key: 'change', question: 'Do you expect any change at home?',
    why: 'More or fewer people changes how much energy is used. We can re-run the engine for that.',
    options: (Object.keys(CHANGE_TEXT) as Change[]).map((c) => ({ label: CHANGE_TEXT[c], apply: { change: c }, selected: (s) => s.change === c })),
  },
];

export function SituationCard({ onClose }: { onClose?: () => void }) {
  const [s, update] = useSituation();
  const [i, setI] = useState(0);
  const step = STEPS[i];
  const finish = () => { update({ done: true }); onClose?.(); };

  if (i >= STEPS.length) {
    return (
      <section className="situation panel" aria-labelledby="sit-title">
        <div className="situation-top">
          <h2 id="sit-title" className="situation-title"><Check size={18} aria-hidden="true" /> Thanks — results are now tailored</h2>
        </div>
        <p className="small">{situationSummary(s)}</p>
        <p className="xsmall muted"><Lock size={12} aria-hidden="true" /> Saved only in this browser. Your answers change how results are shown, never the engine’s numbers.</p>
        <div className="row"><button className="btn" onClick={finish}>Done</button><button className="btn btn-ghost" onClick={() => setI(0)}>Change answers</button></div>
      </section>
    );
  }

  return (
    <section className="situation panel" aria-labelledby="sit-title">
      <div className="situation-top">
        <p className="kicker">Your situation · question {i + 1} of {STEPS.length} · optional</p>
        <button className="btn btn-sm btn-ghost" onClick={finish} aria-label="Skip these questions"><X size={14} aria-hidden="true" /> Skip</button>
      </div>
      <h2 id="sit-title" className="situation-title">{step.question}</h2>
      <p className="small muted">{step.why}</p>
      <div className="choice-grid" role="group" aria-label={step.question}>
        {step.options.map((o) => (
          <button key={o.label} type="button" className="choice" aria-pressed={o.selected(s)} onClick={() => { update(o.apply); setI(i + 1); }}>
            {o.label}
          </button>
        ))}
      </div>
      <div className="row situation-nav">
        <button className="btn btn-sm btn-ghost" disabled={i === 0} onClick={() => setI(i - 1)}><ChevronLeft size={14} aria-hidden="true" /> Back</button>
        <span className="progress" aria-hidden="true">{STEPS.map((x, k) => <i key={x.key} className={k <= i ? 'on' : ''} />)}</span>
        <button className="btn btn-sm btn-link" onClick={() => setI(i + 1)}>Not now</button>
      </div>
      <p className="xsmall muted"><Lock size={12} aria-hidden="true" /> We never ask for income, employer or bank details. Answers stay in this browser.</p>
    </section>
  );
}
