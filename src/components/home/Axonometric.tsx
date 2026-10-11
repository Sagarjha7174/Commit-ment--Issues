/**
 * Retrofit sheet: an interactive 3D exploded architectural axonometric of the home, drawn in SVG from engine fields.
 *
 * Fully rotatable 360° via mouse drag, touch orbit, or keyboard arrows.
 * Geometry is shaped by real fields: property type, built form, glazing, existing solar, wall type, and floor area.
 * Every measure is an interactive control: clicking a 3D tag or orange index row toggles the measure in the scenario.
 */
import { useState, useRef, useCallback, type KeyboardEvent, type ReactNode, type PointerEvent, type WheelEvent } from 'react';
import { Compass, RotateCcw, ZoomIn, ZoomOut, Maximize2, Move3d } from 'lucide-react';
import { MEASURE_ORDER, type FeasibilityItem, type MeasureId, type PublicHome } from '../../api/schema';
import { fmtNumber, shortId } from '../../utils/format';
import { MEASURE_SHORT, measureLabel } from '../../utils/labels';
import { HabiMark } from '../brand/Habi';
import { calloutState, type CalloutState } from './blueprintState';
import './axonometric.css';

// ---------------------------------------------------------------- 3D projection & camera

type P3 = [number, number, number];
const U = 20; // px per model unit

interface Prim {
  k: 'poly' | 'line' | 'text';
  p: P3[];
  cls: string;
  text?: string;
  cull?: boolean;
}

const poly = (p: P3[], cls: string, cull = false): Prim => ({ k: 'poly', p, cls, cull });
const line = (a: P3, b: P3, cls: string): Prim => ({ k: 'line', p: [a, b], cls });
const text = (at: P3, t: string, cls = 'axo-label'): Prim => ({ k: 'text', p: [at], cls, text: t });

/** Project a 3D world coordinate to 2D screen coordinates around model center */
function project3D(
  [x, y, z]: P3,
  center: P3,
  yawDeg: number,
  pitchDeg: number,
  zoomScale: number,
  uScale = U,
): { p2: [number, number]; depth: number } {
  const dx = x - center[0];
  const dy = y - center[1];
  const dz = z - center[2];

  const yawRad = (yawDeg * Math.PI) / 180;
  const pitchRad = (pitchDeg * Math.PI) / 180;

  // Yaw rotation around vertical Z axis
  const cosY = Math.cos(yawRad);
  const sinY = Math.sin(yawRad);
  const x1 = dx * cosY - dy * sinY;
  const y1 = dx * sinY + dy * cosY;
  const z1 = dz;

  // Pitch rotation around screen horizontal axis
  const cosP = Math.cos(pitchRad);
  const sinP = Math.sin(pitchRad);
  const y2 = y1 * sinP - z1 * cosP;
  const z2 = y1 * cosP + z1 * sinP; // depth towards viewer

  const scale = 1.22 * uScale * zoomScale;
  return {
    p2: [x1 * scale, y2 * scale],
    depth: z2,
  };
}

/** 2D signed area of a screen polygon to determine front-facing vs back-facing (backface culling) */
function signedArea(pts: [number, number][]): number {
  let a = 0;
  for (let i = 0; i < pts.length; i++) {
    const j = (i + 1) % pts.length;
    a += pts[i][0] * pts[j][1] - pts[j][0] * pts[i][1];
  }
  return a * 0.5;
}

/** 6-sided solid box with outward-facing wound faces for clean 360° rotation */
function box(x0: number, x1: number, y0: number, y1: number, z0: number, z1: number, cls: string): Prim[] {
  return [
    poly([[x0, y0, z1], [x1, y0, z1], [x1, y1, z1], [x0, y1, z1]], `${cls} f-top`, true),
    poly([[x0, y1, z0], [x1, y1, z0], [x1, y0, z0], [x0, y0, z0]], `${cls} f-bottom`, true),
    poly([[x0, y1, z0], [x1, y1, z0], [x1, y1, z1], [x0, y1, z1]], `${cls} f-y`, true),
    poly([[x1, y0, z0], [x0, y0, z0], [x0, y0, z1], [x1, y0, z1]], `${cls} f-y-neg`, true),
    poly([[x1, y0, z0], [x1, y1, z0], [x1, y1, z1], [x1, y0, z1]], `${cls} f-x`, true),
    poly([[x0, y1, z0], [x0, y0, z0], [x0, y0, z1], [x0, y1, z1]], `${cls} f-x-neg`, true),
  ];
}

