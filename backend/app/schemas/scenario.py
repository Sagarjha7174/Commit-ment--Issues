"""Scenario request/result and the deterministic scenario_id."""
from __future__ import annotations

import hashlib
import json
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .enums import HeatPumpMode, ImpactLevel, MeasureId, Provenance, ValueStatus
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
    model_config = ConfigDict(extra="forbid")
    status: ValueStatus
    reason: str
    low_pct: Optional[float] = None
    high_pct: Optional[float] = None


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
