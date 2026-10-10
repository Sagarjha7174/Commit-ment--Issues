"""Hand arithmetic for demo homes A, B, C -> tests/fixtures/scenario_{a,b,c}.json.

Independent of the engine: imports nothing from backend/, reads only the public demo inputs (configs/demo_homes.json)
and the documented constants, and applies the formulas in docs/SCORE.md and docs/ENGINE.md by hand.
Run: .venv/bin/python tests/fixtures/hand_calc_demo.py
"""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).resolve().parent
demo = {h["case"][0]: h for h in json.loads((ROOT / "configs/demo_homes.json").read_text())["homes"]}

# documented constants (cat-v3, engine-params-v2, score-params-v1, DESNZ 2026)
EFF, OTHER, SPACE, WATER = 0.85, 0.0305, 0.77, 0.23   # EFF: gas boiler rated Good (D18)
SCOP = 2.80                                           # Electrification of Heat median SPF (D24)
GLZ = 0.10
THERM_BY_CONTROLS = {"none": 0.10, "timer": 0.075, "full": 0.05}   # brief 5-10% placed by existing controls (D25)
CAT = {m["id"]: m for m in json.loads((ROOT / "configs/retrofit_catalogue.json").read_text())["measures"]}


def segment_impact(measure, segments):
    """Empirical-Bayes segment adjustment (D15), recomputed by hand from the published NEED segment tables."""
    import math
    spec = CAT[measure]
    shrunk = {}
    for dim, name in segments.items():
        segs = spec["impact_by_segment"][dim]["segments"]
        head = segs["All domestic properties"]["median_pct"]
        rows = {k: v for k, v in segs.items() if k != "All domestic properties" and v["status"] == "observed"}
        se = {k: 1.2533 * ((v["q3"] - v["q1"]) / 1.349) / math.sqrt(v["n"]) for k, v in rows.items()}
        dev = {k: v["median_pct"] - head for k, v in rows.items()}
        mean = sum(dev.values()) / len(dev)
        tau2 = max(0.0, sum((d - mean) ** 2 for d in dev.values()) / (len(dev) - 1) - sum(x ** 2 for x in se.values()) / len(se))
        w = tau2 / (tau2 + se[name] ** 2) if tau2 > 0 else 0.0
        shrunk[dim] = w * dev[name]
    # "max" rule (D15 rev.): region + the single largest non-region adjustment
    others = [v for k, v in shrunk.items() if k != "region"]
    total = shrunk.get("region", 0.0) + (max(others, key=abs) if others else 0.0)
    return max(spec["impact"]["mid"] + total, 0.0)


# demo A segments: EPC E -> "E-G", 1967-1975 (midpoint 1971) -> "1965-82", detached house, York
SEG_A = {"epc_rating": "E-G", "property_age": "1965-82", "property_type": "Detached", "region": "Yorkshire and the Humber"}
LOFT, CAV, PV = (segment_impact(m, SEG_A) for m in ("loft_insulation", "cavity_wall", "solar_pv"))
EF_GAS, EF_ELEC = 0.18231, 0.14395
P10, P90 = 75.749, 186.022

# ---------- demo A: 1967-75 detached house, gas boiler, cavity walls Poor, roof Very Poor, partial 87% ----------
# Its certificate's roof description is "Flat, limited insulation (assumed)": a flat roof has no loft, so loft
# insulation is infeasible (D20) and the roof stays Very Poor after the package.
pa = demo["a"]["public_fields"]
G, E, AREA = pa["baseline_gas_kwh"], pa["baseline_elec_kwh"], pa["floor_area_m2"]
THERM = THERM_BY_CONTROLS[pa["controls"]]   # demo A has 'full' controls -> 5%
other = OTHER * G
hw = G - other
space, water = SPACE * hw, WATER * hw
# standalone
loft_alone = LOFT * G
cav_alone = CAV * G
glz_alone = GLZ * (1 - 0.87) * space
therm_alone = THERM * space
hp_alone_gas = hw
hp_alone_elec = -(hw * EFF / SCOP)
pv_alone = PV * E
# full feasible package, fixed order
s1 = space        # no loft step (flat roof, D20)
g1 = G
s2 = s1 - CAV * g1
s3 = s2 * (1 - GLZ * (1 - 0.87))
s4 = s3 * (1 - THERM)
hp_elec = (s4 + water) * EFF / SCOP
pv = PV * E   # PV on baseline electricity, not on heat-pump electricity (D19)
gas_saving = G - other
elec_saving = -hp_elec + pv
purchased_before = G + E
purchased_after = other + E + hp_elec - pv
ip = 100 * (purchased_before - purchased_after) / purchased_before
carbon = gas_saving * EF_GAS + elec_saving * EF_ELEC
x = (G + E) / AREA
s_int = 100 * (P90 - x) / (P90 - P10)
s_ins = (0.5 * 30 + 0.35 * 10) / 0.85
score_raw = 0.25 * 48 + 0.20 * s_int + 0.15 * s_ins + 0.15 * 80 + 0.10 * (10 + 65 * 0.87) + 0.10 * 0 + 0.05 * 70
# after score: EPC unchanged 48; intensity from after energy; insulation walls Good 80, roof stays Very Poor 10 (no loft
# measure), floor N/A -> (0.5*80 + 0.35*10)/0.85; heating Good 80 (HP floor 75);
# windows double 75; renewables some PV 60; controls smart 100
x_after = purchased_after / AREA
s_int_after = min(max(100 * (P90 - x_after) / (P90 - P10), 0), 100)
s_ins_after = (0.5 * 80 + 0.35 * 10) / 0.85
after_raw = 0.25 * 48 + 0.20 * s_int_after + 0.15 * s_ins_after + 0.15 * 80 + 0.10 * 75 + 0.10 * 60 + 0.05 * 100

