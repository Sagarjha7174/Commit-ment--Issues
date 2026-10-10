"""Small parsers for EPC description text (certificate fields, available at prediction time). Pure functions.

Wall and roof types reuse the engine's own rules (feasibility._wall_type / roof_type / loft_depth_mm) so the ML layer
and the feasibility rules never disagree about what a description means.
"""
from __future__ import annotations

import re
from types import SimpleNamespace
from typing import Optional

from ..services import feasibility

_U_RE = re.compile(r"thermal transmittance\s*=?\s*(\d+(?:\.\d+)?)", re.I)


def _norm(d: Optional[str]) -> str:
    return (d or "").strip().lower()


def u_value(d: Optional[str]) -> Optional[float]:
    """U-value (W/m²K) from 'Average thermal transmittance 0.27 W/m²K'; None otherwise or if implausible (> 5)."""
    m = _U_RE.search(d or "")
    if not m:
        return None
    v = float(m.group(1))
    return v if 0 < v <= 5 else None


# ---------------- walls ----------------

def wall_type(d: Optional[str]) -> Optional[str]:
    """cavity | solid | timber | system | other | unknown; None when there is no description."""
    t = _norm(d)
    if not t:
        return None
    ft = feasibility._wall_type(SimpleNamespace(walls_description=d))
    if ft in ("cavity", "solid"):
        return ft
    if t.startswith("timber frame"):
        return "timber"
    if t.startswith("system built"):
        return "system"
    if t.startswith("park home"):
        return "other"
    return "unknown"   # U-value only, software codes ("SAP05:Walls"), basement walls


def wall_insulation(d: Optional[str]) -> Optional[str]:
    """none | partial | filled_cavity | internal | external | insulated | unknown; None without a description."""
    t = _norm(d)
    if not t:
        return None
    if "filled cavity" in t:
        return "filled_cavity"
    if "internal insulation" in t:
        return "internal"
    if "external insulation" in t:
        return "external"
    if "partial insulation" in t:
        return "partial"
    if "no insulation" in t or "uninsulated" in t:
        return "none"
    if "insulated" in t or "additional insulation" in t:
        return "insulated"
    return "unknown"


WALL_INS_LEVEL = {"none": 0, "partial": 1, "filled_cavity": 2, "internal": 2, "external": 2, "insulated": 2}


def wall_insulation_level(d: Optional[str]) -> Optional[int]:
    """Ordered wall insulation: none 0, partial 1, insulated (any kind) 2; None when unknown."""
    return WALL_INS_LEVEL.get(wall_insulation(d) or "")


# ---------------- roof ----------------

def roof_type(d: Optional[str]) -> Optional[str]:
    """pitched | rafters | flat | roof_room | thatched | dwelling_above | unknown (engine rule, D20)."""
    return feasibility.roof_type(SimpleNamespace(roof_description=d))


def loft_mm(d: Optional[str]) -> Optional[int]:
    """Recorded loft insulation depth (mm; 0 for 'no insulation'), engine rule."""
    return feasibility.loft_depth_mm(SimpleNamespace(roof_description=d))


# ---------------- floor ----------------

def floor_type(d: Optional[str]) -> Optional[str]:
    """solid | suspended | dwelling_below | exposed | unknown; None without a description."""
    t = _norm(d)
    if not t:
        return None
    if "dwelling below" in t or "premises below" in t:
        return "dwelling_below"
    if t.startswith("solid"):
        return "solid"
    if t.startswith("suspended"):
        return "suspended"
    if t.startswith(("to unheated space", "to external air")):
        return "exposed"
    return "unknown"


def floor_insulation_level(d: Optional[str]) -> Optional[int]:
    """none 0, limited 1, insulated 2; None when unknown or another dwelling is below."""
    t = _norm(d)
    if not t or "below" in t:
        return None
    if "no insulation" in t or "uninsulated" in t:
        return 0
    if "limited insulation" in t:
        return 1
    if "insulated" in t:
        return 2
    return None


# ---------------- fuel and heating ----------------

def main_fuel(d: Optional[str]) -> Optional[str]:
    """mains_gas | electricity | oil | lpg | solid | other; None when not recorded."""
    t = _norm(d)
    if not t:
        return None
    if "mains gas" in t:
        return "mains_gas"
    if "lpg" in t:
        return "lpg"
    if re.search(r"\boil\b", t) or "b30k" in t or "biodiesel" in t:
        return "oil"
    if "electric" in t:
        return "electricity"
    if any(k in t for k in ("coal", "anthracite", "wood", "biomass", "smokeless", "dual fuel", "pellets")):
        return "solid"
    return "other"


_HEATING = (
    ("heat_pump", r"heat pump"),
    ("community", r"community scheme"),
    ("storage_heaters", r"storage heater"),
    ("boiler", r"boiler"),
    ("room_heaters", r"room heaters|portable electric heaters|no system present"),
    ("other", r"warm air|underfloor heating|electricaire|electric ceiling"),
)


def heating_family(d: Optional[str]) -> Optional[str]:
    """boiler | storage_heaters | room_heaters | heat_pump | community | other; the first system named wins."""
    t = _norm(d)
    if not t:
        return None
    best, pos = None, len(t) + 1
    for fam, pat in _HEATING:
        m = re.search(pat, t)
        if m and m.start() < pos:
            best, pos = fam, m.start()
    return best or "other"


# ---------------- certificate context ----------------

def transaction_type(d: Optional[str]) -> Optional[str]:
    """marketed_sale | non_marketed_sale | rental_private | rental_social | rental | new_dwelling | other."""
    t = _norm(d)
    if not t:
        return None
    if t.startswith(("not sale", "none of the above")):
        return "other"
    if t.startswith(("non-marketed", "non marketed")):
        return "non_marketed_sale"
    if "marketed sale" in t:
        return "marketed_sale"
    if "rental" in t:
        return "rental_social" if "social" in t else "rental_private" if "private" in t else "rental"
    if "new dwelling" in t:
        return "new_dwelling"
    return "other"


def age_mid_year(age_band: Optional[str], start: Optional[float], end: Optional[float]) -> Optional[float]:
    """Midpoint of the construction age band; 'before 1900' = 1890 (plan M1.2); implausible years -> None."""
    if age_band and age_band.strip().lower() == "before 1900":
        return 1890.0
    if start is None and end is None:
        return None
    lo = start if start is not None else end
    hi = end if end is not None else start
    mid = (lo + hi) / 2.0
    return mid if 1700 <= mid <= 2027 else None


def need_age_band(end: Optional[float]) -> Optional[int]:
    """NEED age band from the band's last year: 1 pre-1930, 2 1930-1975, 3 1976-2002, 4 2003+ (mappings/age_band.csv)."""
    if end is None:
        return None
    return 1 if end <= 1929 else 2 if end <= 1975 else 3 if end <= 2002 else 4