/** Dashed wireframe of a box (ghost neighbours / dwelling above). */
function ghostBox(x0: number, x1: number, y0: number, y1: number, z0: number, z1: number): Prim[] {
  const c: P3[] = [[x0, y0, z0], [x1, y0, z0], [x1, y1, z0], [x0, y1, z0], [x0, y0, z1], [x1, y0, z1], [x1, y1, z1], [x0, y1, z1]];
  const e = [[0, 1], [1, 2], [2, 3], [3, 0], [4, 5], [5, 6], [6, 7], [7, 4], [0, 4], [1, 5], [2, 6], [3, 7]];
  return e.map(([a, b]) => line(c[a], c[b], 'axo-ghost'));
}

// ---------------------------------------------------------------- data → drawing state

type Look = 'on' | 'pending' | 'ghost' | 'blocked';
function lookOf(st: CalloutState): Look {
  if (st === 'selected' || st === 'pending-add') return 'on';
  if (st === 'pending-remove') return 'pending';
  if (st === 'blocked') return 'blocked';
  return 'ghost';
}

type WallType = 'cavity-empty' | 'cavity-filled' | 'solid' | 'unknown';
function wallType(f: Map<string, FeasibilityItem>): WallType {
  const cav = f.get('cavity_wall');
  const sol = f.get('solid_wall');
  if (cav?.reason_code === 'wall_inputs_missing' || (!cav && !sol)) return 'unknown';
  if (cav?.reason_code === 'not_cavity_wall' || sol?.state === 'feasible') return 'solid';
  if (cav?.reason_code === 'already_insulated' || cav?.reason_code === 'built_2000_or_later') return 'cavity-filled';
  return 'cavity-empty';
}

interface Model {
  prims: Prim[];
  anchors: Record<MeasureId, P3>;
  tagOffset: Record<MeasureId, [number, number]>;
  detailAt: P3;
  center: P3;
}

const LEAF = 0.24;
const T = 0.68; // wall thickness

function wall(x0: number, x1: number, y0: number, y1: number, h: number, along: 'x' | 'y', wt: WallType, cavityLook: Look): Prim[] {
  const out = box(x0, x1, y0, y1, 0, h, 'axo-wall');
  const cavCls = wt === 'solid' ? 'cav-solid' : wt === 'cavity-filled' ? 'cav-filled' : wt === 'unknown' ? 'cav-unknown' : cavityLook === 'on' ? 'cav-on' : cavityLook === 'pending' ? 'cav-pending' : 'cav-empty';
  if (along === 'x') {
    const a = y0 + LEAF, b = y1 - LEAF;
    out.push(poly([[x0, a, h], [x1, a, h], [x1, b, h], [x0, b, h]], `axo-cavity ${cavCls}`));
  } else {
    const a = x0 + LEAF, b = x1 - LEAF;
    out.push(poly([[a, y0, h], [b, y0, h], [b, y1, h], [a, y1, h]], `axo-cavity ${cavCls}`));
  }
  return out;
}

function windowOn(plane: 'x' | 'y', at: number, from: number, to: number, z0: number, z1: number, glazing: 'single' | 'double' | 'unknown', upgradeLook: Look, arch = false): Prim[] {
  const P = (u: number, z: number): P3 => (plane === 'y' ? [u, at, z] : [at, u, z]);
  const out: Prim[] = [];
  const frame: P3[] = [P(from, z0), P(to, z0)];
  const top = arch ? 9 : 0;
  const r = (to - from) / 2;
  const zs = z1 - (arch ? r : 0);
  frame.push(P(to, zs));
  if (arch) for (let i = 1; i < top; i++) { const a = (Math.PI * i) / top; frame.push(P(from + r + r * Math.cos(a), zs + r * Math.sin(a))); }
  frame.push(P(from, zs));
  out.push(poly(frame, glazing === 'unknown' ? 'axo-window axo-unknown' : 'axo-window'));
  const inset = 0.22;
  const inner: P3[] = [P(from + inset, z0 + inset), P(to - inset, z0 + inset), P(to - inset, zs), ...(arch ? Array.from({ length: top - 1 }, (_, i) => { const a = (Math.PI * (i + 1)) / top; return P(from + r + (r - inset) * Math.cos(a), zs + (r - inset) * Math.sin(a)); }) : []), P(from + inset, zs)];
  if (glazing === 'double') out.push(poly(inner, 'axo-glaze-existing'));
  else if (glazing === 'single' && upgradeLook !== 'blocked') out.push(poly(inner, `axo-glaze-${upgradeLook}`));
  out.push(line(P((from + to) / 2, z0), P((from + to) / 2, zs + (arch ? r : 0)), 'axo-mullion'));
  if (glazing === 'unknown') out.push(text(P((from + to) / 2, (z0 + z1) / 2), '?', 'axo-q'));
  return out;
}

function glazingFor(i: number, g: string | null): 'single' | 'double' | 'unknown' {
  if (!g) return 'unknown';
  if (g === 'double' || g === 'triple' || g === 'secondary') return 'double';
  if (g === 'partial') return i === 0 ? 'double' : 'single';
  return 'single';
}

