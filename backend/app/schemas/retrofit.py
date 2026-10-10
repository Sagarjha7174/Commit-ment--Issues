"""Feasibility, simulation, carbon and package schemas.

Sign convention everywhere: saving = before - after (kWh/year or kg CO2e/year); positive = reduction;
an increase is a NEGATIVE saving. Missing = None plus a status, never 0.
"""
from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, ConfigDict, Field, computed_field, model_validator

from .enums import FeasibilityState, MeasureId, Provenance, Suitability, ValueStatus

TOL = 1e-6


class FeasibilityItem(BaseModel):
    model_config = ConfigDict(extra="forbid")
    measure: MeasureId
    state: FeasibilityState
    suitability: Optional[Suitability] = None
    reason_code: str
    reason_text: str
    missing_inputs: list[str] = Field(default_factory=list)


class EndUses(BaseModel):
    """Annual purchased energy split by end use, kWh/year. All values >= 0."""
    model_config = ConfigDict(extra="forbid")
    gas_space: float = 0.0
    gas_water: float = 0.0
    gas_other: float = 0.0          # cooking etc.; never touched by any measure
    elec_base: float = 0.0          # baseline electricity not split out as heating (appliances, lighting, ...)
    elec_space: float = 0.0         # electric space heating (electrically heated homes with a known split, D16)
    elec_water: float = 0.0         # electric water heating
    hp_elec: float = 0.0            # electricity added by a heat pump
    pv_offset: float = 0.0          # grid import avoided by solar PV

    @model_validator(mode="before")
    @classmethod
    def _drop_computed(cls, data):
        """Totals are computed fields (exported in JSON so consumers never recompute them); ignore them on input."""
        if isinstance(data, dict):
            return {k: v for k, v in data.items() if k not in ("gas_total", "elec_import", "elec_gross", "purchased")}
        return data

    @computed_field
    @property
    def gas_total(self) -> float:
        return self.gas_space + self.gas_water + self.gas_other

    @computed_field
    @property
    def elec_import(self) -> float:
        return self.elec_base + self.elec_space + self.elec_water + self.hp_elec - self.pv_offset

    @computed_field
    @property
    def elec_gross(self) -> float:
        """Electricity used before any PV offset (what PV % of grid electricity applies to)."""
        return self.elec_base + self.elec_space + self.elec_water + self.hp_elec

    @computed_field
    @property
    def purchased(self) -> float:
        return self.gas_total + self.elec_import


class SimStep(BaseModel):
    model_config = ConfigDict(extra="forbid")
    measure: MeasureId
    status: ValueStatus
    reason_code: Optional[str] = None
    impact_used: Optional[float] = None
    impact_basis: Optional[str] = None
    before: EndUses
    after: EndUses
    gas_saving_kwh: float          # before.gas_total - after.gas_total (0 when not applied)
    elec_saving_kwh: float         # before.elec_import - after.elec_import
    note: str = ""


class MeasureRow(BaseModel):
    """Marginal effect of one measure at its position in the fixed order."""
    model_config = ConfigDict(extra="forbid")
    measure: MeasureId
    status: ValueStatus
    reason_code: Optional[str] = None
    gas_saving_kwh: Optional[float] = None
    elec_saving_kwh: Optional[float] = None
    purchased_saving_kwh: Optional[float] = None
    impact_used: Optional[float] = None
    impact_basis: Optional[str] = None
    validated_impact: Optional[bool] = None
    provenance: Provenance = Provenance.derived