A = {
    "home_id": demo["a"]["home_id"],
    "expect": {
        "score_before": 44, "score_before_raw": score_raw, "class_before": "Poor",
        "impacts_used": {"loft_insulation": LOFT, "cavity_wall": CAV, "solar_pv": PV, "smart_thermostat": THERM, "scop": SCOP},
        "score_after_raw": after_raw, "score_after": int(after_raw + 0.5),
        "end_uses_before": {"gas_space": space, "gas_water": water, "gas_other": other, "elec_base": E},
        "standalone_gas_saving_kwh": {"cavity_wall": cav_alone, "double_glazing": glz_alone,
                                      "smart_thermostat": therm_alone, "heat_pump": hp_alone_gas, "solar_pv": 0.0},
        "standalone_elec_saving_kwh": {"cavity_wall": 0.0, "double_glazing": 0.0,
                                       "smart_thermostat": 0.0, "heat_pump": hp_alone_elec, "solar_pv": pv_alone},
        "package_gas_saving_kwh": gas_saving, "package_elec_saving_kwh": elec_saving,
        "improvement_potential_pct": ip, "carbon_saving_kg": carbon,
        "feasible": ["cavity_wall", "double_glazing", "smart_thermostat", "heat_pump", "solar_pv"],
        "infeasible": ["loft_insulation", "solid_wall"],
    },
}

# ---------- demo B: 2003-06 flat, electric heating, no mains gas ----------
pb = demo["b"]["public_fields"]
xb = (pb["baseline_gas_kwh"] + pb["baseline_elec_kwh"]) / pb["floor_area_m2"]
sb_int = 100 * (P90 - xb) / (P90 - P10)
b_raw = 0.25 * 81 + 0.20 * sb_int + 0.15 * 80 + 0.15 * 10 + 0.10 * 75 + 0.10 * 0 + 0.05 * 40
B = {
    "home_id": demo["b"]["home_id"],
    "expect": {
        "score_before_raw": b_raw, "score_before": int(b_raw + 0.5), "class_before": "Moderate",
        "baseline_gas_kwh": 0.0, "baseline_elec_kwh": pb["baseline_elec_kwh"],
        "infeasible": ["loft_insulation", "cavity_wall", "solid_wall", "double_glazing", "solar_pv"],
        "feasible": ["smart_thermostat", "heat_pump"],
        "not_estimated": {"smart_thermostat": "heating_not_on_gas", "heat_pump": "no_gas_to_displace"},
        "improvement_potential_status": "not_estimated",
    },
}

# ---------- demo C: missing data ----------
C = {
    "home_id": demo["c"]["home_id"],
    "expect": {
        "score_status": "unavailable", "completeness": "1/7",
        "baseline_gas_kwh": None, "baseline_elec_kwh": None,
        "improvement_potential_status": "unavailable",
        "needs_verification": ["loft_insulation", "cavity_wall", "solid_wall", "double_glazing", "smart_thermostat", "heat_pump", "solar_pv"],
    },
}

for name, d in (("a", A), ("b", B), ("c", C)):
    d["generated_by"] = "tests/fixtures/hand_calc_demo.py (hand arithmetic, no engine imports)"
    (OUT / f"scenario_{name}.json").write_text(json.dumps(d, indent=1))
    print("wrote", f"scenario_{name}.json")