function houseModel(home: PublicHome, f: Map<string, FeasibilityItem>, look: (m: MeasureId) => Look): Model {
  const L = 11, W = 8, H = 5.2, h = 1.3, E = 5.4, R = 3, o = 0.45;
  const wt = wallType(f);
  const cav = look('cavity_wall');
  const prims: Prim[] = [];
  const bf = (home.built_form ?? '').toLowerCase();
  const neighbours = bf.includes('mid') || bf.includes('enclosed') ? 2 : bf.includes('semi') || bf.includes('end') ? 1 : 0;

  // site plan (dashed) + floor
  prims.push(poly([[-2, -2, 0], [L + T + 2, -2, 0], [L + T + 2, W + T + 4.2, 0], [-2, W + T + 4.2, 0]], 'axo-site'));
  prims.push(poly([[0, 0, 0], [L, 0, 0], [L, W, 0], [0, W, 0]], 'axo-floor'));
  if (neighbours >= 1) { prims.push(...ghostBox(-T - 7, -T - 0.3, 0, W, 0, H)); prims.push(text([-T - 3.6, W / 2, H + 0.6], 'NEIGHBOUR', 'axo-label axo-label-muted')); }

  // back walls (full height, inner faces visible), with openings
  prims.push(...wall(-T, L + T, -T, 0, H, 'x', wt, cav));
  prims.push(...wall(-T, 0, 0, W + T, H, 'y', wt, cav));
  const gl = look('double_glazing');
  prims.push(...windowOn('y', 0, 2.2, 4.2, 1.4, 4.4, glazingFor(0, home.glazing), gl, true));
  prims.push(...windowOn('y', 0, 6.4, 8.4, 1.4, 4.4, glazingFor(1, home.glazing), gl, true));
  prims.push(...windowOn('x', 0, 1.6, 3.2, 1.6, 4.0, glazingFor(2, home.glazing), gl));
  prims.push(poly([[0, 5.0, 0], [0, 6.6, 0], [0, 6.6, 3.6], [0, 5.0, 3.6]], 'axo-door'));
  // thermostat on the inner back-left wall
  const th = look('smart_thermostat');
  prims.push(poly([[0, 4.0, 2.6], [0, 4.6, 2.6], [0, 4.6, 3.2], [0, 4.0, 3.2]], `axo-part axo-${th}`));

  // front walls cut to sill height (section), external insulation when on
  prims.push(...wall(0, L, W, W + T, h, 'x', wt, cav));
  prims.push(...wall(L, L + T, 0, W + T, h, 'y', wt, cav));
  const sw = look('solid_wall');
  if (sw !== 'blocked') {
    prims.push(...box(0, L + T, W + T, W + T + 0.26, 0, h, `axo-ewi axo-${sw}`));
    prims.push(...box(L + T, L + T + 0.26, 0, W + T + 0.26, 0, h, `axo-ewi axo-${sw}`));
  }
  if (neighbours >= 2) { prims.push(...ghostBox(L + T + 0.3, L + T + 7, 0, W, 0, H)); prims.push(text([L + T + 3.6, W / 2, H + 0.6], 'NEIGHBOUR', 'axo-label axo-label-muted')); }

  // heat pump in the yard, piped through the wall
  const hp = look('heat_pump');
  if (hp !== 'blocked') {
    prims.push(line([L - 3.1, W + T, 0.7], [L - 3.1, W + T + 1.5, 0.7], `axo-pipe axo-${hp}`));
    prims.push(...box(L - 4, L - 2.2, W + T + 1.5, W + T + 2.7, 0, 1.4, `axo-unit axo-${hp}`));
    const fan: P3[] = Array.from({ length: 14 }, (_, i) => { const a = (2 * Math.PI * i) / 14; return [L - 3.1 + 0.55 * Math.cos(a), W + T + 2.7, 0.7 + 0.5 * Math.sin(a)]; });
    prims.push(poly(fan, `axo-fan axo-${hp}`));
  }

  // exploded loft insulation layer + construction lines
  const lf = look('loft_insulation');
  const zl = H + 1.8;
  for (const [x, y] of [[0, 0], [L, 0], [0, W], [L, W]] as const) prims.push(line([x, y, H], [x, y, zl + E + 0.4], 'axo-construct'));
  if (lf !== 'blocked') prims.push(...box(0, L, 0, W, zl, zl + 0.36, `axo-slab axo-${lf}`));
  else prims.push(...ghostBox(0, L, 0, W, zl, zl + 0.36));

  // exploded gable roof with solar
  const z0 = H + E;
  const ridgeY = W / 2;
  prims.push(poly([[-o, -o, z0], [L + o, -o, z0], [L + o, ridgeY, z0 + R], [-o, ridgeY, z0 + R]], 'axo-roof axo-roof-back'));
  prims.push(poly([[-o, ridgeY, z0 + R], [L + o, ridgeY, z0 + R], [L + o, W + o, z0], [-o, W + o, z0]], 'axo-roof'));
  prims.push(poly([[L + o, -o, z0], [L + o, W + o, z0], [L + o, ridgeY, z0 + R]], 'axo-roof axo-gable'));
  const pv = look('solar_pv');
  const onSlope = (u: number, v: number): P3 => [u, ridgeY + v * (W / 2 + o), z0 + R - v * R];
  const panels: Prim[] = [];
  const existingPv = home.solar_pv === true;
  if (pv !== 'blocked' || existingPv) {
    for (let i = 0; i < 4; i++) for (let j = 0; j < 2; j++) {
      const u0 = 1.6 + i * 2.1, v0 = 0.18 + j * 0.38;
      panels.push(poly([onSlope(u0, v0), onSlope(u0 + 1.9, v0), onSlope(u0 + 1.9, v0 + 0.34), onSlope(u0, v0 + 0.34)], `axo-panel ${existingPv ? 'axo-existing' : `axo-${pv}`}`));
    }
  }
  prims.push(...panels);
  if (wt === 'unknown') prims.push(text([L + T + 0.6, W * 0.45, h + 1.4], 'WALL TYPE NOT RECORDED ?', 'axo-label axo-q-label'));

  return {
    prims,
    anchors: {
      loft_insulation: [L * 0.35, W * 0.5, zl + 0.36],
      solar_pv: onSlope(5.6, 0.55),
      cavity_wall: [L * 0.82, -T / 2, H],
      solid_wall: [L + T + 0.26, W * 0.35, h * 0.6],
      double_glazing: [7.4, 0, 3.4],
      smart_thermostat: [0, 4.3, 2.9],
      heat_pump: [L - 3.1, W + T + 2.1, 1.4],
    },
    tagOffset: {
      loft_insulation: [-140, -10],
      solar_pv: [80, -50],
      cavity_wall: [80, 16],
      solid_wall: [64, 28],
      double_glazing: [110, -85],
      smart_thermostat: [-96, 26],
      heat_pump: [-80, 42],
    },
    detailAt: [L * 0.6, -T / 2, H],
    center: [L / 2, W / 2, (H + E + R) / 2],
  };
}

