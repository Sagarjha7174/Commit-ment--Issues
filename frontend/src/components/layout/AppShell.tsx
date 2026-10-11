import { useState, useEffect, type FormEvent, type ReactNode } from 'react';
import { NavLink, useLocation, useNavigate } from 'react-router-dom';
import { BookOpen, Building2, Home, Menu, X } from 'lucide-react';
import { useQueryClient } from '@tanstack/react-query';
import { envDataMode, setDataMode, useDataMode } from '../../api/config';
import { useDemoHomes, useEvidence, useHealth, useSnapshotManifest } from '../../api/queries';
import { toApiError } from '../../api/errors';
import { fmtDate } from '../../utils/format';
import { HabiLogo } from '../brand/Habi';
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
      <div className="sidebar-top">
        <NavLink to="/home" className="brand" aria-label="HABI, home" onClick={onNavigate}>
          <HabiLogo size={30} tone="light" />
        </NavLink>
        <button className="sidebar-close-btn" onClick={onNavigate} aria-label="Close navigation menu">
          <X size={18} aria-hidden="true" />
        </button>
      </div>
      <p className="brand-tagline">Property intelligence for better homes.</p>

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
        <b>HABI</b> · Property intelligence for better homes. Every number comes from the engine; the language model only explains. Not a lending, eligibility or credit decision.
      </p>
      <details className="footer-versions">
        <summary className="xsmall muted">Model and data versions</summary>
        <p className="xsmall muted mono">
          {versions ? Object.entries(versions).map(([k, v]) => `${k} ${v}`).join(' · ') : ''}
          {manifest.data ? ` · snapshot ${fmtDate(manifest.data.generated_at)} (${manifest.data.engine_commit})` : ''}
        </p>
      </details>
    </footer>
  );
}

export function AppShell({ children }: { children: ReactNode }) {
  const loc = useLocation();
  const demos = useDemoHomes();
  const [openOn, setOpenOn] = useState<string | null>(null);
  const open = openOn === loc.pathname; // navigating closes the drawer
  const close = () => setOpenOn(null);

  // Lock background scroll when drawer is open and handle Escape key
  useEffect(() => {
    if (open) {
      document.body.style.overflow = 'hidden';
      const handleKeyDown = (e: KeyboardEvent) => {
        if (e.key === 'Escape') setOpenOn(null);
      };
      window.addEventListener('keydown', handleKeyDown);
      return () => {
        document.body.style.overflow = '';
        window.removeEventListener('keydown', handleKeyDown);
      };
    } else {
      document.body.style.overflow = '';
    }
  }, [open]);

  // Current active home in mobile header if on /home/:id
  const currentHomeId = loc.pathname.startsWith('/home/') ? loc.pathname.replace('/home/', '') : null;
  const currentDemo = (demos.data ?? []).find((d) => d.home_id === currentHomeId);

  return (
    <div className="app">
      <a className="skip-link" href="#main">Skip to content</a>
      <header className="mobilebar">
        <NavLink to="/home" className="brand mobile-brand" aria-label="HABI, home">
          <HabiLogo size={24} tone="light" />
        </NavLink>

        {currentDemo && (
          <div className="mobilebar-home-pill">
            <span className={`epc-chip epc-xs epc-${(currentDemo.rating ?? 'x').toLowerCase()}`}>{currentDemo.rating ?? '?'}</span>
            <span className="mobilebar-home-name">{currentDemo.display_label.replace(/^Demo home (\w),.*$/, 'Home $1')}</span>
          </div>
        )}

        <button
          className="nav-toggle"
          aria-expanded={open}
          aria-controls="sidebar"
          aria-label={open ? 'Close menu' : 'Open menu'}
          onClick={() => setOpenOn(open ? null : loc.pathname)}
        >
          {open ? <X size={20} aria-hidden="true" /> : <Menu size={20} aria-hidden="true" />}
          <span className="sr-only">{open ? 'Close menu' : 'Open menu'}</span>
        </button>
      </header>
      <aside id="sidebar" className={`sidebar ${open ? 'is-open' : ''}`} aria-label="Sidebar navigation">
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
