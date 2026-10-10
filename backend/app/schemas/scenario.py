"""Scenario request/result and the deterministic scenario_id."""
from __future__ import annotations

import hashlib
import json
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .enums import CombinationMode, HeatPumpMode, ImpactLevel, MeasureId, Provenance, ValueStatus
from .retrofit import CarbonResult, FeasibilityItem, PackageSearch, SimResult


class Assumptions(BaseModel):
    """Overrides for sensitivity / what-if. None = use the catalogue value."""
    model_config = ConfigDict(extra="forbid")
    impact_level: ImpactLevel = ImpactLevel.mid
    heat_pump_scop: Optional[float] = None
    space_share_of_heat_water_gas: Optional[float] = None
    other_gas_share: Optional[float] = None
    boiler_efficiency: Optional[float] = None
    heat_pump_mode: HeatPumpMode = HeatPumpMode.full
    heat_pump_partial_share: Optional[float] = None   # required when mode = partial
    baseline_scale: float = 1.0                       # sensitivity only
    segment_impacts: bool = True                      # NEED impacts adjusted to the home's segments (D15)
    gas_price_p: Optional[float] = Field(default=None, ge=0)    # what-if unit rate, p/kWh (D26); None = price cap
    elec_price_p: Optional[float] = Field(default=None, ge=0)   # e.g. a heat-pump tariff
    apply_grants: bool = True                         # package selection on cost net of grants (D27)
    combination_mode: CombinationMode = CombinationMode.engineering   # D17


class UserReading(BaseModel):
    model_config = ConfigDict(extra="forbid")
    gas_kwh: Optional[float] = Field(default=None, ge=0)
    elec_kwh: Optional[float] = Field(default=None, ge=0)


class ScenarioRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    home_id: str
    measures: Optional[list[MeasureId]] = None   # None = every feasible / needs_verification measure
    assumptions: Assumptions = Field(default_factory=Assumptions)
    user_reading: Optional[UserReading] = None
    include_packages: bool = True
    include_sensitivity: bool = False
    include_uncertainty: bool = False   # Monte Carlo ranges for the requested package (D28)
    use_modelled_epc: bool = False      # after-score EPC part = observed SAP + modelled ΔSAP (D34); default unchanged
    use_model_baseline: bool = False    # modelled baseline energy (M4) when configs/model_switch.json allows it


class Baseline(BaseModel):
    model_config = ConfigDict(extra="forbid")
    gas_kwh: Optional[float]
    elec_kwh: Optional[float]
    gas_provenance: Provenance
    elec_provenance: Provenance
    gas_status: str
    elec_status: str
    source: str                       # user_provided | modelled | population_benchmark | mixed
    blocking_flags: list[str] = Field(default_factory=list)
    gas_heated: bool = False
    elec_heated: bool = False                 # electric heating with a known heating share of electricity (D16)
    elec_heat_share: Optional[float] = None   # share of baseline electricity used for space + water heating
    elec_heat_share_source: str = ""
    note: str = ""


class PartScore(BaseModel):
    model_config = ConfigDict(extra="forbid")
    part: str
    sub: Optional[float]               # 0-100, None when missing
    used_sub: float                    # sub, or 50 for the headline when missing
    weight: float
    points: float                      # weight * used_sub
    provenance: Provenance
    status: str                        # ok | missing | unchanged_epc_not_reassessed | assumption
    detail: str = ""


class ScoreResult(BaseModel):
    model_config = ConfigDict(extra="forbid")
    status: ValueStatus
    total: Optional[int]
    raw_total: Optional[float]
    classification: Optional[str]
    range_low: Optional[int]
    range_high: Optional[int]
    completeness: str                  # "k/7"
    missing_parts: list[str]
    parts: list[PartScore]
    key_issues: list[str]
    notes: list[str] = Field(default_factory=list)
    # modelled EPC change after retrofit (M2 SAP model, provenance modelled); None when not computed (D34)
    epc_change: Optional[dict] = None
    rating_after_indicative: Optional[str] = None

    @model_validator(mode="after")
    def _check(self):
        if self.status == ValueStatus.ok:
            s = sum(p.points for p in self.parts)
            if abs(s - self.raw_total) > 1e-6:
                raise ValueError("part points do not sum to the total")
            if not (0 <= self.total <= 100):
                raise ValueError("score out of range")
        return self


