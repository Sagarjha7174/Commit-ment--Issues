"""Run the team's engine (services/scenario_builder) for the LLM layer: explanations and what-if reruns.

    from backend.app.llm.engine import run_scenario
    result = run_scenario("U100050529765", ["loft_insulation", "heat_pump"])   # York data under data/processed

Homes come from the engine's own loader (York data) unless a home source is set, e.g. the synthetic test homes
in eval/synthetic_homes.py: set_home_source(synthetic_homes.get).
"""

from __future__ import annotations

from typing import Any, Callable, Optional

_home_source: Optional[Callable[[str], Any]] = None


def set_home_source(source: Optional[Callable[[str], Any]]) -> None:
    """source(home_id) -> HomeRecord; None = the engine's York data loader."""
    global _home_source
    _home_source = source


def run_scenario(home_id: str, measures: Optional[list[str]] = None, include_packages: bool = True) -> dict:
    """Engine ScenarioResult as a JSON dict. measures=None: every feasible / needs-verification measure."""
    from ..schemas.scenario import ScenarioRequest
    from ..services import scenario_builder  # imported lazily: the engine needs pandas

    home = _home_source(home_id) if _home_source else None
    request = ScenarioRequest(home_id=home_id, measures=measures, include_packages=include_packages)
    return scenario_builder.build(request, home).model_dump(mode="json")
