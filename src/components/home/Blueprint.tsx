/**
 * Retrofit Blueprint: an architectural elevation of the home with one numbered callout per measure.
 * Drawn from engine fields only (property type, feasibility, selected measures). Each callout is a real
 * control: it toggles the measure in the Scenario Lab, or explains why it is not available.
 */
import type { KeyboardEvent } from 'react';
import { MEASURE_ORDER, type FeasibilityItem, type MeasureId } from '../../api/schema';
import { MEASURE_SHORT } from '../../utils/labels';
import { calloutState, type CalloutState } from './blueprintState';
import './blueprint.css';

interface Props {
  isFlat: boolean;
  feasibility: FeasibilityItem[];
  selected: ReadonlySet<string>;   // draft selection
  applied: ReadonlySet<string>;    // confirmed (engine) selection
  onToggle(m: MeasureId): void;
  onExplain(m: MeasureId): void;
}

const STATE_TEXT: Record<CalloutState, string> = {
  selected: 'in the confirmed plan',
  'pending-add': 'being added (recalculating)',
  'pending-remove': 'being removed (recalculating)',
  available: 'feasible, not selected',
  verify: 'needs verification, not selected',
  blocked: 'not suitable for this home',
};

const HOUSE_POS: Record<MeasureId, [number, number]> = {
  loft_insulation: [240, 108], solar_pv: [318, 82], cavity_wall: [114, 208], solid_wall: [366, 208],
  double_glazing: [165, 178], smart_thermostat: [282, 182], heat_pump: [428, 236],
};
const FLAT_POS: Record<MeasureId, [number, number]> = {
  loft_insulation: [240, 128], solar_pv: [300, 46], cavity_wall: [126, 166], solid_wall: [354, 166],
  double_glazing: [180, 164], smart_thermostat: [292, 168], heat_pump: [428, 246],
};

function House({ on }: { on: (m: MeasureId) => boolean }) {
  return (
    <g className="bp-structure">
      <line x1="20" y1="270" x2="470" y2="270" className="bp-ground" />
      <polygon points="92,140 240,48 388,140" className="bp-roof" />
      <polygon points="122,134 240,62 358,134" className="bp-void" />
      {on('loft_insulation') && <rect x="130" y="124" width="220" height="10" className="bp-insul" />}
      {on('solar_pv') && (
        <g className="bp-pv">
          {[0, 1, 2].map((i) => {
            const x = 262 + i * 34;
            const y = 62 + i * 21;
            return <polygon key={i} points={`${x},${y} ${x + 30},${y + 19} ${x + 30},${y + 33} ${x},${y + 14}`} />;
          })}
        </g>
      )}
      <rect x="110" y="140" width="260" height="130" className="bp-wall" />
      {/* wall build-ups: cavity detail left, solid masonry right */}
      <line x1="118" y1="142" x2="118" y2="268" className="bp-cavity" />
      {on('cavity_wall') && <rect x="111" y="142" width="7" height="126" className="bp-insul" />}
      {on('solid_wall') && <rect x="370" y="140" width="8" height="130" className="bp-insul" />}
      {[[140, 158], [290, 158], [140, 212], [290, 212]].map(([x, y]) => (
        <g key={`${x}${y}`} className="bp-window">
          <rect x={x} y={y} width="50" height="40" />
          <line x1={x + 25} y1={y} x2={x + 25} y2={y + 40} />
          {on('double_glazing') && <rect x={x + 3} y={y + 3} width="44" height="34" className="bp-glaze2" />}
        </g>
      ))}
      <rect x="218" y="200" width="44" height="70" className="bp-door" />
      {on('smart_thermostat') && <g className="bp-stat"><rect x="270" y="170" width="24" height="24" rx="5" /><circle cx="282" cy="182" r="5" /></g>}
      <g className={on('heat_pump') ? 'bp-hp' : 'bp-hp bp-ghost'}>
        <rect x="398" y="226" width="60" height="44" rx="3" />
        <circle cx="420" cy="248" r="13" />
        <line x1="398" y1="244" x2="370" y2="244" />
      </g>
    </g>
  );
}