class SimResult(BaseModel):
    model_config = ConfigDict(extra="forbid")
    status: ValueStatus
    reason_code: Optional[str] = None
    before: Optional[EndUses] = None
    after: Optional[EndUses] = None
    steps: list[SimStep] = Field(default_factory=list)
    measures: list[MeasureRow] = Field(default_factory=list)
    gas_saving_kwh: Optional[float] = None
    elec_saving_kwh: Optional[float] = None
    purchased_saving_kwh: Optional[float] = None
    purchased_before_kwh: Optional[float] = None
    purchased_after_kwh: Optional[float] = None
    improvement_potential_pct: Optional[float] = None
    improvement_potential_status: ValueStatus = ValueStatus.unavailable
    improvement_potential_reason: Optional[str] = None
    warnings: list[str] = Field(default_factory=list)
    assumptions: dict = Field(default_factory=dict)

    @model_validator(mode="after")
    def _reconciles(self):
        if self.status != ValueStatus.ok or self.before is None or self.after is None:
            return self
        gas = sum(s.gas_saving_kwh for s in self.steps)
        elec = sum(s.elec_saving_kwh for s in self.steps)
        if abs(gas - (self.before.gas_total - self.after.gas_total)) > TOL * max(1, self.before.gas_total):
            raise ValueError("gas steps do not reconcile with total change")
        if abs(elec - (self.before.elec_import - self.after.elec_import)) > TOL * max(1, self.before.elec_import):
            raise ValueError("electricity steps do not reconcile with total change")
        if self.gas_saving_kwh is not None and abs(self.gas_saving_kwh - gas) > TOL * max(1, abs(gas)):
            raise ValueError("reported gas saving != sum of steps")
        if self.elec_saving_kwh is not None and abs(self.elec_saving_kwh - elec) > TOL * max(1, abs(elec)):
            raise ValueError("reported electricity saving != sum of steps")
        return self


class CarbonResult(BaseModel):
    model_config = ConfigDict(extra="forbid")
    status: ValueStatus
    reason_code: Optional[str] = None
    gas_kg: Optional[float] = None       # dE_gas * EF_gas, positive = emissions fell
    elec_kg: Optional[float] = None      # dE_elec * EF_elec
    total_kg: Optional[float] = None
    before_kg: Optional[float] = None
    after_kg: Optional[float] = None
    saving_pct_of_baseline: Optional[float] = None
    factors: dict = Field(default_factory=dict)

    @model_validator(mode="after")
    def _sum(self):
        if self.status == ValueStatus.ok and abs((self.gas_kg + self.elec_kg) - self.total_kg) > TOL * max(1, abs(self.total_kg)):
            raise ValueError("carbon per-fuel parts do not sum to total")
        return self


class PackageResult(BaseModel):
    model_config = ConfigDict(extra="forbid")
    package_id: str
    measures: list[MeasureId]
    confirmed: bool                       # only feasible measures
    must_verify: list[str] = Field(default_factory=list)
    cost_gbp: Optional[float] = None
    cost_provenance: str = "assumption: catalogue mid (EPC indicative cost)"
    cost_status: ValueStatus = ValueStatus.ok
    eligible_for_cost_comparison: bool = True
    gas_saving_kwh: Optional[float] = None
    elec_saving_kwh: Optional[float] = None
    purchased_saving_kwh: Optional[float] = None
    improvement_potential_pct: Optional[float] = None
    carbon_saving_kg: Optional[float] = None
    carbon_saving_pct: Optional[float] = None
    carbon_per_pound_kg: Optional[float] = None
    dominated: bool = False
    dominated_by: Optional[str] = None
    unvalidated_impacts: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    sensitivity: Optional[dict] = None    # for featured packages: does the pick survive each sensitivity run
    calibrated: Optional[dict] = None     # NEED-calibrated reference for 2+ fabric/controls measures (D17)
    grants_gbp: Optional[float] = None    # D27; subject to eligibility
    net_cost_gbp: Optional[float] = None
    bill_saving_gbp: Optional[float] = None    # annual, positive = bill falls (D26)
    payback_years: Optional[float] = None      # net cost / bill saving; None if the bill does not fall
    status: ValueStatus = ValueStatus.ok
    reason_code: Optional[str] = None


class FeaturedPick(BaseModel):
    model_config = ConfigDict(extra="forbid")
    objective: str           # lowest_cost_meeting_threshold | largest_carbon_saving | best_carbon_per_pound
    label: str               # literal description, never "best overall"
    package_id: Optional[str] = None
    message: Optional[str] = None
    alternatives: list[str] = Field(default_factory=list)   # fallback options shown instead of a pick


class PackageSearch(BaseModel):
    model_config = ConfigDict(extra="forbid")
    packages: list[PackageResult]
    featured: list[FeaturedPick]
    fallbacks: list[str] = Field(default_factory=list)
    excluded_measures: dict[str, str] = Field(default_factory=dict)
    threshold_pct: float
    budget_gbp: Optional[float] = None
    baseline_emissions_kg: Optional[float] = None
    cost_basis: str = "gross"             # "net of grants (subject to eligibility)" when grants are applied (D27)
