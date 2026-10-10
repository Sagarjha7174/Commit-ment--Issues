"""FastAPI routes for explanations and what-ifs.

Wire-up in backend/app/main.py (P2/P5):

    from backend.app.llm.api import router as llm_router, configure_engine
    from backend.app.llm.engine import run_scenario   # team engine: (home_id, measures | None) -> result dict
    configure_engine(run_scenario)
    app.include_router(llm_router)

The frontend sends the property and the measure selection, never numbers: the
server reruns the engine (fast and deterministic) and explains the result, so
the explanation can only describe numbers the server computed. Pass the
scenario ID the UI is showing as expected_scenario_id; a mismatch returns 409
so a stale explanation is never displayed.
"""

from __future__ import annotations

from typing import Any, Callable

from fastapi import APIRouter, BackgroundTasks, HTTPException
from pydantic import BaseModel, Field

from . import memory
from .advise import advise, advise_whatif
from .client import status
from .context import UserContext
from ..schemas.scenario import Assumptions, UserReading
from .explain import explain
from .measures import MeasureId
from .whatif import EngineMismatch, answer_whatif

router = APIRouter(prefix="/llm", tags=["llm"])
_runner: Callable[[str, list[str] | None], dict] | None = None
_request_runner: Callable[[dict], dict] | None = None


def configure_engine(runner: Callable[[str, list[str] | None], dict],
                     request_runner: Callable[[dict], dict] | None = None) -> None:
    """runner(property_id, measures) -> scenario dict. request_runner(ScenarioRequest dict) -> scenario dict (optional):
    lets a caller send its full engine request (assumptions, reading, packages, sensitivity), so the scenario ID matches
    the one the web app shows, and lets what-ifs change assumptions and readings."""
    global _runner, _request_runner
    _runner = runner
    _request_runner = request_runner


def _run(property_id: str, measures: list[str] | None) -> dict:
    if _runner is None:
        raise HTTPException(503, "engine not configured: call backend.app.llm.api.configure_engine() at startup")
    try:
        return _runner(property_id, measures)
    except KeyError as e:
        raise HTTPException(404, f"unknown property {property_id}") from e


class EngineRequestFields(BaseModel):
    """Optional: the rest of the engine request the caller is showing. When any is set (and a request runner is
    configured), the engine runs exactly that request, so scenario IDs match the caller's."""
    assumptions: Assumptions | None = None
    user_reading: UserReading | None = None
    include_packages: bool | None = None
    include_sensitivity: bool | None = None
    include_uncertainty: bool | None = None

    def engine_request(self, property_id: str, measures: list[str] | None) -> dict | None:
        fields = {"assumptions": self.assumptions, "user_reading": self.user_reading,
                  "include_packages": self.include_packages, "include_sensitivity": self.include_sensitivity,
                  "include_uncertainty": self.include_uncertainty}
        if all(v is None for v in fields.values()):
            return None
        req = {"home_id": property_id, "measures": None if measures is None else [str(getattr(m, "value", m)) for m in measures]}
        for k, v in fields.items():
            if v is not None:
                req[k] = v.model_dump(mode="json") if isinstance(v, BaseModel) else v
        return req


class ExplainRequest(EngineRequestFields):
    property_id: str
    measures: list[MeasureId] | None = Field(default=None, description="None = the recommended plan")
    expected_scenario_id: str | None = None
    template_mode: bool = False
    prefetch_llm: bool = True  # with template_mode: also generate the LLM version in the background
    # Decision context (optional): who is deciding and their constraints. With either field set, the plan is chosen
    # for that person (engine package search) and the answer includes "For you" and "Before you start".
    customer_id: str | None = Field(default=None, pattern=r"^[A-Za-z0-9_-]{1,64}$")
    context: UserContext | None = None


class WhatIfRequest(EngineRequestFields):
    property_id: str
    measures: list[MeasureId] | None = Field(default=None, description="The selection currently shown")
    question: str = Field(min_length=1, max_length=500)
    expected_scenario_id: str | None = None
    template_mode: bool = False
    customer_id: str | None = Field(default=None, pattern=r"^[A-Za-z0-9_-]{1,64}$")
    context: UserContext | None = None