function flatModel(home: PublicHome, f: Map<string, FeasibilityItem>, look: (m: MeasureId) => Look): Model {
  const L = 10, W = 7.5, H = 3.6, h = 1.2;
  const wt = wallType(f);
  const cav = look('cavity_wall');
  const prims: Prim[] = [];
  const above = ['flat_not_top_floor', 'dwelling_above'].includes(f.get('loft_insulation')?.reason_code ?? '');
  prims.push(poly([[-1.5, -1.5, 0], [L + T + 1.5, -1.5, 0], [L + T + 1.5, W + T + 3.8, 0], [-1.5, W + T + 3.8, 0]], 'axo-site'));
  prims.push(poly([[0, 0, 0], [L, 0, 0], [L, W, 0], [0, W, 0]], 'axo-floor'));
  prims.push(...wall(-T, L + T, -T, 0, H, 'x', wt, cav));
  prims.push(...wall(-T, 0, 0, W + T, H, 'y', wt, cav));
  const gl = look('double_glazing');
  prims.push(...windowOn('y', 0, 2.0, 4.2, 1.0, 3.0, glazingFor(0, home.glazing), gl));
  prims.push(...windowOn('y', 0, 6.0, 8.2, 1.0, 3.0, glazingFor(1, home.glazing), gl));
  prims.push(poly([[0, 4.6, 0], [0, 6.0, 0], [0, 6.0, 2.6], [0, 4.6, 2.6]], 'axo-door'));
  const th = look('smart_thermostat');
  prims.push(poly([[0, 3.4, 1.8], [0, 3.9, 1.8], [0, 3.9, 2.3], [0, 3.4, 2.3]], `axo-part axo-${th}`));
  prims.push(...wall(0, L, W, W + T, h, 'x', wt, cav));
  prims.push(...wall(L, L + T, 0, W + T, h, 'y', wt, cav));
  const sw = look('solid_wall');
  if (sw !== 'blocked') prims.push(...box(L + T, L + T + 0.26, 0, W + T, 0, h, `axo-ewi axo-${sw}`));
  const hp = look('heat_pump');
  if (hp !== 'blocked') {
    prims.push(line([L - 2.6, W + T, 0.6], [L - 2.6, W + T + 1.3, 0.6], `axo-pipe axo-${hp}`));
    prims.push(...box(L - 3.4, L - 1.8, W + T + 1.3, W + T + 2.3, 0, 1.2, `axo-unit axo-${hp}`));
  }
  // the dwelling above (or the flat's own roof slab)
  const lf = look('loft_insulation');
  if (above) {
    prims.push(...ghostBox(-T, L + T, -T, W + T, H + 0.25, 2 * H));
    prims.push(text([L * 0.55, W * 0.4, 2 * H + 0.5], 'DWELLING ABOVE', 'axo-label axo-label-muted'));
  } else {
    prims.push(...box(-T, L + T, -T, W + T, H + 0.9, H + 1.3, `axo-slab axo-${lf === 'blocked' ? 'ghost' : lf}`));
  }
  if (wt === 'unknown') prims.push(text([L * 0.5, -T / 2, H + 0.5], 'WALL TYPE NOT RECORDED ?', 'axo-label axo-q-label'));
  const roofZ = above ? 2 * H : H + 1.3;
  return {
    prims,
    anchors: {
      loft_insulation: [L * 0.3, W * 0.5, above ? H + 0.25 : H + 1.3],
      solar_pv: [L * 0.7, W * 0.3, roofZ],
      cavity_wall: [L * 0.8, -T / 2, H],
      solid_wall: [L + T + 0.26, W * 0.4, h * 0.6],
      double_glazing: [7.1, 0, 2.3],
      smart_thermostat: [0, 3.65, 2.05],
      heat_pump: [L - 2.6, W + T + 1.8, 1.2],
    },
    tagOffset: {
      loft_insulation: [-140, -35],
      solar_pv: [80, -35],
      cavity_wall: [90, 8],
      solid_wall: [60, 26],
      double_glazing: [110, -85],
      smart_thermostat: [-90, 30],
      heat_pump: [-75, 40],
    },
    detailAt: [L * 0.55, -T / 2, H],
    center: [L / 2, W / 2, (above ? 2 * H : H + 1.3) / 2],
  };
}

