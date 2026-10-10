"""Customer memory and versioned decision records (brief: optional Customer Memory extension; product concept:
"the decision record").

One JSON file per customer, local only (backend/.cache/memory/, never committed). It stores the decision context
the user chose to share and one record per recommendation: context, chosen plan and why, scenario ID, key engine
outcomes and versions. what_changed() compares the latest two records so the explanation can say what changed and
why the plan changed. Customer IDs are opaque; nothing here is inferred about the person.
"""

from __future__ import annotations

import os
import re
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from pydantic import BaseModel, Field

from .context import ROLE_TEXT, UserContext
from .measures import display_name

MEMORY_DIR = Path(os.environ.get("LLM_MEMORY_DIR", Path(__file__).resolve().parents[2] / ".cache" / "memory"))
_ID_RE = re.compile(r"^[A-Za-z0-9_-]{1,64}$")
_LOCK = threading.Lock()


class DecisionRecord(BaseModel):
    ts: str
    home_id: str
    scenario_id: str
    context: UserContext
    plan: list[str]
    choice: str = ""
    carbon_saving_kg: Optional[float] = None
    cost_gbp: Optional[float] = None
    score_after: Optional[int] = None
    versions: dict[str, Any] = Field(default_factory=dict)


class Profile(BaseModel):
    customer_id: str
    context: UserContext = Field(default_factory=UserContext)
    records: list[DecisionRecord] = Field(default_factory=list)


def _path(customer_id: str) -> Path:
    if not _ID_RE.match(customer_id or ""):
        raise ValueError("customer_id must be 1-64 letters, digits, '-' or '_'")
    return MEMORY_DIR / f"{customer_id}.json"


def load(customer_id: str) -> Profile:
    p = _path(customer_id)
    return Profile.model_validate_json(p.read_text()) if p.exists() else Profile(customer_id=customer_id)


def save(profile: Profile) -> None:
    p = _path(profile.customer_id)
    with _LOCK:
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(profile.model_dump_json(indent=1))


def record_from(contract: dict, ctx: UserContext, choice: str) -> DecisionRecord:
    ch = (contract.get("energy_results") or {}).get("change") or {}
    after = (contract.get("green_home_score") or {}).get("after") or {}
    return DecisionRecord(
        ts=datetime.now(timezone.utc).isoformat(timespec="seconds"), home_id=str(contract.get("property_id")),
        scenario_id=str(contract.get("scenario_id")), context=ctx, plan=list(contract.get("selected_measures") or []),
        choice=choice, carbon_saving_kg=(contract.get("carbon_results") or {}).get("saving_kg"),
        cost_gbp=(contract.get("cost_results") or {}).get("package_cost_gbp"), score_after=after.get("total"),
        versions=contract.get("versions") or {})


def _context_changes(old: UserContext, new: UserContext) -> list[str]:
    out = []
    if old.role != new.role and new.role != "unknown":
        out.append(f"you told us you are {ROLE_TEXT[new.role]}")
    if old.horizon != new.horizon and new.horizon != "uncertain":
        out.append("your expected time in the home changed")
    if old.budget_gbp != new.budget_gbp:
        out.append("you set a budget of up to £{:,}".format(new.budget_gbp) if new.budget_gbp is not None
                   else "you removed your budget")
    for m in sorted(set(new.completed) - set(old.completed)):
        out.append(f"you told us {display_name(m)} is already done")
    for m in sorted({r.measure for r in new.rejected} - {r.measure for r in old.rejected}):
        out.append(f"you told us you do not want {display_name(m)}")
    if set(new.constraints) != set(old.constraints):
        out.append("your constraints changed")
    if set(new.priorities) != set(old.priorities):
        out.append("your priorities changed")
    return out


def what_changed(prev: Optional[DecisionRecord], cur: DecisionRecord) -> Optional[dict[str, Any]]:
    """Facts for 'what changed since last time and why' (None for the first recommendation of a home)."""
    if prev is None or prev.home_id != cur.home_id:
        return None
    summary = _context_changes(prev.context, cur.context)
    added = [display_name(m) for m in cur.plan if m not in prev.plan]
    removed = [display_name(m) for m in prev.plan if m not in cur.plan]
    if added:
        summary.append("the plan now adds " + ", ".join(added))
    if removed:
        summary.append("the plan no longer includes " + ", ".join(removed))
    if not summary:
        summary.append("nothing in your situation or the plan changed")
    out: dict[str, Any] = {"changes_summary": summary}
    if prev.carbon_saving_kg is not None and cur.carbon_saving_kg is not None and added + removed:
        # kg_change semantics: positive = the new plan cuts more emissions than the previous one
        out["changes"] = {"carbon_saving_kg": round(cur.carbon_saving_kg - prev.carbon_saving_kg, 1)}
        if prev.cost_gbp is not None and cur.cost_gbp is not None:
            out["changes"]["extra_cost_gbp"] = round(cur.cost_gbp - prev.cost_gbp, 1)
    return out
