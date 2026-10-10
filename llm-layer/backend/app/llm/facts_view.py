"""Turn a scenario result (plan_final.md contract) into a flat catalogue of facts.

This is the only module that knows the shape of the scenario result. When P2's
schemas/scenario.py changes, adjust this file and nothing else in llm/.

Every fact has a dotted key ("energy_results.change.gas_saving_kwh",
"energy_results.per_measure.0.measure"), a kind that decides how it is rendered,
a status (available / unavailable / not_estimated / needs_verification) and,
where known, a provenance label. Numeric values are never shown to the LLM:
it sees keys, meanings, units, statuses and directions, and writes placeholders.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from .engine_map import is_engine_result, to_contract
from .measures import FABRIC, MEASURE_ORDER, display_name, ordered

# Kinds whose sign carries meaning: positive = reduction (savings convention).
SAVING_KINDS = frozenset({"kwh_change", "kg_change"})
# Kinds where positive = "goes up" (score points, extra cost).
UP_KINDS = frozenset({"score_change", "gbp_change"})
NUMERIC_KINDS = frozenset(
    {"kwh", "kwh_change", "kg", "kg_change", "gbp", "gbp_change", "pct", "score", "score_change",
     "points", "area", "weight", "number", "score_range"}
)
TEXT_KINDS = frozenset({"text", "text_list", "bool"})

AVAILABLE = "available"

PART_NAMES = {
    "energy_efficiency": "energy efficiency rating",
    "energy_intensity": "energy use per square metre",
    "intensity": "energy use per square metre",
    "insulation": "insulation",
    "heating": "heating system",
    "glazing": "windows and glazing",
    "windows": "windows and glazing",
    "renewables": "renewable energy",
    "smart": "smart energy controls",
    "smart_controls": "smart energy controls",
}

PART_ISSUES = {
    "energy_intensity": "high energy use per square metre",
    "energy_efficiency": "a low EPC energy efficiency rating",
    "intensity": "high energy use per square metre",
    "insulation": "poor insulation",
    "heating": "an inefficient heating system",
    "glazing": "single or partial glazing",
    "windows": "single or partial glazing",
    "renewables": "no renewable generation",
    "smart": "basic heating controls",
    "smart_controls": "basic heating controls",
}

INPUT_NAMES = {
    "floor_area_m2": "floor area",
    "gas_kwh": "gas use",
    "elec_kwh": "electricity use",
    "grid_elec_kwh": "electricity use",
    "floor_level": "which floor the flat is on",
    "walls": "wall construction",
    "roof": "roof insulation",
    "heating": "heating system",
    "controls": "heating controls",
    "glazing": "glazing",
}

# Friendlier labels for the keys the LLM uses most. Anything else gets an
# automatic label from its path.
LABELS = {
    "green_home_score.before.total": "Green Home Score today (0-100)",
    "green_home_score.before.class": "Score class today",
    "green_home_score.before.range": "Possible score range given missing parts",
    "green_home_score.before.completeness": "How many of the seven score parts use known data",
    "green_home_score.after.total": "Green Home Score after the selected measures",
    "green_home_score.after.class": "Score class after the selected measures",
    "energy_results.baseline.gas_kwh": "Gas use today",
    "energy_results.baseline.grid_elec_kwh": "Grid electricity use today",
    "energy_results.after.gas_kwh": "Gas use after the measures",
    "energy_results.after.grid_elec_kwh": "Grid electricity use after the measures",
    "energy_results.after.heat_pump_elec_kwh": "Electricity used by the heat pump",
    "energy_results.change.gas_saving_kwh": "Change in gas use (positive = less gas)",
    "energy_results.change.grid_elec_saving_kwh": "Change in grid electricity (positive = less electricity)",
    "energy_results.change.purchased_saving_kwh": "Change in total purchased energy (positive = less)",
    "energy_results.change.improvement_potential_pct": "Improvement potential: % cut in purchased energy",
    "carbon_results.saving_kg": "Change in carbon emissions (positive = emissions fell)",
    "carbon_results.factors_version": "Emissions factors used",
    "cost_results.package_cost_gbp": "Estimated cost of the selected measures",
    "cost_results.bill_change_gbp": "Change in energy bills in pounds",
    "valuation.status": "Valuation status (exploratory = a range IS given, to be called indicative)",
    "valuation.uplift_low_pct": "Indicative property value change, low end",
    "valuation.uplift_high_pct": "Indicative property value change, high end",
    "derived.score_drags": "Score parts with known data losing the most points (code-ranked; unknown parts excluded)",
    "derived.issues": "Key issues, in plain English (code-derived)",
    "derived.missing_inputs": "Details about the home that are missing",
    "diff.added": "Measures added in this what-if",
    "diff.removed": "Measures removed in this what-if",
    "diff.blocked": "Requested measures that were not added because they are not suitable",
    "diff.conditional": "Added measures that need checking first",
    "diff.gas_saving_kwh": "Gas change versus the previous plan (positive = new plan uses less gas)",
    "diff.grid_elec_saving_kwh": "Grid electricity change versus the previous plan (positive = new plan uses less)",
    "diff.carbon_saving_kg": "Carbon change versus the previous plan (positive = new plan cuts more emissions)",
    "diff.extra_cost_gbp": "Cost change versus the previous plan (positive = new plan costs more)",
    "derived.plan_order": "Selected measures in the order they are applied",
    "derived.order_reason": "Why the measures are applied in this order",
    "derived.largest_gas_saving_measure": "Measure with the largest estimated gas saving (code-ranked)",
}

# Keys never exposed as facts (identifiers, bookkeeping, handled specially).
_SKIP_TOP = {"scenario_id", "baseline_id", "input_provenance", "feasibility", "feasibility_reasons",
             "selected_measures", "data_timestamp", "versions", "key_issues"}

_STATUS_WORDS = {
    "not estimated": "not_estimated",
    "not_estimated": "not_estimated",
    "unavailable": "unavailable",
    "needs verification": "needs_verification",
    "needs_verification": "needs_verification",
    "off": "not_estimated",
    "disabled": "not_estimated",
}


@dataclass(frozen=True)
class Fact:
    key: str
    value: Any
    kind: str
    label: str
    status: str = AVAILABLE
    reason: str | None = None
    provenance: str | None = None

    @property
    def available(self) -> bool:
        return self.status == AVAILABLE and self.value is not None

    @property
    def numeric(self) -> bool:
        return self.kind in NUMERIC_KINDS

    @property
    def signed(self) -> bool:
        return self.kind in SAVING_KINDS or self.kind in UP_KINDS

    @property
    def direction(self) -> str | None:
        """Plain-English direction of a signed change, or None."""
        if not self.signed or not self.available:
            return None
        v = float(self.value)
        if v == 0:
            return "no change"
        if self.kind in SAVING_KINDS:
            return "reduction" if v > 0 else "increase"
        return "up" if v > 0 else "down"


@dataclass(frozen=True)
class Feasibility:
    measure: str
    state: str  # feasible | infeasible | needs_verification
    reason: str | None = None
    reason_code: str | None = None


@dataclass
class FactSheet:
    scenario_id: str
    property_id: str | None
    facts: dict[str, Fact]
    selected_measures: list[str]
    feasibility: dict[str, Feasibility]
    missing_inputs: list[str] = field(default_factory=list)
    warning_keys: list[str] = field(default_factory=list)
    baseline_provenance: set[str] = field(default_factory=set)
    permissions: dict[str, str] = field(default_factory=dict)  # decision context: measure -> permission status
    role: str = "unknown"

    def get(self, key: str) -> Fact | None:
        return self.facts.get(key)

    def value(self, key: str) -> Any:
        f = self.facts.get(key)
        return f.value if f else None

    def measures_in(self, state: str) -> list[str]:
        return ordered([m for m, f in self.feasibility.items() if f.state == state])

    def llm_catalogue(self, scope: str = "report") -> list[dict[str, Any]]:
        """What the LLM is allowed to see: no numeric values, ever. Bookkeeping and detail the
        explanation does not need are left out to keep the prompt small (free-tier token limits).
        scope="whatif" keeps only what a what-if answer needs: the differences and the new totals."""
        out = []
        for key in sorted(self.facts):
            f = self.facts[key]
            if _hidden_from_llm(key, self) or (scope == "whatif" and not key.startswith(_WHATIF_PREFIXES)):
                continue
            entry: dict[str, Any] = {"key": key, "meaning": f.label, "kind": f.kind, "status": f.status}
            if f.reason:
                entry["reason"] = f.reason
            if f.provenance:
                entry["provenance"] = f.provenance
            if f.direction:
                entry["direction"] = f.direction
            if f.kind in TEXT_KINDS and f.available:
                entry["text"] = mask_numbers(_as_text(f.value))
            out.append(entry)
        return out


_HIDDEN_RE = re.compile(
    r"^(green_home_score\.parts\.|property_id$|baseline_id$|validation_status$|\w*_version$|blocked_measures|"
    r"missing_inputs|energy_results\.baseline\.useful_|energy_results\.per_measure\.\d+\.impact_source|"
    r"valuation\.label$|cost_results\.bill_status$|assumptions\.\d+$|warnings$|"
    r"energy_results\.(baseline|after|change)\.(status|reason)$)")


_WHATIF_PREFIXES = ("diff.", "green_home_score.after.", "feasibility.", "derived.plan_order", "energy_results.change.",
                    "carbon_results.saving_kg", "cost_results.package_cost_gbp")


def _hidden_from_llm(key: str, sheet: "FactSheet") -> bool:
    if _HIDDEN_RE.search(key) and key != "carbon_results.factors_version":
        return True
    m = re.match(r"^feasibility\.(\w+)\.(state|measure|reason)$", key)
    if m:  # FEASIBILITY in the prompt header already lists every state; details only for non-feasible ones
        f = sheet.feasibility.get(m.group(1))
        return m.group(2) == "state" or (f is not None and f.state == "feasible")
    return False


_NUMBER_RE = re.compile(r"\d+(?:[.,/:]\d+)*")
_NUMBER_WORD_RE = re.compile(
    r"\b(one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve|thirteen|fourteen|fifteen|sixteen|"
    r"seventeen|eighteen|nineteen|twenty|thirty|forty|fifty|sixty|seventy|eighty|ninety|hundred|thousand|"
    r"million|dozen|half|quarter|twice)\b", re.IGNORECASE)


def mask_numbers(text: str) -> str:
    """Hide every figure in text shown to the LLM ("Two months ... 85%" -> "# months ... #%"). The LLM keeps the
    meaning and cites the fact by placeholder; code shows the real text. Keeps "the LLM never sees a number" true."""
    return _NUMBER_WORD_RE.sub("#", _NUMBER_RE.sub("#", text.replace("CO2", "CO\u2082")))


def _as_text(value: Any) -> str:
    if isinstance(value, bool):
        return "yes" if value else "no"
    if isinstance(value, (list, tuple)):
        return "; ".join(str(v) for v in value)
    return str(value)


def _kind_for(path: list[str], name: str, value: Any) -> str:
    if isinstance(value, bool):
        return "bool"
    if isinstance(value, str):
        return "text"
    in_score = bool(path) and path[0] == "green_home_score"
    if name == "range" and in_score:
        return "score_range"
    if name.endswith("_saving_kwh") or name.endswith("_change_kwh"):
        return "kwh_change"
    if name == "saving_kg" or name.endswith("_saving_kg") or name.endswith("_change_kg"):
        return "kg_change"
    if name.endswith("_kwh"):
        return "kwh"
    if name.endswith("_kg"):
        return "kg"
    if name.endswith("_gbp"):
        return "gbp_change" if "change" in name or "extra" in name else "gbp"
    if name.endswith("_pct"):
        return "pct"
    if name.endswith("_m2"):
        return "area"
    if name == "weight":
        return "weight"
    if in_score and name in ("total", "sub"):
        return "score"
    if in_score and name == "points":
        return "points"
    if name.endswith("score_change"):
        return "score_change"
    return "number"


def _auto_label(key: str) -> str:
    parts = [p for p in key.split(".") if not p.isdigit()]
    return " / ".join(p.replace("_", " ") for p in parts)


def _sibling_status(parent: dict, name: str) -> tuple[str | None, str | None]:
    """Find the status and reason that the contract stores next to a null value."""
    stem = re.sub(r"_(kwh|kg|gbp|pct|m2)$", "", name)
    candidates = [f"{name}_status", f"{stem}_status", "status"]
    stem_parts = stem.split("_")
    for i in range(len(stem_parts), 0, -1):
        candidates.append("_".join(stem_parts[:i]) + "_status")
    status = next((parent[c] for c in candidates if isinstance(parent.get(c), str)), None)
    reason_keys = [f"{name}_reason", f"{stem}_reason", "reason"]
    reason = next((parent[c] for c in reason_keys if isinstance(parent.get(c), str)), None)
    return status, reason


def _norm_status(status: str | None) -> str:
    if not status:
        return "unavailable"
    return _STATUS_WORDS.get(status.strip().lower(), "unavailable")


class _Builder:
    def __init__(self, scenario: dict):
        self.scenario = scenario
        self.input_prov: dict[str, str] = scenario.get("input_provenance") or {}
        self.facts: dict[str, Fact] = {}

    def add(self, key: str, value: Any, kind: str, *, status: str = AVAILABLE, reason: str | None = None,
            provenance: str | None = None, label: str | None = None) -> None:
        if value is None and status == AVAILABLE:
            status = "unavailable"
        self.facts[key] = Fact(key, value, kind, label or LABELS.get(key) or _auto_label(key), status, reason,
                               provenance)
        if status != AVAILABLE and reason:
            # Lets a claim cite why something is missing: {valuation.uplift_low_pct.reason}
            self.facts[f"{key}.reason"] = Fact(f"{key}.reason", reason, "text", f"why {_auto_label(key)} is {status}")

    def provenance_for(self, name: str) -> str | None:
        for cand in (name, name.replace("grid_", ""), name.replace("_kwh", ""), name.replace("grid_elec", "elec")):
            if cand in self.input_prov:
                return self.input_prov[cand]
        return None

    def walk(self, node: Any, path: list[str]) -> None:
        key = ".".join(path)
        name = path[-1] if path else ""
        if isinstance(node, dict):
            if "value" in node and not any(isinstance(v, dict) for v in node.values()):
                # Numeric leaf object: {"value", "unit", "provenance", "status", "reason"}
                v = node.get("value")
                status = AVAILABLE if v is not None else _norm_status(node.get("status"))
                self.add(key, v, _kind_for(path[:-1], name, v if v is not None else 0.0), status=status,
                         reason=node.get("reason"), provenance=node.get("provenance"))
                return
            for k, v in node.items():
                if not path and k in _SKIP_TOP:
                    continue
                if v is None:
                    status, reason = _sibling_status(node, k)
                    self.add(".".join(path + [k]), None, _kind_for(path, k, 0.0), status=_norm_status(status),
                             reason=reason)
                else:
                    self.walk(v, path + [k])
            return
        if isinstance(node, (list, tuple)):
            if name == "range" and all(isinstance(x, (int, float)) for x in node) and len(node) == 2:
                self.add(key, tuple(node), "score_range")
                return
            if all(isinstance(x, str) for x in node):
                self.add(key, list(node), "text_list", status=AVAILABLE if node else "unavailable",
                         reason=None if node else "none")
            for i, item in enumerate(node):
                self.walk(item, path + [str(i)])
            return
        self.add(key, node, _kind_for(path[:-1], name, node), provenance=self.provenance_for(name))


def _feasibility(scenario: dict) -> dict[str, Feasibility]:
    raw = scenario.get("feasibility") or {}
    reasons = scenario.get("feasibility_reasons") or {}
    out: dict[str, Feasibility] = {}
    for m, v in raw.items():
        if isinstance(v, dict):
            out[m] = Feasibility(m, v.get("state", "needs_verification"), v.get("reason") or reasons.get(m),
                                 v.get("reason_code"))
        else:
            out[m] = Feasibility(m, str(v), reasons.get(m))
    return out


def _derived(b: _Builder, scenario: dict, selected: list[str], feas: dict[str, "Feasibility"]) -> None:
    parts = (scenario.get("green_home_score") or {}).get("parts") or {}
    lost = []
    for name, p in parts.items():
        sub, weight = (p or {}).get("sub"), (p or {}).get("weight")
        if isinstance(sub, (int, float)) and isinstance(weight, (int, float)) and sub < 50:
            lost.append((weight * (100 - sub), name))
    lost.sort(key=lambda t: (-t[0], t[1]))
    top = [n for _, n in lost[:3]]
    if top:
        b.add("derived.score_drags", [PART_NAMES.get(n, n.replace("_", " ")) for n in top], "text_list",
              provenance="derived")
        issues = scenario.get("key_issues") or [PART_ISSUES.get(n, n.replace("_", " ")) for _, n in lost]
        b.add("derived.issues", issues, "text_list", provenance="derived")
    else:
        reason = "no score part is below average" if parts else "score parts not available"
        b.add("derived.score_drags", None, "text_list", status="unavailable", reason=reason)
        b.add("derived.issues", None, "text_list", status="unavailable", reason=reason)

    if selected:
        # A selected measure that needs verification carries its caveat inside the plan itself.
        perm = ((scenario.get("decision") or {}).get("permission")) or {}

        def note(m: str) -> str:
            p = perm.get(m) or {}
            if p.get("status") == "conditional" and p.get("who"):
                return f" (check first with {p['who']})"
            if (feas.get(m) is not None and feas[m].state == "needs_verification") or p.get("status") == "unverified":
                return " (needs checking on site first)"
            return ""

        names = [display_name(m) + note(m) for m in selected]
        b.add("derived.plan_order", ", then ".join(names), "text", provenance="derived")
        reasons = []
        if FABRIC & set(selected) and "heat_pump" in selected:
            reasons.append("insulation and glazing come before the heat pump because they reduce the heat it has "
                           "to supply")
        if "solar_pv" in selected and len(selected) > 1:
            reasons.append("solar panels are applied last because they only reduce the electricity bought "
                           "from the grid")
        if reasons:
            b.add("derived.order_reason", "; ".join(reasons), "text", provenance="assumption")

    per_measure = ((scenario.get("energy_results") or {}).get("per_measure")) or []
    best = None
    for row in per_measure:
        g = row.get("gas_saving_kwh")
        g = g.get("value") if isinstance(g, dict) else g
        if isinstance(g, (int, float)) and g > 0 and (best is None or g > best[0]):
            best = (g, row.get("measure"))
    if best:
        b.add("derived.largest_gas_saving_measure", display_name(best[1]), "text", provenance="derived")


def canonical(scenario: Any) -> dict:
    """Any supported scenario result (team engine result, model or dict; or the plan_final contract) as the
    contract dict the LLM layer reads."""
    if hasattr(scenario, "model_dump"):
        scenario = scenario.model_dump(mode="json")
    return to_contract(scenario) if is_engine_result(scenario) else scenario


def build_factsheet(scenario: Any) -> FactSheet:
    """Build the fact catalogue for one scenario result (team engine result, dict or Pydantic model)."""
    scenario = canonical(scenario)
    if not isinstance(scenario, dict) or not scenario.get("scenario_id"):
        raise ValueError("scenario result must be a dict with a scenario_id")

    b = _Builder(scenario)
    b.walk(scenario, [])

    rng = b.facts.get("green_home_score.before.range")
    if rng is not None and rng.available and rng.value[0] == rng.value[1]:
        del b.facts["green_home_score.before.range"]  # no missing parts: a "38-38" range only confuses

    feas = _feasibility(scenario)
    for m, f in feas.items():
        b.add(f"feasibility.{m}.state", f.state.replace("_", " "), "text")
        if f.reason:
            b.add(f"feasibility.{m}.reason", f.reason, "text")
        b.add(f"feasibility.{m}.measure", display_name(m), "text")

    # Per-measure rows: expose a readable measure name next to the raw ID.
    for i, row in enumerate(((scenario.get("energy_results") or {}).get("per_measure")) or []):
        if isinstance(row, dict) and row.get("measure"):
            b.add(f"energy_results.per_measure.{i}.measure", display_name(row["measure"]), "text")

    selected = ordered([m for m in scenario.get("selected_measures") or [] if m in MEASURE_ORDER])
    _derived(b, scenario, selected, feas)

    missing = list(scenario.get("missing_inputs") or [])
    if missing:
        b.add("derived.missing_inputs", [INPUT_NAMES.get(m, m.replace("_", " ")) for m in missing], "text_list",
              provenance="derived")

    warnings = scenario.get("warnings") or []
    prov = b.input_prov
    baseline_prov = {prov[k] for k in ("gas_kwh", "elec_kwh", "grid_elec_kwh") if k in prov}

    return FactSheet(
        scenario_id=str(scenario["scenario_id"]),
        property_id=scenario.get("property_id"),
        facts=b.facts,
        selected_measures=selected,
        feasibility=feas,
        missing_inputs=list(scenario.get("missing_inputs") or []),
        warning_keys=[f"warnings.{i}" for i in range(len(warnings))],
        baseline_provenance=baseline_prov,
        permissions={m: str(v.get("status", "")).replace(" ", "_")
                     for m, v in (((scenario.get("decision") or {}).get("permission")) or {}).items()},
        role=str((scenario.get("decision") or {}).get("role") or "unknown"),
    )