// ---------------------------------------------------------------- component

const STATE_WORD: Record<CalloutState, string> = {
  selected: 'In plan',
  'pending-add': 'Adding…',
  'pending-remove': 'Removing…',
  available: 'Possible',
  verify: 'Check first',
  blocked: 'Not possible',
};

interface Props {
  home: PublicHome;
  isFlat: boolean;
  feasibility: FeasibilityItem[];
  selected: ReadonlySet<string>;
  applied: ReadonlySet<string>;
  buildOrder: readonly MeasureId[];
  scenarioId: string;
  onToggle(m: MeasureId): void;
  onExplain(m: MeasureId): void;
}

function DetailA({ wt, cavOn, ewiOn }: { wt: WallType; cavOn: boolean; ewiOn: boolean }) {
  return (
    <figure className="axo-detail" aria-label="Detail A: wall section">
      <svg viewBox="0 0 120 120" width="120" height="120" aria-hidden="true">
        <circle cx="60" cy="60" r="57" className="axo-detail-ring" />
        <clipPath id="axo-detail-clip"><circle cx="60" cy="60" r="56" /></clipPath>
        <g clipPath="url(#axo-detail-clip)">
          <rect x="18" y="0" width="22" height="120" className="axo-leaf" />
          <rect x="40" y="0" width="18" height="120" className={wt === 'solid' ? 'axo-leaf' : wt === 'unknown' ? 'axo-cav-unknown' : cavOn ? 'axo-hatch-on' : wt === 'cavity-filled' ? 'axo-hatch-existing' : 'axo-cav-air'} />
          <rect x="58" y="0" width="22" height="120" className="axo-leaf" />
          {ewiOn && <rect x="6" y="0" width="12" height="120" className="axo-hatch-on" />}
        </g>
        <text x="60" y="114" textAnchor="middle" className="axo-detail-a">A</text>
      </svg>
      <figcaption>
        <b>Detail A · wall section</b>
        <span>{ewiOn ? 'External insulation · ' : ''}outer leaf · {wt === 'solid' ? 'solid masonry' : wt === 'unknown' ? 'wall type not recorded (survey needed)' : cavOn ? 'cavity filled (plan)' : wt === 'cavity-filled' ? 'cavity already filled' : 'empty cavity'} · inner leaf</span>
      </figcaption>
    </figure>
  );
}

