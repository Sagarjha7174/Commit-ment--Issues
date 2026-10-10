import { useState, type FormEvent, type ReactNode } from 'react';
import { NavLink, useLocation, useNavigate } from 'react-router-dom';
import { BookOpen, Building2, Home, Menu, X } from 'lucide-react';
import { useQueryClient } from '@tanstack/react-query';
import { envDataMode, setDataMode, useDataMode } from '../../api/config';
import { useDemoHomes, useEvidence, useHealth, useSnapshotManifest } from '../../api/queries';
import { toApiError } from '../../api/errors';
import { fmtDate } from '../../utils/format';
import './shell.css';

const LINKS = [
  { to: '/home', label: 'My home', Icon: Home },
  { to: '/homes-needing-help', label: 'Homes needing help', Icon: Building2 },
  { to: '/method', label: 'Method & evidence', Icon: BookOpen },
];

const CASE_SHORT: Record<string, string> = {
  a_poor_gas_house: 'Gas-heated house',
  b_flat_loft_solar_infeasible: 'Electric flat',
  c_missing_data: 'Missing data',
};

function Logo() {
  return (
    <svg width="28" height="28" viewBox="0 0 28 28" aria-hidden="true" className="logo-mark">
      <rect width="28" height="28" rx="7" fill="var(--brand)" />
      <path d="M7 13.5 14 8l7 5.5V20a1 1 0 0 1-1 1H8a1 1 0 0 1-1-1z" fill="none" stroke="#fff" strokeWidth="1.8" strokeLinejoin="round" />
      <path d="M11.5 21v-3.5a2.5 2.5 0 0 1 5 0V21" fill="#fff" />
    </svg>
  );
}

function DataStatus() {
  const mode = useDataMode();
  const health = useHealth();
  const qc = useQueryClient();
  const switchTo = (m: 'live' | 'fixtures') => {
    qc.clear();
    setDataMode(m);
  };
  if (mode === 'fixtures') {
    return (
      <div className="status-card" role="note">
        <span className="status-line"><i className="dot dot-amber" aria-hidden="true" /> Offline snapshot</span>
        <span className="xsmall muted">Real engine results for 3 example homes, not live York data.</span>
        {envDataMode() === 'live' && <button className="btn-link xsmall" onClick={() => switchTo('live')}>Connect to live engine</button>}
      </div>
    );
  }
  const err = health.error ? toApiError(health.error) : null;
  return (
    <div className="status-card" role={err ? 'alert' : 'note'}>
      <span className="status-line">
        <i className={`dot ${err ? 'dot-red' : health.data ? 'dot-green' : 'dot-grey'}`} aria-hidden="true" />
        {err ? 'Live engine unreachable' : health.data ? 'Live engine' : 'Connecting…'}
      </span>
      {err && <span className="xsmall muted">{err.message}</span>}
      {!err && health.data?.data_mode === 'demo_homes' && <span className="xsmall muted">York data not on this server: the 3 public demo homes only.</span>}
      <span className="row">
        {err && <button className="btn-link xsmall" onClick={() => health.refetch()}>Retry</button>}
        <button className="btn-link xsmall" onClick={() => switchTo('fixtures')}>Use offline snapshot</button>
      </span>
    </div>
  );
}

function Sidebar({ onNavigate }: { onNavigate(): void }) {
  const demos = useDemoHomes();
  const mode = useDataMode();
  const nav = useNavigate();
  const [id, setId] = useState('');
  const open = (e: FormEvent) => {
    e.preventDefault();
    if (id.trim()) {
      nav(`/home/${encodeURIComponent(id.trim())}`);
      onNavigate();
    }
  };
  return (
    <div className="sidebar-inner">
      <NavLink to="/home" className="brand" aria-label="Green Home Score, home" onClick={onNavigate}>
        <Logo />
        <span className="brand-text"><b>Green Home Score</b><span>Retrofit planning</span></span>
      </NavLink>

      <nav className="side-nav" aria-label="Primary">
        {LINKS.map(({ to, label, Icon }) => (
          <NavLink key={to} to={to} onClick={onNavigate} className={({ isActive }) => `side-link ${isActive ? 'active' : ''}`}>
            <Icon size={17} aria-hidden="true" />
            <span>{label}</span>
          </NavLink>
        ))}
      </nav>

      <div className="side-section">
        <p className="side-label">Example homes</p>
        <nav className="side-homes" aria-label="Example homes">
          {(demos.data ?? []).map((d) => (
            <NavLink key={d.home_id} to={`/home/${d.home_id}`} onClick={onNavigate} className={({ isActive }) => `side-home ${isActive ? 'active' : ''}`}>
              <span className={`epc-chip epc-${(d.rating ?? 'x').toLowerCase()}`} aria-label={`EPC ${d.rating ?? 'unknown'}`}>{d.rating ?? '?'}</span>
              <span className="side-home-text"><b>{d.display_label.replace(/^Demo home (\w),.*$/, 'Home $1')}</b><span>{CASE_SHORT[d.case] ?? d.case}</span></span>
            </NavLink>
          ))}
        </nav>
        {mode === 'live' && (
          <form className="side-open" onSubmit={open}>
            <label htmlFor="open-home" className="side-label">Open a York home</label>
            <div className="row">
              <input id="open-home" className="input" value={id} onChange={(e) => setId(e.target.value)} placeholder="Property ID" />
              <button className="btn btn-sm" type="submit">Open</button>
            </div>
          </form>
        )}
      </div>

      <div className="side-foot">
        <DataStatus />
      </div>
    </div>
  );
}

export function Footer() {
  const ev = useEvidence();
  const health = useHealth();
  const manifest = useSnapshotManifest();
  const versions = ev.data?.versions ?? health.data?.versions;
  return (
    <footer className="footer">
      <p className="xsmall muted">
        Every number comes from the engine; the language model only explains. Not a lending, eligibility or credit decision.
      </p>
      <p className="xsmall muted mono">
        {versions ? Object.entries(versions).map(([k, v]) => `${k} ${v}`).join(' · ') : ''}
        {manifest.data ? ` · snapshot ${fmtDate(manifest.data.generated_at)} (${manifest.data.engine_commit})` : ''}
      </p>
    </footer>
  );
}

export function AppShell({ children }: { children: ReactNode }) {
  const loc = useLocation();
  const [openOn, setOpenOn] = useState<string | null>(null);
  const open = openOn === loc.pathname; // navigating closes the drawer
  const close = () => setOpenOn(null);
  return (
    <div className="app">
      <a className="skip-link" href="#main">Skip to content</a>
      <header className="mobilebar">
        <NavLink to="/home" className="brand" aria-label="Green Home Score, home"><Logo /><span className="brand-text"><b>Green Home Score</b></span></NavLink>
        <button className="nav-toggle" aria-expanded={open} aria-controls="sidebar" onClick={() => setOpenOn(open ? null : loc.pathname)}>
          {open ? <X size={20} aria-hidden="true" /> : <Menu size={20} aria-hidden="true" />}
          <span className="sr-only">{open ? 'Close menu' : 'Open menu'}</span>
        </button>
      </header>
      <aside id="sidebar" className={`sidebar ${open ? 'is-open' : ''}`}>
        <Sidebar onNavigate={close} />
      </aside>
      {open && <div className="scrim" onClick={close} aria-hidden="true" />}
      <div className="app-main">
        <main id="main" tabIndex={-1}>{children}</main>
        <Footer />
      </div>
    </div>
  );
}
