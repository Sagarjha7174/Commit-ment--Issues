/**
 * Permission and approval guidance by role and building type.
 *
 * Engine feasibility is a hard gate and always comes first. The permission layer is general UK guidance
 * only: it can mark a measure "conditional" or "unverified", never "confirmed", because this app has no
 * verified source for consents, leases or planning rules. Not legal advice.
 */
import type { FeasibilityItem, MeasureId, PublicHome } from '../api/schema';
import type { Role } from '../hooks/useSituation';

export type PermissionState = 'not_feasible' | 'needs_survey' | 'needs_consent' | 'needs_building_approval' | 'check_local_rules' | 'no_known_issue';

export interface PermissionStatus {
  state: PermissionState;
  label: string;
  /** Who to ask, in plain words. */
  who: string | null;
  detail: string;
}

const STATE_LABEL: Record<PermissionState, string> = {
  not_feasible: 'Not possible here',
  needs_survey: 'Needs a survey first',
  needs_consent: 'Needs landlord permission',
  needs_building_approval: 'Needs building approval',
  check_local_rules: 'Check local rules',
  no_known_issue: 'No known permission issue',
};

/** Measures that change the outside of the building or shared parts. */
const EXTERIOR: ReadonlySet<MeasureId> = new Set(['solid_wall', 'double_glazing', 'heat_pump', 'solar_pv']);
const SHARED_ROOF: ReadonlySet<MeasureId> = new Set(['solar_pv', 'loft_insulation']);

const LOCAL_RULES: Partial<Record<MeasureId, string>> = {
  solid_wall: 'External wall insulation can need planning permission, especially in conservation areas.',
  heat_pump: 'Air-source heat pumps are often permitted development, subject to noise and siting conditions.',
  solar_pv: 'Roof solar is often permitted development, but not on listed buildings or some conservation-area roofs.',
  double_glazing: 'Window changes can need consent on listed buildings or in conservation areas.',
};

export function isFlat(home: PublicHome): boolean {
  return home.property_type === 'Flat' || home.property_type === 'Maisonette';
}

export function permissionFor(m: MeasureId, f: FeasibilityItem | undefined, role: Role, home: PublicHome): PermissionStatus {
  if (f?.state === 'infeasible') {
    return { state: 'not_feasible', label: STATE_LABEL.not_feasible, who: null, detail: f.reason_text };
  }
  if (role === 'tenant') {
    return {
      state: 'needs_consent', label: STATE_LABEL.needs_consent, who: 'your landlord',
      detail: 'This is a permanent change to the property, so the landlord must agree (and usually pays).',
    };
  }
  if ((role === 'leaseholder' || isFlat(home)) && (EXTERIOR.has(m) || SHARED_ROOF.has(m))) {
    return {
      state: 'needs_building_approval', label: STATE_LABEL.needs_building_approval, who: 'the freeholder, managing agent or residents’ committee',
      detail: 'It affects the roof, outside walls or shared parts of the building.',
    };
  }
  if (f?.state === 'needs_verification') {
    return {
      state: 'needs_survey', label: STATE_LABEL.needs_survey, who: 'a qualified surveyor or installer',
      detail: `${f.reason_text}${f.missing_inputs.length ? ` Missing: ${f.missing_inputs.join(', ').replace(/_/g, ' ')}.` : ''}`,
    };
  }
  if (LOCAL_RULES[m]) {
    return { state: 'check_local_rules', label: STATE_LABEL.check_local_rules, who: 'your local council planning team', detail: LOCAL_RULES[m]! };
  }
  return { state: 'no_known_issue', label: STATE_LABEL.no_known_issue, who: null, detail: 'Still use a qualified installer.' };
}

export const PERMISSION_NOTE = 'General UK guidance, not legal advice. Nothing here has been checked against your lease, tenancy or local planning rules.';
