"""Routes for the web app (frontend/, contract: frontend/docs/API_CONTRACT.md), under /api.

Thin wrappers over services/api.py: every number comes from scenario_builder.build() or the engine's package search
and portfolio code. Every response is checked for address fields before it leaves the server.
"""
from __future__ import annotations

from typing import Literal, Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field

from . import config
from .data import demo_homes
from .data.loaders import data_mode
from .evidence import evidence
from .llm.payload import assert_address_free
from .schemas.scenario import Assumptions, ScenarioRequest, UserReading
from .services import api as engine_api

router = APIRouter(prefix="/api", tags=["web"])

DATA_NOTES = {
    "york_parquet": "York EPC build: 65,872 homes.",
    "demo_homes": "York data not present on this server: the three public demo homes only, rebuilt from "
                  "configs/demo_homes.json.",
}


def _safe(obj):
    assert_address_free(obj)
    return obj


class PackagesBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    home_id: str
    assumptions: Assumptions = Field(default_factory=Assumptions)
    user_reading: Optional[UserReading] = None
    budget_gbp: Optional[float] = Field(default=None, ge=0)
    threshold_pct: Optional[float] = Field(default=None, gt=0, le=100)


@router.get("/health")
def health() -> dict:
    return {"status": "ok", "data_mode": data_mode(),
            "versions": {k: str(v) for k, v in config.versions().items() if v is not None}}


@router.get("/demo-homes")
def demo_home_list() -> list[dict]:
    return _safe(demo_homes.demo_list())


@router.post("/scenario")
def scenario(req: ScenarioRequest) -> dict:
    try:
        res = engine_api.build(req)
    except KeyError as e:
        raise HTTPException(404, f"unknown home {req.home_id}") from e
    return _safe(res.model_dump(mode="json"))


@router.post("/packages")
def packages(body: PackagesBody) -> dict:
    """The engine's package search with an optional spending limit (packages costing at most budget_gbp)."""
    kw = {} if body.threshold_pct is None else {"threshold_pct": body.threshold_pct}
    try:
        ps = engine_api.search(body.home_id, body.assumptions, budget_gbp=body.budget_gbp,
                               user_reading=body.user_reading, **kw)
    except KeyError as e:
        raise HTTPException(404, f"unknown home {body.home_id}") from e
    return _safe(ps.model_dump(mode="json"))


@router.get("/portfolio")
def portfolio(top_n: int = Query(100, ge=1, le=500), split: Optional[str] = None,
              rank_by: Literal["improvement_potential", "fabric_potential", "carbon_per_pound",
                               "carbon_saving"] = "improvement_potential") -> dict:
    out = dict(engine_api.portfolio(top_n=top_n, split=split, rank_by=rank_by))
    mode = data_mode()
    out["data_mode"] = mode
    out["data_note"] = DATA_NOTES[mode]
    return _safe(out)


@router.get("/evidence")
def get_evidence() -> dict:
    return _safe(evidence())