export function Axonometric({ home, isFlat, feasibility, selected, applied, buildOrder, scenarioId, onToggle, onExplain }: Props) {
  const [mode, setMode] = useState<'assembled' | 'order'>('assembled');
  const [yaw, setYaw] = useState<number>(45); // horizontal azimuth degrees
  const [pitch, setPitch] = useState<number>(30); // elevation degrees
  const [zoom, setZoom] = useState<number>(1.0);
  const [isDragging, setIsDragging] = useState<boolean>(false);
  const [hasInteracted, setHasInteracted] = useState<boolean>(false);

  const dragStart = useRef<{ x: number; y: number; yaw: number; pitch: number } | null>(null);
  const dragDistance = useRef<number>(0);

  const fmap = new Map(feasibility.map((f) => [f.measure as string, f]));
  const state = (m: MeasureId) => calloutState(m, fmap.get(m), selected, applied);
  const look = (m: MeasureId) => lookOf(state(m));
  const model = isFlat ? flatModel(home, fmap, look) : houseModel(home, fmap, look);
  const wt = wallType(fmap);

  // Mouse & touch drag rotation handlers
  const handlePointerDown = useCallback((e: PointerEvent<SVGSVGElement>) => {
    // Only primary button or touch
    if (e.button !== 0) return;
    dragStart.current = { x: e.clientX, y: e.clientY, yaw, pitch };
    dragDistance.current = 0;
    setIsDragging(true);
    setHasInteracted(true);
    try {
      e.currentTarget.setPointerCapture(e.pointerId);
    } catch {}
  }, [yaw, pitch]);

  const handlePointerMove = useCallback((e: PointerEvent<SVGSVGElement>) => {
    if (!dragStart.current) return;
    const dx = e.clientX - dragStart.current.x;
    const dy = e.clientY - dragStart.current.y;
    dragDistance.current = Math.hypot(dx, dy);

    const sensitivity = 0.45;
    const newYaw = (dragStart.current.yaw + dx * sensitivity) % 360;
    const newPitch = Math.max(12, Math.min(82, dragStart.current.pitch + dy * sensitivity));

    setYaw(newYaw);
    setPitch(newPitch);
  }, []);

  const handlePointerUp = useCallback((e: PointerEvent<SVGSVGElement>) => {
    dragStart.current = null;
    setIsDragging(false);
    try {
      e.currentTarget.releasePointerCapture(e.pointerId);
    } catch {}
  }, []);

  const handleWheel = useCallback((e: WheelEvent<SVGSVGElement>) => {
    if (e.ctrlKey || e.metaKey || e.altKey) return;
    e.preventDefault();
    setZoom((z) => Math.max(0.75, Math.min(1.8, z - e.deltaY * 0.0012)));
  }, []);

  // Keyboard navigation for rotation
  const handleKeyDownSvg = (e: KeyboardEvent<SVGSVGElement>) => {
    if (e.key === 'ArrowLeft') { e.preventDefault(); setYaw((y) => (y - 5) % 360); setHasInteracted(true); }
    else if (e.key === 'ArrowRight') { e.preventDefault(); setYaw((y) => (y + 5) % 360); setHasInteracted(true); }
    else if (e.key === 'ArrowUp') { e.preventDefault(); setPitch((p) => Math.min(82, p + 5)); setHasInteracted(true); }
    else if (e.key === 'ArrowDown') { e.preventDefault(); setPitch((p) => Math.max(12, p - 5)); setHasInteracted(true); }
  };

  const resetView = () => {
    setYaw(45);
    setPitch(30);
    setZoom(1.0);
  };

  const setPreset = (presetYaw: number, presetPitch: number) => {
    setYaw(presetYaw);
    setPitch(presetPitch);
    setHasInteracted(true);
  };

  // Dynamic 3D projection & depth-sorting
  const proj = useCallback((p: P3) => project3D(p, model.center, yaw, pitch, zoom), [model.center, yaw, pitch, zoom]);

  // Project and filter primitives with backface culling and depth sorting
  interface ProjectedPrim {
    k: 'poly' | 'line' | 'text';
    cls: string;
    text?: string;
    pts2: [number, number][];
    depth: number;
    idx: number;
  }

  const projectedPrims: ProjectedPrim[] = [];
  model.prims.forEach((pr, i) => {
    const projected = pr.p.map((pt) => proj(pt));
    const pts2 = projected.map((item) => item.p2);
    const avgDepth = projected.reduce((acc, curr) => acc + curr.depth, 0) / projected.length;

    if (pr.k === 'poly' && pr.cull) {
      const area = signedArea(pts2);
      // Backface culling: only draw front-facing faces (signed area > 0)
      if (area <= 0) return;
    }

    projectedPrims.push({
      k: pr.k,
      cls: pr.cls,
      text: pr.text,
      pts2,
      depth: avgDepth,
      idx: i,
    });
  });

  // Sort back-to-front (painter's depth sorting)
  projectedPrims.sort((a, b) => a.depth - b.depth);

  const drawn: ReactNode[] = projectedPrims.map((pr) => {
    if (pr.k === 'poly') {
      return <polygon key={pr.idx} className={pr.cls} points={pr.pts2.map((p) => p.join(',')).join(' ')} />;
    }
    if (pr.k === 'line') {
      const [a, b] = pr.pts2;
      return <line key={pr.idx} className={pr.cls} x1={a[0]} y1={a[1]} x2={b[0]} y2={b[1]} />;
    }
    const [x, y] = pr.pts2[0];
    return <text key={pr.idx} className={pr.cls} x={x} y={y} textAnchor="middle">{pr.text}</text>;
  });

  // Project measure callout tags
  const tags = MEASURE_ORDER.map((m, i) => {
    const anchorProj = proj(model.anchors[m]);
    const a = anchorProj.p2;
    const [dx, dy] = model.tagOffset[m];
    const t: [number, number] = [a[0] + dx, a[1] + dy];
    return { m, i, a, t, st: state(m) };
  });

  // Stable, comfortable centered viewBox
  const vbW = 760;
  const vbH = 620;
  const vb = [-vbW / 2, -vbH / 2, vbW, vbH];

  const order = buildOrder.filter((m) => selected.has(m) || applied.has(m));
  const orderPos = (m: MeasureId) => order.indexOf(m);

  const act = (m: MeasureId) => {
    // Prevent measure toggle if the user was dragging to rotate
    if (dragDistance.current > 5) return;
    if (state(m) === 'blocked') onExplain(m);
    else onToggle(m);
  };

  const onKey = (m: MeasureId) => (e: KeyboardEvent) => {
    if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); act(m); }
  };

  const label = (m: MeasureId, i: number) => {
    const st = state(m);
    return `E-${i + 1} ${measureLabel(m)}: ${STATE_WORD[st]}. ${st === 'blocked' ? `${fmap.get(m)?.reason_text ?? ''} Press to see why.` : 'Press to toggle.'}`;
  };

  const showDetail = selected.has('cavity_wall') || selected.has('solid_wall') || applied.has('cavity_wall') || applied.has('solid_wall');
  const detailScreen = proj(model.detailAt).p2;

  // Format angles for display
  const normYaw = Math.round(((yaw % 360) + 360) % 360);
  const normPitch = Math.round(pitch);

  return (
    <figure className={`axo axo-mode-${mode}`} aria-label="Retrofit sheet: rotatable 3D exploded axonometric of the home with its improvements">
      <ol className="axo-index" aria-label="Improvements index">
        {MEASURE_ORDER.map((m, i) => {
          const st = state(m);
          return (
            <li key={m}>
              <button
                type="button"
                className={`axo-row axo-row-${st}`}
                aria-pressed={st === 'blocked' ? undefined : selected.has(m)}
                aria-label={label(m, i)}
                onClick={() => act(m)}
              >
                <span className="axo-code">E-{i + 1}</span>
                <span className="axo-row-name">{MEASURE_SHORT[m]}</span>
                <span className="axo-row-state">{STATE_WORD[st]}</span>
              </button>
            </li>
          );
        })}
      </ol>

      <div className="axo-sheet">
        <div className="axo-head">
          <div className="axo-head-title-wrap">
            <span className="axo-title">Retrofit axonometric</span>
            <span className="axo-orbit-badge" title="Active 3D orientation">
              <Compass size={13} aria-hidden="true" />
              <span>{normYaw}° / {normPitch}°</span>
            </span>
          </div>

          {/* Quick 3D camera presets */}
          <div className="axo-camera-tools" role="toolbar" aria-label="3D View and Rotation controls">
            <div className="seg axo-presets-seg" role="group" aria-label="View presets">
              <button type="button" aria-pressed={normYaw === 45 && normPitch === 30} onClick={() => setPreset(45, 30)} title="Isometric view">3D Iso</button>
              <button type="button" aria-pressed={normYaw === 0 && normPitch === 15} onClick={() => setPreset(0, 15)} title="South elevation">Front</button>
              <button type="button" aria-pressed={normYaw === 90 && normPitch === 15} onClick={() => setPreset(90, 15)} title="East elevation">Side</button>
              <button type="button" aria-pressed={normPitch >= 75} onClick={() => setPreset(45, 80)} title="Roof plan view">Top</button>
            </div>

            <div className="axo-zoom-tools">
              <button type="button" className="btn-icon" onClick={() => setZoom((z) => Math.min(1.8, z + 0.15))} title="Zoom In" aria-label="Zoom in">
                <ZoomIn size={14} />
              </button>
              <button type="button" className="btn-icon" onClick={() => setZoom((z) => Math.max(0.75, z - 0.15))} title="Zoom Out" aria-label="Zoom out">
                <ZoomOut size={14} />
              </button>
              <button type="button" className="btn-icon" onClick={resetView} title="Fit to view" aria-label="Fit to view">
                <Maximize2 size={13} />
              </button>
              <button type="button" className="btn-icon" onClick={resetView} title="Reset 3D view" aria-label="Reset 3D view">
                <RotateCcw size={13} />
              </button>
            </div>
          </div>

          <div className="seg axo-seg" role="group" aria-label="Drawing mode">
            <button type="button" aria-pressed={mode === 'assembled'} onClick={() => setMode('assembled')}>Assembled</button>
            <button type="button" aria-pressed={mode === 'order'} onClick={() => setMode('order')}>Build order</button>
          </div>

          <span className="axo-area">{home.floor_area_m2 != null ? <>{fmtNumber(home.floor_area_m2)} m²</> : <span className="v-unknown">area ?</span>}</span>
        </div>

        {/* Rotatable 3D canvas viewport */}
        <div className={`axo-canvas-wrap ${isDragging ? 'is-dragging' : ''}`}>
          {!hasInteracted && (
            <div className="axo-drag-hint" aria-hidden="true">
              <Move3d size={15} />
              <span>Click & drag to rotate 3D house</span>
            </div>
          )}

          <svg
            className="axo-svg axo-svg-interactive"
            viewBox={vb.join(' ')}
            role="application"
            aria-label="3D Axonometric drawing. Click and drag with mouse or touch to rotate 360°. Use arrow keys to orbit. Numbered tags toggle improvements."
            tabIndex={0}
            onPointerDown={handlePointerDown}
            onPointerMove={handlePointerMove}
            onPointerUp={handlePointerUp}
            onPointerCancel={handlePointerUp}
            onWheel={handleWheel}
            onKeyDown={handleKeyDownSvg}
          >
            <defs>
              <pattern id="axo-hatch-on" width="5" height="5" patternUnits="userSpaceOnUse" patternTransform="rotate(45)">
                <line x1="0" y1="0" x2="0" y2="5" className="axo-hatch-line-on" />
              </pattern>
              <pattern id="axo-hatch-grey" width="5" height="5" patternUnits="userSpaceOnUse" patternTransform="rotate(45)">
                <line x1="0" y1="0" x2="0" y2="5" className="axo-hatch-line-grey" />
              </pattern>
            </defs>

            <g className="axo-model">{drawn}</g>

            {showDetail && (
              <g className="axo-detail-mark">
                <circle cx={detailScreen[0]} cy={detailScreen[1]} r="9" />
                <text x={detailScreen[0]} y={detailScreen[1] - 13} textAnchor="middle">A</text>
              </g>
            )}

            {tags.map(({ m, i, a, t, st }) => {
              const n = mode === 'order' && orderPos(m) >= 0 ? `${orderPos(m) + 1}` : `${i + 1}`;
              return (
                <g
                  key={m}
                  className={`axo-tag axo-tag-${st} ${mode === 'order' && orderPos(m) < 0 ? 'axo-tag-dim' : ''}`}
                  role="button"
                  tabIndex={0}
                  aria-label={`Tag ${i + 1}, ${label(m, i)}`}
                  aria-pressed={st === 'blocked' ? undefined : selected.has(m)}
                  onClick={() => act(m)}
                  onKeyDown={onKey(m)}
                >
                  <title>{`${measureLabel(m)}: ${STATE_WORD[st]}`}</title>
                  <line className="axo-leader" x1={a[0]} y1={a[1]} x2={t[0]} y2={t[1]} />
                  <circle className="axo-anchor" cx={a[0]} cy={a[1]} r="2.6" />
                  <rect x={t[0] - 11} y={t[1] - 11} width="22" height="22" />
                  <text x={t[0]} y={t[1] + 4.5} textAnchor="middle">{st === 'blocked' ? '×' : n}</text>
                </g>
              );
            })}
          </svg>
        </div>

        {mode === 'order' && (
          <p className="axo-order-caption small">
            {order.length
              ? <>The engine applies the plan in this order: <b>{order.map((m) => MEASURE_SHORT[m]).join(' → ')}</b>. Fabric first, so the heat pump can be smaller; solar last.</>
              : 'Add improvements to see the order the engine applies them in.'}
          </p>
        )}

        <div className="axo-foot">
          {showDetail && <DetailA wt={wt} cavOn={selected.has('cavity_wall')} ewiOn={selected.has('solid_wall')} />}
          <div className="axo-titleblock">
            <div className="tb-brand"><HabiMark size={22} /><b>HABI</b></div>
            <div><span>Property</span><b>{home.display_label}</b></div>
            <div><span>Ref.</span><b className="mono">{home.home_id}</b></div>
            <div><span>Scenario</span><b className="mono">{shortId(scenarioId)}</b></div>
            <div><span>Scale</span><b>Interactive 3D · 360°</b></div>
            <div><span>Source</span><b>EPC record + engine result</b></div>
            <div className="tb-sheet"><b>01/01</b></div>
          </div>
        </div>
      </div>
    </figure>
  );
}
