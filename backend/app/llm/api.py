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
from .explain import explain
from .measures import MeasureId
from .whatif import EngineMismatch, answer_whatif

router = APIRouter(prefix="/llm", tags=["llm"])
_runner: Callable[[str, list[str] | None], dict] | None = None


def configure_engine(runner: Callable[[str, list[str] | None], dict]) -> None:
    global _runner
    _runner = runner


def _run(property_id: str, measures: list[str] | None) -> dict:
    if _runner is None:
        raise HTTPException(503, "engine not configured: call backend.app.llm.api.configure_engine() at startup")
    try:
        return _runner(property_id, measures)
    except KeyError as e:
        raise HTTPException(404, f"unknown property {property_id}") from e


class ExplainRequest(BaseModel):
    property_id: str
    measures: list[MeasureId] | None = Field(default=None, description="None = the recommended plan")
    expected_scenario_id: str | None = None
    template_mode: bool = False
    prefetch_llm: bool = True  # with template_mode: also generate the LLM version in the background
    # Decision context (optional): who is deciding and their constraints. With either field set, the plan is chosen
    # for that person (engine package search) and the answer includes "For you" and "Before you start".
    customer_id: str | None = Field(default=None, pattern=r"^[A-Za-z0-9_-]{1,64}$")
    context: UserContext | None = None


class WhatIfRequest(BaseModel):
    property_id: str
    measures: list[MeasureId] | None = Field(default=None, description="The selection currently shown")
    question: str = Field(min_length=1, max_length=500)
    expected_scenario_id: str | None = None
    template_mode: bool = False
    customer_id: str | None = Field(default=None, pattern=r"^[A-Za-z0-9_-]{1,64}$")
    context: UserContext | None = None


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
    scenario = _run(req.property_id, req.measures)
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
    scenario = _run(req.property_id, req.measures)
    _check_expected(scenario, req.expected_scenario_id)
    try:
        answer = answer_whatif(scenario, req.question, lambda pid, ms: _run(pid, ms), use_llm=not req.template_mode)
    except EngineMismatch as e:
        raise HTTPException(500, f"engine did not apply the validated change: {e}") from e
    return answer.to_dict()
