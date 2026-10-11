import { useEffect, useState } from 'react';
import { Navigate, useParams, useSearchParams } from 'react-router-dom';
import { useDemoHomes, useEvidence } from '../api/queries';
import type { ScenarioResult } from '../api/schema';
import { useScenarioLab } from '../hooks/useScenarioLab';
import { useExplanation } from '../hooks/useExplanation';
import { useSituation } from '../hooks/useSituation';
import { PropertyHero } from '../components/home/PropertyHero';
import { ScorePanel } from '../components/score/ScorePanel';
import { EnergyBalance } from '../components/energy/EnergyBalance';
import { MeasureExplorer } from '../components/retrofits/MeasureExplorer';
import { DecisionStudio } from '../components/packages/DecisionStudio';
import { ScenarioLabSection } from '../components/whatif/ScenarioLab';
import { ScenarioDock } from '../components/whatif/ScenarioDock';
import { ExplanationPanel } from '../components/explanation/ExplanationPanel';
import { DecisionAudit } from '../components/decision-audit/DecisionAudit';
import { ErrorState, LoadingBlock } from '../components/common/States';
import { SituationCard } from '../components/situation/SituationCard';
import { StepBar } from './myhome/StepBar';
import { TABS, type TabId } from './myhome/tabs';
import { YourHomeTab } from './myhome/YourHomeTab';
import { OptionsTab } from './myhome/OptionsTab';
import { TryTab } from './myhome/TryTab';
import { PlanTab } from './myhome/PlanTab';
import '../components/home/home.css';
import '../components/situation/situation.css';
import './pages.css';
import './myhome/myhome.css';

function PageHeader({ r }: { r: ScenarioResult }) {
  const h = r.home;
  return (
    <header className="page-header">
      <nav className="crumbs" aria-label="Breadcrumb"><span>My home</span><span aria-hidden="true">/</span><span>York</span></nav>
      <div className="page-header-row">
        <span className={`epc-chip epc-lg epc-${(h.rating ?? 'x').toLowerCase()}`} aria-label={`EPC band ${h.rating ?? 'unknown'}`}>{h.rating ?? '?'}</span>
        <div className="page-header-text">
          <h1 className="page-header-title">{h.display_label}</h1>
          <p className="page-header-meta">
            {[[h.built_form, h.property_type].filter(Boolean).join(' '), h.age_band, h.floor_area_m2 != null ? `${Math.round(h.floor_area_m2)} m²` : null, h.postcode_outward].filter(Boolean).join(' · ')}
            <span className="mono"> · {h.home_id}</span>
          </p>
        </div>
      </div>
    </header>
  );
}

const TAB_IDS = new Set<string>(TABS.map((t) => t.id));

function HomeView({ homeId }: { homeId: string }) {
  const lab = useScenarioLab(homeId);
  const evidence = useEvidence();
  const [params, setParams] = useSearchParams();
  const [situation] = useSituation();
  const [editing, setEditing] = useState(false);
  const [templateMode, setTemplateMode] = useState(false);
  const tabParam = params.get('tab') ?? 'home';
  const tab: TabId = TAB_IDS.has(tabParam) ? (tabParam as TabId) : 'home';
  const r = lab.state.confirmed;
  const explanation = useExplanation(r, templateMode);

  const goTo = (t: TabId) => {
    setParams((p) => { const n = new URLSearchParams(p); n.set('tab', t); return n; }, { replace: false });
    window.scrollTo?.({ top: 0, behavior: 'smooth' });
  };

  useEffect(() => {
    document.title = r ? `${r.home.display_label} · HABI` : 'HABI — Property intelligence for better homes';
  }, [r]);

  if (!r) {
    return (
      <div className="page" style={{ padding: '48px 0' }}>
        {lab.state.failure
          ? <ErrorState error={lab.state.failure.error} onRetry={lab.retry} />
          : <LoadingBlock label="Loading the home from the engine" lines={6} />}
      </div>
    );
  }

  const busy = lab.status === 'recalculating';
  const selected = new Set<string>(lab.selectedMeasures);
  return (
    <>
      <div className="page"><PageHeader r={r} /></div>
      <StepBar tab={tab} onTab={goTo} onEditSituation={() => setEditing((e) => !e)} />
      {editing && <div className="page"><SituationCard onClose={() => setEditing(false)} /></div>}
      <div
        className={`page tab-panel results ${busy ? 'is-recalculating' : ''}`}
        role="tabpanel"
        id={`panel-${tab}`}
        aria-labelledby={`tab-${tab}`}
        aria-busy={busy}
      >
        {tab === 'home' && <YourHomeTab r={r} lab={lab} classes={evidence.data?.score.classes} onTab={goTo}
          situation={!situation.done && !editing ? <SituationCard onClose={() => setEditing(false)} /> : null} />}
        {tab === 'options' && <OptionsTab r={r} lab={lab} onTab={goTo} />}
        {tab === 'try' && <TryTab r={r} lab={lab} onTab={goTo} />}
        {tab === 'plan' && <PlanTab r={r} lab={lab} onTab={goTo} explanation={explanation} templateMode={templateMode} onTemplateMode={setTemplateMode} />}
      </div>
      {tab === 'expert' && (
        <div className={`results ${busy ? 'is-recalculating' : ''}`} role="tabpanel" id="panel-expert" aria-labelledby="tab-expert" aria-busy={busy}>
          <div className="page" id="top">
            <PropertyHero result={r} selected={selected} onToggle={lab.toggleMeasure} />
          </div>
          <ScorePanel result={r} classes={evidence.data?.score.classes} />
          <EnergyBalance result={r} />
          <MeasureExplorer result={r} selected={selected} onToggle={lab.toggleMeasure} catalogue={evidence.data?.catalogue.measures} busy={busy} />
          <DecisionStudio
            result={r}
            selectedObjective={lab.state.selectedObjective}
            onSelectObjective={lab.selectObjective}
            onApply={(ms) => lab.setMeasures(ms)}
            currentSelection={lab.selectedMeasures}
          />
          <ScenarioLabSection lab={lab} result={r} />
          <ExplanationPanel result={r} state={explanation} templateMode={templateMode} onTemplateMode={setTemplateMode} pending={lab.pending || busy} />
          <DecisionAudit result={r} objective={lab.state.selectedObjective} />
        </div>
      )}
      <ScenarioDock lab={lab} />
    </>
  );
}

export default function MyHome() {
  const { homeId } = useParams();
  const demos = useDemoHomes();
  if (!homeId) {
    if (demos.data?.length) return <Navigate to={`/home/${demos.data[0].home_id}`} replace />;
    if (demos.error) return <div className="page" style={{ padding: '48px 0' }}><ErrorState error={demos.error} onRetry={() => demos.refetch()} /></div>;
    return <div className="page" style={{ padding: '48px 0' }}><LoadingBlock label="Loading example homes" /></div>;
  }
  return (
<HomeView key={homeId} homeId={homeId} />
  );
}