class Valuation(BaseModel):
    """Indicative property-value impact (M3). Association from historical York sales, not a causal effect.
    Percentages are of the current value; GBP values are null (with value_reason) when the location is unseen."""
    model_config = ConfigDict(extra="forbid")
    status: ValueStatus
    reason: str
    low_pct: Optional[float] = None
    mid_pct: Optional[float] = None
    high_pct: Optional[float] = None
    sap_before: Optional[float] = None
    sap_change: Optional[float] = None
    sap_after_indicative: Optional[float] = None
    rating_before: Optional[str] = None
    rating_after_indicative: Optional[str] = None
    current_value_gbp: Optional[float] = None
    current_value_low_gbp: Optional[float] = None
    current_value_high_gbp: Optional[float] = None
    potential_value_low_gbp: Optional[float] = None
    potential_value_high_gbp: Optional[float] = None
    value_status: Optional[ValueStatus] = None      # status of the GBP figures
    value_reason: Optional[str] = None
    measures: list[MeasureId] = Field(default_factory=list)
    provenance: Optional[Provenance] = None
    basis: str = ""
    caveats: list[str] = Field(default_factory=list)
    model_versions: dict[str, str] = Field(default_factory=dict)
    explanation: Optional[list[dict]] = None        # top-5 TreeSHAP contributions to the current value (explain=True)

    @model_validator(mode="after")
    def _ordered(self):
        if self.status == ValueStatus.ok:
            if None in (self.low_pct, self.mid_pct, self.high_pct):
                raise ValueError("ok valuation needs low, mid and high")
            if not (self.low_pct <= self.mid_pct <= self.high_pct):
                raise ValueError("valuation range must satisfy low <= mid <= high")
        return self


class ScenarioResult(BaseModel):
    model_config = ConfigDict(extra="forbid")
    scenario_id: str
    home: dict[str, Any]               # public fields only (display_label, outward code, characteristics)
    request: ScenarioRequest
    baseline: Baseline
    feasibility: list[FeasibilityItem]
    measures_applied: list[MeasureId]
    measures_blocked: dict[str, str]
    simulation: SimResult
    standalone: dict[str, dict]        # per measure, applied alone
    carbon: CarbonResult
    score_before: ScoreResult
    score_after: Optional[ScoreResult]
    packages: Optional[PackageSearch] = None
    sensitivity: Optional[dict] = None
    valuation: Valuation
    combination_check: Optional[dict] = None   # NEED-calibrated reference next to the engineering estimate (D17)
    bills: Optional[dict] = None               # annual bill before/after per fuel (D26)
    finance: Optional[dict] = None             # gross/net cost, grants, payback, illustrative loan (D27)
    uncertainty: Optional[dict] = None         # Monte Carlo ranges (D28)
    recommendation_ranking: Optional[list[dict]] = None   # assessor-relevance priority of feasible measures (M5)
    install_sequence: Optional[list[str]] = None          # "do in this order": the engine's fixed physical order
    audit: dict
    assumptions: dict
    warnings: list[str]
    versions: dict[str, str]
    data_timestamp: str                # excluded from scenario_id

    @model_validator(mode="after")
    def _no_address(self):
        banned = {"address", "postcode", "uprn", "certificate_number"}
        if banned & set(self.home):
            raise ValueError("home block must not carry address fields")
        for m in self.measures_applied:
            if m.value in self.measures_blocked:
                raise ValueError(f"blocked measure {m.value} has a computed impact")
        return self


def _canonical(obj: Any) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), default=str)


def scenario_id(home_state: dict, request: ScenarioRequest, versions: dict) -> str:
    """SHA-256 of the canonical state: home inputs, request (measures sorted) and config versions. No timestamps."""
    req = request.model_dump(mode="json")
    if req.get("measures") is not None:
        req["measures"] = sorted(req["measures"])
    payload = {"home": home_state, "request": req, "versions": versions}
    return hashlib.sha256(_canonical(payload).encode()).hexdigest()
