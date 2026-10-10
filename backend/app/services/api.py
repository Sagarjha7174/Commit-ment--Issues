"""Entry points for the API owner (no FastAPI here). Every number comes from scenario_builder.build().

    build(req: ScenarioRequest) -> ScenarioResult
    assess(home_id: str) -> list[FeasibilityItem]
    score(home_id: str) -> ScoreResult
    search(home_id: str, assumptions: Assumptions | None = None, threshold_pct: float = 10.0,
           budget_gbp: float | None = None, user_reading: UserReading | None = None) -> PackageSearch
    portfolio(top_n: int = 50, split: str | None = None) -> dict
"""
from __future__ import annotations

from typing import Optional

from ..data.loaders import get_home
from ..schemas.retrofit import FeasibilityItem, PackageSearch
from ..schemas.scenario import Assumptions, ScenarioRequest, ScenarioResult, ScoreResult, UserReading
from . import feasibility, packages, scenario_builder
from . import portfolio as portfolio_mod
from . import score as score_mod
from .baseline import get_baseline


def build(req: ScenarioRequest) -> ScenarioResult:
    return scenario_builder.build(req)


def assess(home_id: str) -> list[FeasibilityItem]:
    return feasibility.assess(get_home(home_id))


def score(home_id: str) -> ScoreResult:
    return score_mod.score_home(get_home(home_id))


def search(home_id: str, assumptions: Optional[Assumptions] = None, threshold_pct: float = packages.THRESHOLD_PCT,
           budget_gbp: Optional[float] = None, user_reading: Optional[UserReading] = None) -> PackageSearch:
    h = get_home(home_id)
    return packages.search(h, get_baseline(h, user_reading), feasibility.assess(h), assumptions, threshold_pct, budget_gbp)


def portfolio(top_n: int = 50, split: Optional[str] = None) -> dict:
    return portfolio_mod.portfolio(top_n, split)
