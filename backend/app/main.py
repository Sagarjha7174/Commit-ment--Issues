"""FastAPI app: engine routes plus the LLM explanation and what-if routes.

    .venv/bin/uvicorn backend.app.main:app --port 8000          (make api)

The web app (frontend/) calls /api/* (web_api.py) and /llm/*. In development Vite proxies both, so no CORS is needed;
CORS_ORIGINS (comma list) allows other origins. After `npm run build` in frontend/, this app also serves the built web
app at / (make web), so one process runs the whole demo.

The engine (scenario_builder.build) is the only writer of numbers; the LLM routes explain its results and turn
what-if questions into validated ScenarioRequests. No response carries an address, full postcode, UPRN or
certificate number (checked on every response). Without an LLM API key every route still works: answers use the
deterministic template explainer.
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Literal, Optional

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel, ConfigDict, Field

from .llm import service
from .llm.api import configure_engine, router as llm_router
from .llm.engine import run_request, run_scenario
from .llm.payload import assert_address_free
from .schemas.enums import MeasureId
from .schemas.scenario import Assumptions, ScenarioRequest, ScenarioResult, UserReading
from .services import api as engine_api
from .services.scenario_builder import PUBLIC_HOME_FIELDS, public_home
from .web_api import router as web_router

app = FastAPI(title="Lloyds PS2 Green Home Score", version="1.0",
              description="Engine results, explanations and what-ifs. Every number comes from the engine.")
configure_engine(lambda pid, measures: run_scenario(pid, measures), request_runner=run_request)
app.include_router(llm_router)
app.include_router(web_router)

_DEFAULT_ORIGINS = "http://localhost:5173,http://127.0.0.1:5173,http://localhost:4173,http://127.0.0.1:4173"
app.add_middleware(CORSMiddleware, allow_origins=[o.strip() for o in os.environ.get("CORS_ORIGINS", _DEFAULT_ORIGINS).split(",")
                                                  if o.strip()],
                   allow_methods=["GET", "POST", "PUT"], allow_headers=["Content-Type", "Accept"])


class Turn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    role: Literal["user", "assistant"]
    text: str = Field(max_length=2000)


class ExplainBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    home_id: str
    question: Optional[str] = Field(default=None, max_length=500)
    history: list[Turn] = Field(default_factory=list, max_length=20)
    measures: Optional[list[MeasureId]] = None          # None = every feasible / needs-verification measure
    assumptions: Assumptions = Field(default_factory=Assumptions)
    user_reading: Optional[UserReading] = None
    include_uncertainty: bool = False
    use_llm: bool = True                                # false = deterministic template only
    include_payload: bool = False                       # the address-free numeric payload (stable keys)


class WhatIfBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    home_id: str
    question: str = Field(min_length=1, max_length=500)
    measures: Optional[list[MeasureId]] = None          # the selection currently shown
    assumptions: Assumptions = Field(default_factory=Assumptions)
    user_reading: Optional[UserReading] = None
    include_uncertainty: bool = False
    history: list[Turn] = Field(default_factory=list, max_length=20)
    use_llm: bool = True


def _safe(obj: Any) -> Any:
    assert_address_free(obj)
    return obj


def _scenario(home_id: str, measures, assumptions, user_reading, include_uncertainty) -> dict:
    req = ScenarioRequest(home_id=home_id, measures=measures, assumptions=assumptions, user_reading=user_reading,
                          include_uncertainty=include_uncertainty)
    try:
        return run_request(req.model_dump(mode="json"))
    except KeyError as e:
        raise HTTPException(404, f"unknown home {home_id}") from e


@app.get("/health")
def health() -> dict:
    from .llm.client import status
    from .ml import registry
    return {"ok": True, "llm": status(), "models": registry.shipped_versions()}


@app.get("/homes/{home_id}/score")
def get_score(home_id: str) -> dict:
    from .data.loaders import get_home
    try:
        home = get_home(home_id)
    except KeyError as e:
        raise HTTPException(404, f"unknown home {home_id}") from e
    return _safe({"home": public_home(home), "score": engine_api.score(home_id).model_dump(mode="json")})


@app.post("/scenario", response_model=ScenarioResult)
def post_scenario(req: ScenarioRequest) -> ScenarioResult:
    try:
        res = engine_api.build(req)
    except KeyError as e:
        raise HTTPException(404, f"unknown home {req.home_id}") from e
    _safe(res.home)
    return res


@app.post("/explain")
def post_explain(body: ExplainBody) -> dict:
    """{answer, cited_values, scenario_id, grounded}: a question about the selected home. A question that changes the
    plan (add/remove measures, tariff, grants, partial heat pump, own reading, ranges) is recalculated as a what-if;
    an out-of-scope question is declined."""
    scenario = _scenario(body.home_id, body.measures, body.assumptions, body.user_reading, body.include_uncertainty)
    out = service.answer(scenario, body.question, run_scenario, run_request,
                         history=[t.model_dump() for t in body.history], use_llm=body.use_llm)
    if body.include_payload:
        out["payload"] = service.payload_for(scenario)
    return _safe(out)


@app.post("/whatif")
def post_whatif(body: WhatIfBody) -> dict:
    """Turn the question into a validated ScenarioRequest change, rerun the engine and explain the difference.
    Situation statements (budget, tenant, horizon, done or refused measures) re-decide the plan for the user."""
    from .llm.advise import advise_whatif, keyword_context
    scenario = _scenario(body.home_id, body.measures, body.assumptions, body.user_reading, body.include_uncertainty)
    if keyword_context(body.question):
        res = advise_whatif(body.home_id, body.question, lambda pid, ms: run_scenario(pid, ms), use_llm=body.use_llm)
        e = res.explanation
        out = {"kind": "advice", "answer": e.rendered.all_text, "scenario_id": e.scenario_id, "recalculated": True,
               "grounded": None if e.number_check is None else e.number_check.grounded,
               "numbers": None if e.number_check is None else e.number_check.to_dict(),
               "cited_values": [], "source": e.source, "advice": res.to_dict()}
        out["advice"].pop("scenario", None)
        return _safe(out)
    out = service.whatif_question(scenario, body.question, run_scenario, run_request, use_llm=body.use_llm)
    out.pop("scenario", None)
    return _safe(out)


@app.get("/portfolio")
def get_portfolio(rank_by: Literal["improvement_potential", "fabric_potential", "carbon_per_pound",
                                   "carbon_saving"] = "improvement_potential",
                  top_n: int = Query(50, ge=1, le=500), split: Optional[str] = None) -> dict:
    return _safe(engine_api.portfolio(top_n=top_n, split=split, rank_by=rank_by))


# ---- built web app (frontend/dist), served last so every API route above wins ----
WEB_DIST = Path(os.environ.get("WEB_DIST", Path(__file__).resolve().parents[2] / "frontend" / "dist"))


if (WEB_DIST / "index.html").exists():
    @app.get("/", include_in_schema=False)
    @app.get("/{path:path}", include_in_schema=False)
    def web_app(path: str = "") -> FileResponse:
        """Static files from the build; any other path is a client-side route, so it gets index.html."""
        root = WEB_DIST.resolve()
        f = (root / path).resolve()
        if path and f.is_file() and f.is_relative_to(root):
            return FileResponse(f)
        if path.startswith(("api/", "llm/")):
            raise HTTPException(404, "not found")
        return FileResponse(root / "index.html")


__all__ = ["app", "PUBLIC_HOME_FIELDS"]