def _run_for(req: EngineRequestFields, property_id: str, measures: list[str] | None) -> dict:
    full = req.engine_request(property_id, measures)
    if full is None:
        return _run(property_id, measures)
    if _request_runner is None:
        raise HTTPException(501, "this server runs measure selections only (no request runner configured)")
    try:
        return _request_runner(full)
    except KeyError as e:
        raise HTTPException(404, f"unknown property {property_id}") from e


def _check_expected(scenario: dict, expected: str | None) -> None:
    if expected and scenario.get("scenario_id") != expected:
        raise HTTPException(409, {"error": "stale_scenario", "current_scenario_id": scenario.get("scenario_id")})


def _prefetch(scenario: dict) -> None:
    """Generate (and cache) the LLM explanation in the background, so the follow-up request is instant."""
    try:
        explain(scenario, use_llm=True)
    except Exception:  # best effort: the template is already on screen
        pass


@router.post("/explain")
def post_explain(req: ExplainRequest, background: BackgroundTasks) -> dict[str, Any]:
    """Template mode answers instantly and starts the LLM version in the background; the UI shows the
    template first and swaps in the LLM text by calling again with template_mode=false (then a cache hit)."""
    if req.customer_id or req.context:
        res = advise(req.property_id, lambda pid, ms: _run(pid, ms), context=req.context,
                     customer_id=req.customer_id, use_llm=not req.template_mode)
        return {"scenario": res.scenario, "explanation": res.explanation.to_dict(), "advice": res.to_dict()}
    scenario = _run_for(req, req.property_id, req.measures)
    _check_expected(scenario, req.expected_scenario_id)
    result = explain(scenario, use_llm=not req.template_mode)
    if req.template_mode and req.prefetch_llm:
        background.add_task(_prefetch, scenario)
    return {"scenario": scenario, "explanation": result.to_dict()}


@router.get("/health")
def get_health() -> dict[str, Any]:
    """Which providers are configured, in order, with their models and limits (no API calls)."""
    return {"engine_configured": _runner is not None, **status()}


@router.get("/profile/{customer_id}")
def get_profile(customer_id: str) -> dict[str, Any]:
    """The decision context this customer chose to share (stored locally, never inferred)."""
    try:
        return memory.load(customer_id).context.model_dump()
    except ValueError as e:
        raise HTTPException(422, str(e)) from e


@router.put("/profile/{customer_id}")
def put_profile(customer_id: str, context: UserContext) -> dict[str, Any]:
    try:
        profile = memory.load(customer_id)
    except ValueError as e:
        raise HTTPException(422, str(e)) from e
    profile.context = context
    memory.save(profile)
    return profile.context.model_dump()


@router.get("/history/{customer_id}")
def get_history(customer_id: str) -> list[dict[str, Any]]:
    """The versioned decision records: what was recommended, for which context, and with which versions."""
    try:
        return [r.model_dump() for r in memory.load(customer_id).records]
    except ValueError as e:
        raise HTTPException(422, str(e)) from e


@router.post("/whatif")
def post_whatif(req: WhatIfRequest) -> dict[str, Any]:
    if req.customer_id or req.context:
        try:
            res = advise_whatif(req.property_id, req.question, lambda pid, ms: _run(pid, ms),
                                customer_id=req.customer_id, context=req.context, use_llm=not req.template_mode)
        except EngineMismatch as e:
            raise HTTPException(500, f"engine did not apply the validated change: {e}") from e
        return {"scenario_id": res.explanation.scenario_id, "scenario": res.scenario,
                "recalculated": True, "explanation": res.explanation.to_dict(), "advice": res.to_dict(),
                "outcome": None if res.whatif is None else res.whatif.to_dict()["outcome"]}
    scenario = _run_for(req, req.property_id, req.measures)
    _check_expected(scenario, req.expected_scenario_id)
    try:
        answer = answer_whatif(scenario, req.question, lambda pid, ms: _run(pid, ms), use_llm=not req.template_mode,
                               request_runner=_request_runner)
    except EngineMismatch as e:
        raise HTTPException(500, f"engine did not apply the validated change: {e}") from e
    return answer.to_dict()