function Flat({ on }: { on: (m: MeasureId) => boolean }) {
  return (
    <g className="bp-structure">
      <line x1="20" y1="270" x2="470" y2="270" className="bp-ground" />
      <rect x="120" y="58" width="240" height="212" className="bp-wall" />
      <rect x="114" y="52" width="252" height="8" className="bp-roof" />
      {on('solar_pv') && <g className="bp-pv"><rect x="270" y="38" width="36" height="12" /><rect x="312" y="38" width="36" height="12" /></g>}
      <rect x="120" y="130" width="240" height="70" className="bp-unit" />
      <text x="128" y="146" className="bp-tag">THIS HOME</text>
      <text x="128" y="78" className="bp-tag bp-tag-muted">DWELLING ABOVE</text>
      {[80, 150, 220].map((y) => [150, 300].map((x) => (
        <g key={`${x}${y}`} className="bp-window">
          <rect x={x} y={y} width="40" height="34" />
          <line x1={x + 20} y1={y} x2={x + 20} y2={y + 34} />
          {y === 150 && on('double_glazing') && <rect x={x + 3} y={y + 3} width="34" height="28" className="bp-glaze2" />}
        </g>
      )))}
      {on('cavity_wall') && <rect x="120" y="130" width="6" height="70" className="bp-insul" />}
      {on('solid_wall') && <rect x="360" y="130" width="7" height="70" className="bp-insul" />}
      {on('smart_thermostat') && <g className="bp-stat"><rect x="280" y="156" width="24" height="24" rx="5" /><circle cx="292" cy="168" r="5" /></g>}
      <rect x="220" y="226" width="40" height="44" className="bp-door" />
      <g className={on('heat_pump') ? 'bp-hp' : 'bp-hp bp-ghost'}>
        <rect x="398" y="236" width="56" height="34" rx="3" />
        <circle cx="418" cy="253" r="11" />
      </g>
    </g>
  );
}

export function Blueprint({ isFlat, feasibility, selected, applied, onToggle, onExplain }: Props) {
  const fmap = new Map(feasibility.map((f) => [f.measure as string, f]));
  const pos = isFlat ? FLAT_POS : HOUSE_POS;
  const on = (m: MeasureId) => selected.has(m) && fmap.get(m)?.state !== 'infeasible';

  const act = (m: MeasureId, st: CalloutState) => (st === 'blocked' ? onExplain(m) : onToggle(m));
  const key = (m: MeasureId, st: CalloutState) => (e: KeyboardEvent) => {
    if (e.key === 'Enter' || e.key === ' ') {
      e.preventDefault();
      act(m, st);
    }
  };

  return (
    <figure className="blueprint">
      <svg viewBox="0 0 480 290" role="group" aria-label="Retrofit blueprint: numbered callouts toggle each measure">
        <defs>
          <pattern id="bp-hatch" width="6" height="6" patternUnits="userSpaceOnUse" patternTransform="rotate(45)">
            <line x1="0" y1="0" x2="0" y2="6" stroke="var(--gold)" strokeWidth="3" />
          </pattern>
          <pattern id="bp-grid" width="16" height="16" patternUnits="userSpaceOnUse">
            <path d="M16 0H0V16" fill="none" stroke="var(--line)" strokeWidth="0.6" />
          </pattern>
        </defs>
        <rect width="480" height="290" fill="url(#bp-grid)" />
        {isFlat ? <Flat on={on} /> : <House on={on} />}
        {MEASURE_ORDER.map((m, i) => {
          const f = fmap.get(m);
          const st = calloutState(m, f, selected, applied);
          const [x, y] = pos[m];
          const label = `${i + 1}. ${MEASURE_SHORT[m]}: ${STATE_TEXT[st]}${st === 'blocked' ? `. ${f?.reason_text ?? ''} Press to see why.` : '. Press to toggle.'}`;
          return (
            <g
              key={m}
              className={`bp-callout bp-${st}`}
              transform={`translate(${x} ${y})`}
              role="button"
              tabIndex={0}
              aria-label={label}
              aria-pressed={st === 'blocked' ? undefined : selected.has(m)}
              onClick={() => act(m, st)}
              onKeyDown={key(m, st)}
            >
              <title>{label}</title>
              <circle r="12" />
              <text y="4.5" textAnchor="middle">{st === 'blocked' ? '×' : i + 1}</text>
            </g>
          );
        })}
      </svg>
      <figcaption className="bp-legend">
        <span><i className="bp-dot bp-selected" /> In plan</span>
        <span><i className="bp-dot bp-pending-add" /> Pending</span>
        <span><i className="bp-dot bp-available" /> Feasible</span>
        <span><i className="bp-dot bp-verify" /> Needs a check</span>
        <span><i className="bp-dot bp-blocked" /> Not suitable</span>
      </figcaption>
    </figure>
  );
}
