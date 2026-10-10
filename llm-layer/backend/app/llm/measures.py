"""Retrofit measure IDs, display names and the words people use for them.

The IDs and their order must match configs/retrofit_catalogue.json (P2). The
order is the documented application order: fabric first, then controls, then
the heat pump, then solar last.
"""

from __future__ import annotations

import re
from typing import Literal

MeasureId = Literal[
    "loft_insulation",
    "cavity_wall",
    "solid_wall",
    "double_glazing",
    "smart_thermostat",
    "heat_pump",
    "solar_pv",
]

MEASURE_ORDER: tuple[str, ...] = (
    "loft_insulation",
    "cavity_wall",
    "solid_wall",
    "double_glazing",
    "smart_thermostat",
    "heat_pump",
    "solar_pv",
)

DISPLAY_NAMES: dict[str, str] = {
    "loft_insulation": "loft insulation",
    "cavity_wall": "cavity wall insulation",
    "solid_wall": "solid wall insulation",
    "double_glazing": "double glazing",
    "smart_thermostat": "a smart thermostat",
    "heat_pump": "a heat pump",
    "solar_pv": "solar panels",
}

FABRIC = frozenset({"loft_insulation", "cavity_wall", "solid_wall", "double_glazing"})

# Phrases that clearly refer to one measure. Kept specific on purpose: "glazing"
# or "windows" alone also describe the home's current state, so they are not
# treated as a mention of the double_glazing retrofit.
SYNONYMS: dict[str, tuple[str, ...]] = {
    "loft_insulation": ("loft insulation", "loft", "roof insulation", "insulating the roof"),
    "cavity_wall": ("cavity wall", "cavity insulation", "cavity"),
    "solid_wall": ("solid wall insulation", "internal wall insulation", "external wall insulation"),
    "double_glazing": ("double glazing", "double-glazing", "double glazed", "double-glazed", "triple glazing"),
    "smart_thermostat": ("smart thermostat", "smart heating control", "smart control"),
    "heat_pump": ("heat pump", "air source", "ground source", "ashp", "gshp"),
    "solar_pv": ("solar", "photovoltaic", "pv"),
}

_SYNONYM_RES: dict[str, re.Pattern[str]] = {
    m: re.compile(r"\b(" + "|".join(re.escape(s) for s in syns) + r")s?\b", re.IGNORECASE)
    for m, syns in SYNONYMS.items()
}


def ordered(measures: list[str] | tuple[str, ...] | set[str]) -> list[str]:
    """Return known measures in catalogue order, dropping duplicates."""
    unique = set(measures)
    return [m for m in MEASURE_ORDER if m in unique]


def mentioned_measures(text: str) -> set[str]:
    """Measures a piece of text refers to, by name or synonym."""
    return {m for m, rx in _SYNONYM_RES.items() if rx.search(text)}


def display_name(measure: str) -> str:
    return DISPLAY_NAMES.get(measure, measure.replace("_", " "))


def measure_mentions(text: str) -> list[tuple[str, int]]:
    """(measure, start offset) for every mention, in text order."""
    hits = [(m, mt.start()) for m, rx in _SYNONYM_RES.items() for mt in rx.finditer(text)]
    return sorted(hits, key=lambda t: t[1])
