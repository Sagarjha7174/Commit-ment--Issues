"""Build the refined regional dataset for the Lloyds PS2 Green Home Score project.

Usage:  .venv/bin/python pipelines/build_region.py
Reads dataset/ (never writes there) and data/processed/{need_4m,need_50k,ppd}.parquet.
Writes everything to OUT_DIR. Deterministic: rerunning gives identical outputs; the
script compares its fingerprint with the previous run's and fails if they differ.
"""
from __future__ import annotations

import hashlib
import json
import re
import sys
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd
import pyarrow as pa
from rapidfuzz import fuzz

sys.path.insert(0, str(Path(__file__).parent))
from epc_stream import header, members, stream_filter  # noqa: E402

# ---------------- parameters ----------------
REGION_NAME = "York"
LA_CODE = "E06000014"
PPD_DISTRICT = "YORK"
SEED = 42
ROOT = Path(__file__).resolve().parents[1]
OUT_DIR = ROOT / "data" / "processed" / "region=york"
EPC_ZIP = ROOT / "dataset" / "epc" / "domestic-csv.zip"
NEED_META = ROOT / "dataset" / "NEED-2026-anonymised-dataset-metadata.ods"  # brief said dataset/need/; actual location
ACCESS_DATE = "2026-10-10"
FUZZY_MIN, AMBIG_GAP, BENCH_MIN_N = 90, 3, 30

CERT_COLS = [
    "certificate_number", "uprn", "uprn_source", "address1", "address2", "address3", "address", "postcode", "posttown",
    "local_authority", "local_authority_label", "region", "lodgement_date", "inspection_date", "transaction_type",
    "tenure", "property_type", "built_form", "construction_age_band", "total_floor_area", "number_habitable_rooms",
    "current_energy_rating", "current_energy_efficiency", "potential_energy_rating", "potential_energy_efficiency",
    "energy_consumption_current", "co2_emissions_current", "walls_description", "walls_energy_eff",
    "roof_description", "roof_energy_eff", "floor_description", "floor_energy_eff", "windows_description",
    "windows_energy_eff", "glazed_type", "multi_glaze_proportion", "main_fuel", "mainheat_description",
    "mainheat_energy_eff", "mainheatcont_description", "mainheatc_energy_eff", "mains_gas_flag", "photo_supply",
    "solar_water_heating_flag", "wind_turbine_count",
]
RATINGS = ["Very Poor", "Poor", "Average", "Good", "Very Good"]

report: dict = {"parameters": {"region": REGION_NAME, "la_code": LA_CODE, "ppd_district": PPD_DISTRICT, "seed": SEED},
                "steps": {}}


def log(step: str, key: str, value):
    report["steps"].setdefault(step, {})[key] = value
    print(f"[{step}] {key}: {value}", flush=True)


# ---------------- normalisation helpers ----------------
def norm_text(s: pd.Series) -> pd.Series:
    s = s.fillna("").astype(str).str.upper()
    s = s.str.replace(r"\b(APARTMENT|APT)\b", "FLAT", regex=True)
    s = s.str.replace(r"[^A-Z0-9 ]", " ", regex=True)
    s = s.str.replace(r"(?<=\d) (?=[A-Z]\b)", "", regex=True)  # "12 A" -> "12A"
    return s.str.replace(r"\s+", " ", regex=True).str.strip()


def norm_postcode(s: pd.Series) -> pd.Series:
    return s.fillna("").astype(str).str.upper().str.replace(r"\s+", "", regex=True)


def stable_hash(s: str, n: int = 16) -> str:
    return hashlib.sha256(s.encode()).hexdigest()[:n]


def num(s: pd.Series) -> pd.Series:
    return pd.to_numeric(s, errors="coerce")


# ---------------- canonical mappings (documented in mappings/) ----------------
def map_rating(s: pd.Series) -> pd.Series:
    t = s.str.strip().str.title()
    return t.where(t.isin(RATINGS))


def rating_status(s: pd.Series) -> pd.Series:
    t = s.fillna("").str.strip().str.upper()
    return np.select([t.isin([r.upper() for r in RATINGS]), t.eq("N/A"), t.eq("")], ["observed", "not_applicable", "missing"],
                     default="invalid")


def map_glazing(glazed_type: pd.Series, windows: pd.Series, prop: pd.Series) -> pd.Series:
    g, w, p = glazed_type.fillna("").str.lower(), windows.fillna("").str.lower(), num(prop)
    single = g.str.contains("single") | w.str.startswith("single") | p.eq(0)
    partial = w.str.contains(r"^(?:partial|some|mostly)") | p.between(1, 99)
    triple = g.str.contains("triple") | w.str.contains("fully triple")
    double = g.str.contains("double|secondary") | w.str.contains("double|secondary|multiple|high performance") | p.eq(100)
    out = np.select([triple & ~partial, partial, single & ~double, double], ["triple", "partial", "single", "double"], default="")
    return pd.Series(out, index=glazed_type.index).replace("", np.nan)


def map_heating(desc: pd.Series, fuel: pd.Series) -> pd.Series:
    t = (desc.fillna("") + " " + fuel.fillna("")).str.lower().str.replace("not community", "", regex=False)
    first = desc.fillna("").str.lower().str.split(",").str[0]  # main system = first listed
    conds = [
        t.str.contains("heat pump") & first.str.contains("heat pump"),
        t.str.contains("community"),
        t.str.contains(r"\boil\b|heating oil|b30k"),
        t.str.contains(r"\blpg\b|coal|anthracite|wood|biomass|dual fuel|smokeless"),
        t.str.contains("mains gas|gas: mains gas") & ~first.str.contains("electric"),
        t.str.contains("electric"),
    ]
    out = np.select(conds, ["heat_pump", "other", "oil", "other", "gas_boiler", "electric"], default="")
    out = pd.Series(out, index=desc.index)
    out[(desc.fillna("").str.strip() == "") | desc.fillna("").str.startswith("SAP05")] = ""
    return out.replace("", np.nan)


CONTROLS_RULES = [  # (regex on lower-case description, level); first match wins
    (r"temperature zone control|smart", "smart"),
    (r"^none$|no time or thermostatic|no thermostatic control|^manual charge|flat rate charging, no", "none"),
    (r"(?:programmer|charging system linked).*(?:room thermostat|room stat|trvs)|room thermostat and trvs|"
     r"automatic charge control|celect|high heat retention|boiler energy manager|programmer.*bypass", "full"),
    (r"programmer|room thermostat|trvs|appliance thermostat|flat rate charging", "timer"),
]


def map_controls(desc: pd.Series) -> pd.Series:
    d = desc.fillna("").str.lower().str.strip()
    out = pd.Series(np.nan, index=desc.index, dtype=object)
    for pat, level in CONTROLS_RULES:
        m = out.isna() & d.str.contains(pat, regex=True) & ~d.str.startswith("sap05")
        out[m] = level
    return out


def map_age(band: pd.Series) -> pd.DataFrame:
    b = band.fillna("").str.replace("England and Wales:", "", regex=False).str.strip()
    start = pd.Series(np.nan, index=band.index)
    end = pd.Series(np.nan, index=band.index)
    pre = b.str.lower().str.contains("before 1900|pre-1900")
    start[pre], end[pre] = 1850, 1899
    rng = b.str.extract(r"^(\d{4})\s*-\s*(\d{4})$").astype(float)
    start = start.fillna(rng[0]); end = end.fillna(rng[1])
    onw = b.str.extract(r"^(\d{4}) onwards$")[0].astype(float)
    start = start.fillna(onw); end = end.fillna(onw.where(onw.isna(), 2026))
    yr = b.str.extract(r"^(\d{4})$")[0].astype(float)
    start = start.fillna(yr); end = end.fillna(yr)
    canon = np.where(start.notna(), b.where(~pre, "before 1900"), np.nan)
    mid = (start + end) / 2
    need = pd.cut(mid, [-np.inf, 1929.99, 1972.99, 1999.99, np.inf], labels=[1, 2, 3, 4]).astype("Int64")
    return pd.DataFrame({"age_band": canon, "age_start": start, "age_end": end, "need_age_band": need})


def map_need_property_type(ptype: pd.Series, form: pd.Series) -> pd.Series:
    p, f = ptype.fillna("").str.lower(), form.fillna("").str.lower()
    out = np.select(
        [p.eq("bungalow"), p.isin(["flat", "maisonette"]), p.eq("house") & f.str.contains("semi"),
         p.eq("house") & f.str.contains("mid"), p.eq("house") & f.str.contains("end"), p.eq("house") & f.eq("detached")],
        ["Bungalow", "Flat", "Semi detached", "Mid terrace", "End terrace", "Detached"], default="")
    return pd.Series(out, index=ptype.index).replace("", np.nan)


def map_floor_band(area: pd.Series) -> pd.Series:
    return pd.cut(area, [0, 50, 100, 150, 200, np.inf], labels=[1, 2, 3, 4, 5], right=True).astype("Int64")


def canonicalise(c: pd.DataFrame) -> pd.DataFrame:
    """Canonical columns for any set of certificates (used for history and current state)."""
    o = pd.DataFrame(index=c.index)
    o["rating"] = c["current_energy_rating"].str.strip().str.upper().where(lambda s: s.isin(list("ABCDEFG")))
    o["sap_score"] = num(c["current_energy_efficiency"])
    o["potential_rating"] = c["potential_energy_rating"].str.strip().str.upper().where(lambda s: s.isin(list("ABCDEFG")))
    o["potential_sap"] = num(c["potential_energy_efficiency"])
    o["floor_area_m2"] = num(c["total_floor_area"]).where(lambda s: s > 0)
    o["property_type"] = c["property_type"].where(c["property_type"].isin(["House", "Flat", "Bungalow", "Maisonette", "Park home"]))
    o["built_form"] = c["built_form"].where(~c["built_form"].isin(["Not Recorded", "NO DATA!"]))
    o = o.join(map_age(c["construction_age_band"]))
    for part in ("walls", "roof", "floor", "windows"):
        o[f"{part}_rating"] = map_rating(c[f"{part}_energy_eff"])
        o[f"{part}_rating_status"] = rating_status(c[f"{part}_energy_eff"])
    o["glazing"] = map_glazing(c["glazed_type"], c["windows_description"], c["multi_glaze_proportion"])
    o["multi_glaze_pct"] = num(c["multi_glaze_proportion"])
    o["heating_type"] = map_heating(c["mainheat_description"], c["main_fuel"])
    o["heating_rating"] = map_rating(c["mainheat_energy_eff"])
    o["controls"] = map_controls(c["mainheatcont_description"])
    pv = num(c["photo_supply"])
    o["solar_pv"] = pv.gt(0).where(pv.notna()).astype("boolean")
    o["solar_pv_roof_pct"] = pv.where(pv > 0)
    o["mains_gas"] = c["mains_gas_flag"].map({"Y": True, "N": False}).astype("boolean")
    ec = num(c["energy_consumption_current"])
    rating_a = c["current_energy_rating"].str.strip().str.upper().eq("A")
    bad_zero = ec.eq(0) & ~rating_a  # zero predicted use is implausible below band A
    o["epc_predicted_consumption_kwh_m2_primary"] = ec.where(~bad_zero)
    o["epc_predicted_consumption_status"] = np.select(
        [ec.isna(), bad_zero, ec <= 0], ["missing", "invalid_zero_set_missing", "observed_net_zero_or_negative"], default="observed")
    o["lodgement_date"] = pd.to_datetime(c["lodgement_date"], errors="coerce")
    return o


# ---------------- steps ----------------
def step1_extract() -> pd.DataFrame:
    tabs = []
    for m in members(EPC_ZIP, "certificates-"):
        t = stream_filter(EPC_ZIP, m, CERT_COLS, "local_authority", {LA_CODE})
        tabs.append(t.append_column("source_member", pa.array([m] * len(t), pa.string())))
        log("1_extract", m, len(t))
    df = pa.concat_tables(tabs).to_pandas()
    df = df.sort_values(["lodgement_date", "certificate_number"], kind="mergesort").reset_index(drop=True)
    log("1_extract", "certificates_total", len(df))
    dup = df.duplicated("certificate_number")
    log("1_extract", "dropped_duplicate_certificate_number", int(dup.sum()))
    return df[~dup].reset_index(drop=True)


def property_ids(c: pd.DataFrame) -> pd.Series:
    uprn = c["uprn"].fillna("").str.replace(r"\.0$", "", regex=True).str.strip()
    addr = norm_text(c["address1"].fillna("") + " " + c["address2"].fillna("") + " " + c["address3"].fillna(""))
    key = addr + "|" + norm_postcode(c["postcode"])
    return pd.Series(np.where(uprn != "", "U" + uprn, "A" + key.map(stable_hash)), index=c.index)


def step2_history(certs: pd.DataFrame, canon: pd.DataFrame) -> pd.DataFrame:
    fields = ["glazing", "walls_rating", "roof_rating", "heating_type", "controls", "solar_pv"]
    h = pd.concat([certs[["property_id", "certificate_number"]], canon[["lodgement_date", *fields]]], axis=1)
    h = h.sort_values(["property_id", "lodgement_date", "certificate_number"], kind="mergesort")
    prev = h.groupby("property_id")[["lodgement_date", *fields]].shift(1)
    rows = []
    for f in fields:
        changed = prev["lodgement_date"].notna() & prev[f].notna() & h[f].notna() & (prev[f].astype(str) != h[f].astype(str))
        rows.append(pd.DataFrame({"property_id": h.loc[changed, "property_id"], "from_date": prev.loc[changed, "lodgement_date"],
                                  "to_date": h.loc[changed, "lodgement_date"], "field": f,
                                  "old": prev.loc[changed, f].astype(str), "new": h.loc[changed, f].astype(str)}))
    out = pd.concat(rows).sort_values(["property_id", "to_date", "field"]).reset_index(drop=True)
    log("2_dedupe", "history_changes", len(out))
    log("2_dedupe", "history_properties_with_changes", int(out.property_id.nunique()))
    return out


IMPROVEMENT_MEASURE = {  # EPC improvement_id -> our measure (see mappings/improvement_to_measure.csv)
    "loft_insulation": [5, 45, 46], "cavity_wall": [6], "solid_wall": [7, 55, 65, 66],
    "double_glazing": [8, 9, 56], "smart_thermostat": [11, 12, 13, 14, 15, 16, 17, 18],
    "heat_pump": [51, 52, 75, 76], "solar_pv": [34],
}
MEASURES = list(IMPROVEMENT_MEASURE)
TEXT_FALLBACK = [("loft_insulation", r"loft|roof insulation|room-in-roof|sloping ceiling"), ("cavity_wall", r"cavity wall insulation$"),
                 ("solid_wall", r"internal or external wall|external wall insulation|internal wall insulation"),
                 ("double_glazing", r"double glaz|glazing units|secondary glazing"), ("smart_thermostat", r"heating controls|zone control|thermostat"),
                 ("heat_pump", r"heat pump"), ("solar_pv", r"photovoltaic")]


def improvement_mapping() -> pd.DataFrame:
    codes = json.loads((ROOT / "configs" / "epc_codes.json").read_text())["improvement_summary"]
    by_id = {i: m for m, ids in IMPROVEMENT_MEASURE.items() for i in ids}
    rows = [{"improvement_id": int(k), "improvement_summary": v, "measure": by_id.get(int(k), "other")}
            for k, v in codes.items() if k.isdigit()]
    return pd.DataFrame(rows).sort_values("improvement_id").reset_index(drop=True)


def step4_recommendations(latest_keys: set, homes: pd.DataFrame, mapping: pd.DataFrame):
    cols = ["certificate_number", "improvement_item", "improvement_id", "improvement_summary_text", "indicative_cost"]
    tabs = []
    for m in members(EPC_ZIP, "recommendations-"):
        t = stream_filter(EPC_ZIP, m, cols, "certificate_number", latest_keys)
        tabs.append(t)
        log("4_recommendations", m, len(t))
    r = pa.concat_tables(tabs).to_pandas()
    r["improvement_id"] = num(r["improvement_id"]).astype("Int64")
    r["improvement_item"] = num(r["improvement_item"]).astype("Int64")
    r = r.merge(mapping[["improvement_id", "measure"]], on="improvement_id", how="left")
    r["mapping_source"] = np.where(r["measure"].notna(), "improvement_id", "")
    txt = r["improvement_summary_text"].fillna("").str.lower()
    for meas, pat in TEXT_FALLBACK:
        m = r["measure"].isna() & txt.str.contains(pat, regex=True)
        r.loc[m, "measure"], r.loc[m, "mapping_source"] = meas, "summary_text"
    r["measure"] = r["measure"].fillna("other")
    r.loc[r["mapping_source"] == "", "mapping_source"] = "unmapped_other"
    r = r.merge(homes[["certificate_number", "property_id"]], on="certificate_number", how="left")
    r = r.sort_values(["property_id", "improvement_item", "improvement_id"]).reset_index(drop=True)
    log("4_recommendations", "rows", len(r))
    log("4_recommendations", "measure_counts", r["measure"].value_counts().to_dict())
    log("4_recommendations", "mapping_source_counts", r["mapping_source"].value_counts().to_dict())
    wide = homes[["property_id"]].copy()
    flags = pd.crosstab(r["property_id"], r["measure"]).clip(upper=1)
    for m in MEASURES + ["other"]:
        wide[f"rec_{m}"] = wide["property_id"].map(flags[m] if m in flags else pd.Series(dtype=int)).fillna(0).astype(int)
    wide["n_recommendations"] = wide["property_id"].map(r.groupby("property_id").size()).fillna(0).astype(int)
    wide["has_recommendations"] = wide["n_recommendations"] > 0
    log("4_recommendations", "properties_with_any_recommendation", int(wide["has_recommendations"].sum()))
    return r, wide


def numbers_key(addr: str) -> tuple:
    return tuple(sorted(re.findall(r"\b\d+[A-Z]?\b", addr)))


def sale_address(p: pd.DataFrame) -> pd.Series:
    return norm_text(p["saon"].fillna("") + " " + p["paon"].fillna("") + " " + p["street"].fillna(""))


def step5_sales(homes: pd.DataFrame, certs: pd.DataFrame, canon: pd.DataFrame) -> pd.DataFrame:
    ppd = pd.read_parquet(ROOT / "data" / "processed" / "ppd.parquet")
    log("5_sales", "ppd_rows_all", len(ppd))
    s = ppd[ppd["district"] == PPD_DISTRICT].copy()
    log("5_sales", "ppd_rows_district", len(s))
    log("5_sales", "category_filter_note", "ppd.parquet already restricted to category A, record_status != D, type != O")
    s = s.sort_values(["date", "transaction_id"]).reset_index(drop=True)
    s["sale_addr"] = sale_address(s)
    s["sale_addr_loc"] = norm_text(s["saon"].fillna("") + " " + s["paon"].fillna("") + " " + s["street"].fillna("") + " "
                                   + s["locality"].fillna(""))
    s["pc"] = norm_postcode(s["postcode"])
    h = homes[["property_id", "postcode", "raw_address1", "raw_address2", "raw_address3"]].copy()
    a1, a2, a3 = (h[f"raw_address{i}"].fillna("") for i in (1, 2, 3))
    h["pc"] = norm_postcode(h["postcode"])
    h["v1"], h["v2"], h["v3"] = norm_text(a1), norm_text(a1 + " " + a2), norm_text(a1 + " " + a2 + " " + a3)
    h["epc_addr"] = h["v3"]
    h["nums"] = h["v2"].map(numbers_key)
    by_pc = {k: g for k, g in h.groupby("pc")}
    res = []
    for row in s.itertuples():
        cand = by_pc.get(row.pc)
        rec = {"transaction_id": row.transaction_id, "property_id": None, "match_status": "unmatched",
               "match_method": None, "match_score": np.nan, "epc_address": None}
        sale_vars = {row.sale_addr, row.sale_addr_loc}
        if cand is None or not row.pc:
            rec["match_method"] = "no_epc_in_postcode"
        else:
            exact = cand[cand.v1.isin(sale_vars) | cand.v2.isin(sale_vars) | cand.v3.isin(sale_vars)]
            if exact.property_id.nunique() == 1:
                rec.update(property_id=exact.property_id.iloc[0], match_status="linked", match_method="exact", match_score=100.0,
                           epc_address=exact.epc_addr.iloc[0])
            elif exact.property_id.nunique() > 1:
                rec.update(match_status="ambiguous", match_method="exact_multiple", match_score=100.0)
            else:
                # fuzzy only among candidates with identical house/flat numbers (prevents 2 vs 12 Chaucer St)
                same = cand[cand.nums == numbers_key(row.sale_addr)]
                if same.empty:
                    rec["match_method"] = "no_candidate_same_numbers"
                else:
                    sc = np.array([max(fuzz.token_sort_ratio(sv, v) for sv in sale_vars for v in (r1, r2, r3))
                                   for r1, r2, r3 in zip(same.v1, same.v2, same.v3)])
                    order = np.argsort(-sc, kind="mergesort")
                    best = sc[order[0]]
                    second = sc[order[1]] if len(sc) > 1 else -1
                    rec["match_score"] = float(best)
                    if best < FUZZY_MIN:
                        rec["match_method"] = "below_threshold"
                    elif second >= best - AMBIG_GAP:
                        rec.update(match_status="ambiguous", match_method="fuzzy")
                    else:
                        c = same.iloc[order[0]]
                        rec.update(property_id=c.property_id, match_status="linked", match_method="fuzzy", epc_address=c.epc_addr)
        res.append(rec)
    m = s.merge(pd.DataFrame(res), on="transaction_id", how="left")
    # rating at sale: latest certificate for that property lodged on/before the sale date (no future leakage)
    hist = pd.concat([certs[["property_id", "certificate_number"]], canon[["lodgement_date", "rating", "sap_score"]]], axis=1)
    hist = hist.dropna(subset=["lodgement_date"]).sort_values(["lodgement_date", "certificate_number"])
    m["sale_date"] = pd.to_datetime(m["date"]).astype("datetime64[ns]")
    hist["lodgement_date"] = hist["lodgement_date"].astype("datetime64[ns]")
    linked = m[m.match_status == "linked"].sort_values("sale_date")
    at = pd.merge_asof(linked[["transaction_id", "property_id", "sale_date"]], hist.rename(columns={"lodgement_date": "sale_date_epc"}),
                       left_on="sale_date", right_on="sale_date_epc", by="property_id", direction="backward")
    at = at.rename(columns={"certificate_number": "epc_cert_at_sale", "sale_date_epc": "epc_lodged_at_sale",
                            "rating": "epc_rating_at_sale", "sap_score": "epc_sap_at_sale"})
    m = m.merge(at[["transaction_id", "epc_cert_at_sale", "epc_lodged_at_sale", "epc_rating_at_sale", "epc_sap_at_sale"]],
                on="transaction_id", how="left")
    m["epc_rating_at_sale_status"] = np.select(
        [m.match_status != "linked", m.epc_rating_at_sale.notna()], ["no_link", "observed"], default="unavailable_no_epc_before_sale")
    assert (m.epc_lodged_at_sale.isna() | (m.epc_lodged_at_sale <= m.sale_date)).all(), "future leakage"
    m = m.drop(columns=["pc"]).rename(columns={"date": "sale_date_raw"})
    log("5_sales", "match_status", m.match_status.value_counts().to_dict())
    log("5_sales", "match_method", m.match_method.value_counts(dropna=False).to_dict())
    log("5_sales", "linked", int((m.match_status == "linked").sum()))
    log("5_sales", "linked_with_rating_at_sale", int((m.epc_rating_at_sale_status == "observed").sum()))
    return m


def step6_benchmarks() -> tuple[pd.DataFrame, str]:
    src = "need_4m" if (ROOT / "data/processed/need_4m.parquet").exists() else "need_50k"
    n = pd.read_parquet(ROOT / f"data/processed/{src}.parquet")
    n = n[n.region_code == "E12000003"].copy()
    log("6_benchmarks", "source", src)
    log("6_benchmarks", "need_rows_region", len(n))
    n["need_main_fuel"] = np.where(n.main_heat_gas == 1, 1, 2)
    n["need_property_type"], n["need_epc_band"], n["need_floor_area_band"] = n.property_type, n.epc_band, n.floor_area_band_code
    levels = {"L1_fuel_type_epc_area": ["need_main_fuel", "need_property_type", "need_epc_band", "need_floor_area_band"],
              "L2_fuel_type_epc": ["need_main_fuel", "need_property_type", "need_epc_band"],
              "L3_fuel_epc": ["need_main_fuel", "need_epc_band"]}
    out = []
    for fuel, cond in (("gas", (n.gas_status == "metered") & (n.main_heat_gas == 1)), ("elec", n.elec_status == "metered")):
        d = n[cond & n.need_epc_band.notna()]
        log("6_benchmarks", f"{fuel}_rows_valid", len(d))
        for lvl, keys in levels.items():
            g = d.groupby(keys)[f"{fuel}_kwh"]
            b = pd.DataFrame({"median": g.median(), "q1": g.quantile(0.25), "q3": g.quantile(0.75), "n": g.size()}).reset_index()
            b["fuel"], b["level"] = fuel, lvl
            out.append(b)
    return pd.concat(out, ignore_index=True), src


def step7_baselines(homes: pd.DataFrame, bench: pd.DataFrame) -> pd.DataFrame:
    levels = [("L1_fuel_type_epc_area", ["need_main_fuel", "need_property_type", "need_epc_band", "need_floor_area_band"]),
              ("L2_fuel_type_epc", ["need_main_fuel", "need_property_type", "need_epc_band"]),
              ("L3_fuel_epc", ["need_main_fuel", "need_epc_band"])]
    for fuel in ("gas", "elec"):
        val = pd.Series(np.nan, index=homes.index)
        lvl_used = pd.Series(np.nan, index=homes.index, dtype=object)
        n_used = pd.Series(np.nan, index=homes.index)
        for lvl, keys in levels:
            b = bench[(bench.fuel == fuel) & (bench.level == lvl) & (bench.n >= BENCH_MIN_N)]
            j = homes[keys].merge(b[keys + ["median", "n"]], on=keys, how="left")
            j.index = homes.index
            fill = val.isna() & j["median"].notna()
            val[fill], lvl_used[fill], n_used[fill] = j["median"][fill], lvl, j["n"][fill]
        homes[f"baseline_{fuel}_kwh"], homes[f"{fuel}_benchmark_level"], homes[f"{fuel}_benchmark_n"] = val, lvl_used, n_used
    b = lambda x: pd.Series(x, index=homes.index).fillna(False).astype(bool)  # noqa: E731
    gas_heated = b(homes.need_main_fuel.eq(1))
    no_gas = b(homes.mains_gas.eq(False))
    homes["flag_conflict_gas_heating_no_mains_gas"] = gas_heated & no_gas
    log("7_baselines", "conflict_gas_boiler_but_no_mains_gas", int((gas_heated & no_gas).sum()))
    homes["gas_status"] = np.select(
        [no_gas, gas_heated & homes.baseline_gas_kwh.notna(), b(homes.mains_gas.eq(True)) & ~gas_heated,
         homes.mains_gas.isna().to_numpy() & ~gas_heated],
        ["no_mains_gas", "population_benchmark", "gas_supply_not_main_heating_no_benchmark", "unknown_mains_gas"],
        default="unavailable")
    homes.loc[no_gas, "baseline_gas_kwh"] = 0.0
    homes.loc[no_gas, ["gas_benchmark_level", "gas_benchmark_n"]] = np.nan
    homes.loc[~gas_heated & ~no_gas, "baseline_gas_kwh"] = np.nan
    homes["elec_status"] = np.where(homes.baseline_elec_kwh.notna(), "population_benchmark", "unavailable")
    homes["baseline_source"] = "population_benchmark"
    homes["modelled_gas_kwh"] = pd.Series(np.nan, index=homes.index, dtype=float)
    homes["modelled_elec_kwh"] = pd.Series(np.nan, index=homes.index, dtype=float)
    log("7_baselines", "gas_status", homes.gas_status.value_counts().to_dict())
    log("7_baselines", "elec_status", homes.elec_status.value_counts().to_dict())
    log("7_baselines", "gas_level", homes.gas_benchmark_level.value_counts(dropna=False).to_dict())
    log("7_baselines", "elec_level", homes.elec_benchmark_level.value_counts(dropna=False).to_dict())
    return homes


def split_for(ids: pd.Series) -> pd.Series:
    u = ids.map(lambda x: int(stable_hash(f"{SEED}:{x}", 12), 16) / 16 ** 12)
    return pd.Series(np.select([u < 0.70, u < 0.85], ["train", "val"], default="test"), index=ids.index)


# ---------------- provenance & docs ----------------
PROVENANCE = {
    "property_id": ("-", "observed", "UPRN (prefix U) or sha256 of normalised address+postcode (prefix A)"),
    "certificate_number": ("-", "observed", "latest certificate"), "uprn": ("-", "observed", ""),
    "address": ("-", "observed", "EPC address"), "postcode": ("-", "observed", ""),
    "lodgement_date": ("date", "observed", "latest certificate lodgement"), "n_certificates": ("count", "observed", ""),
    "rating": ("A-G", "observed", "current_energy_rating"), "sap_score": ("SAP points 1-100+", "observed", "current_energy_efficiency"),
    "potential_rating": ("A-G", "modelled", "assessor software potential rating"),
    "potential_sap": ("SAP points", "modelled", "potential_energy_efficiency"),
    "floor_area_m2": ("m2", "observed", "total_floor_area; values <=0 set missing"),
    "property_type": ("category", "observed", ""), "built_form": ("category", "observed", "'Not Recorded' -> missing"),
    "age_band": ("text", "observed", "construction_age_band with 'England and Wales:' prefix removed"),
    "age_start": ("year", "observed", "parsed from age band"), "age_end": ("year", "assumption", "'onwards' bands end at 2026; pre-1900 starts 1850"),
    "walls_rating": ("Very Poor..Very Good", "observed", ""), "roof_rating": ("Very Poor..Very Good", "observed", "N/A = another dwelling above"),
    "floor_rating": ("Very Poor..Very Good", "observed", "mostly N/A in EPC (not rated in RdSAP)"),
    "windows_rating": ("Very Poor..Very Good", "observed", ""),
    "glazing": ("single/partial/double/triple", "observed", "rules in mappings/glazing.csv; secondary glazing counted as double (assumption)"),
    "multi_glaze_pct": ("%", "observed", ""), "heating_type": ("category", "observed", "rules in mappings/heating_type.csv"),
    "heating_rating": ("Very Poor..Very Good", "observed", "mainheat_energy_eff"),
    "controls": ("none/timer/full/smart", "observed", "rules in mappings/controls.csv; 'smart' = time & temperature zone control (proxy)"),
    "solar_pv": ("bool", "observed", "photo_supply > 0"), "solar_pv_roof_pct": ("% of roof", "observed", "photo_supply"),
    "mains_gas": ("bool", "observed", "mains_gas_flag"),
    "epc_predicted_consumption_kwh_m2_primary": ("kWh/m2/yr (DEPRECATED: 'primary' unverified; use epc_modelled_energy_kwh_m2 in homes_tagged)", "modelled", "EPC energy_consumption_current (SAP model, not metered)"),
    "need_property_type": ("NEED category", "observed", "mappings/need_property_type.csv"),
    "need_age_band": ("NEED code 1-4", "assumption", "EPC band midpoint mapped to NEED edges"),
    "need_floor_area_band": ("NEED code 1-5", "observed", "NEED edges 50/100/150/200 m2"),
    "need_region": ("ONS code", "observed", "EPC region column"), "need_epc_band": ("A/B,C,D,E,F/G", "observed", ""),
    "need_main_fuel": ("1 gas / 2 not gas", "observed", "heating_type == gas_boiler"),
    "flag_floor_area_implausible": ("bool", "observed", "outside 15-1000 m2"), "flag_missing_rating": ("bool", "observed", ""),
    "flag_missing_heating": ("bool", "observed", ""),
    "flag_conflict_gas_heating_no_mains_gas": ("bool", "observed", "gas boiler recorded but mains_gas_flag = N; gas set 0 per rule"),
    "baseline_gas_kwh": ("kWh/yr", "population_benchmark", "NEED median for similar homes in region; 0 only when no mains gas"),
    "baseline_elec_kwh": ("kWh/yr", "population_benchmark", "NEED median for similar homes in region"),
    "baseline_source": ("category", "population_benchmark", "provenance of baseline_*_kwh"),
    "gas_status": ("category", "-", "how baseline_gas_kwh was set"), "elec_status": ("category", "-", ""),
    "modelled_gas_kwh": ("kWh/yr", "unavailable", "reserved for energy model"), "modelled_elec_kwh": ("kWh/yr", "unavailable", "reserved"),
    "split": ("train/val/test", "assumption", "hash of property_id with seed 42, 70/15/15"),
}


def write_docs(homes: pd.DataFrame, mappings: dict, bench_src: str):
    md = [f"# York regional dataset (Lloyds PS2 Green Home Score)\n",
          f"Built by `pipelines/build_region.py` (seed {SEED}). Access date for all sources: {ACCESS_DATE}.\n",
          "## Sources and licences\n",
          "| Source | URL | Licence / attribution |\n|---|---|---|",
          "| EPC domestic certificates and recommendations (bulk, 2008-2026), MHCLG | https://get-energy-performance-data.communities.gov.uk | Open Government Licence v3.0; address data subject to Royal Mail / OS copyright terms on the service |",
          "| NEED anonymised dataset 2026 (4M sample), DESNZ | https://www.gov.uk/government/statistics/national-energy-efficiency-data-framework-need-anonymised-data-2026 | OGL v3.0 |",
          "| HM Land Registry Price Paid Data 2025-2026 | https://www.gov.uk/government/statistical-data-sets/price-paid-data-downloads | OGL v3.0. Contains HM Land Registry data © Crown copyright and database right 2026. This data is licensed under the Open Government Licence v3.0. |",
          "| DESNZ GHG conversion factors 2026 | https://www.gov.uk/government/publications/greenhouse-gas-reporting-conversion-factors-2026 | OGL v3.0 |",
          "| postcodes / EPC code lists (epc_codes.json) | EPC API /api/codes | OGL v3.0 |\n",
          "## Coverage\n",
          f"Local authority {LA_CODE} ({REGION_NAME}); all EPC certificates lodged 2008-2026; Land Registry sales Jan 2025-Aug 2026 in district {PPD_DISTRICT}; "
          f"NEED benchmarks from {bench_src}, region E12000003 (Yorkshire and The Humber).\n",
          "## Known limitations\n",
          "- NEED is anonymised and cannot be linked to individual EPC homes: baseline energy is a **population benchmark** (median of similar homes in the region), not a measurement of that home.",
          "- Benchmarks are keyed by NEED's coarse bands; within-cell variation (IQR in benchmarks.parquet) is large because of occupant behaviour.",
          "- NEED gas benchmarks cover gas-heated homes only; homes with mains gas but non-gas main heating get no gas baseline.",
          "- NEED electricity is metered import; homes with solar PV will import less than the benchmark suggests.",
          "- Only 2025-26 sales are available, so repeat sales of the same home are rare: price changes after retrofits cannot be observed directly.",
          "- homes.parquet holds the *latest* certificate; for any sale-related modelling use the at-sale fields in sales_matched.parquet (latest EPC lodged on/before the sale) to avoid future leakage.",
          "- EPC data reflect the assessor's visit; many certificates are old (EPCs last 10 years) and features may have changed since.",
          "- `epc_predicted_consumption_kwh_m2_primary` (deprecated name) is SAP-modelled energy per m2, not metered; the data dictionary does not say whether it is primary or delivered energy.",
          "- 'smart' controls is a proxy: EPCs record 'Time and temperature zone control', not whether a thermostat is internet-connected.",
          "- Recommendations are the assessor's software suggestions: context labels, not feasibility ground truth.\n",
          "## Assumptions\n",
          "- property_id = UPRN where present, else hash of normalised address + postcode.",
          "- Secondary glazing is treated as `double`; partial = any multi-glazed share between 1 and 99%.",
          "- Main heating system = first system listed in mainheat_description; community schemes, LPG and solid fuels -> `other`.",
          "- EPC age bands straddling NEED band edges are assigned by their midpoint (e.g. 1967-1975 -> NEED band 2).",
          "- Open-ended floor-area and age bands: '2007/2012 onwards' end at 2026; 'before 1900' starts at 1850.",
          f"- Benchmark cells need >= {BENCH_MIN_N} homes; otherwise the next coarser level is used (recorded per home). Benchmarks also split by main heating fuel, because electricity use differs strongly for electrically heated homes.",
          f"- Sales matching: same postcode, then exact normalised address (EPC lines 1 / 1-2 / 1-3 vs sale SAON+PAON+street with and without locality), then fuzzy token_sort_ratio >= {FUZZY_MIN} restricted to candidates with identical house/flat numbers; matches whose runner-up is within {AMBIG_GAP} points are 'ambiguous' and not linked.\n",
          "## Mapping tables\n"]
    for name, df in mappings.items():
        md.append(f"### {name}\n\nFile: `mappings/{name}.csv`\n")
        md.append(df.head(80).to_markdown(index=False) if len(df) <= 80 else df.head(80).to_markdown(index=False) + f"\n\n...({len(df)} rows, see CSV)")
        md.append("")
    md.append("## Column dictionary: homes.parquet\n\n| Column | Unit | Provenance | Notes |\n|---|---|---|---|")
    for c in homes.columns:
        if c in PROVENANCE:
            u, p, n = PROVENANCE[c]
        elif c.startswith("raw_"):
            u, p, n = "text", "observed", "raw EPC field, unchanged"
        elif c.endswith("_status"):
            u, p, n = "category", "-", "status/provenance of the related field"
        elif c.endswith("_benchmark_level") or c.endswith("_benchmark_n"):
            u, p, n = "level / count", "population_benchmark", "benchmark cell used and its size"
        elif c.startswith("rec_") or c in ("n_recommendations", "has_recommendations"):
            u, p, n = "0/1", "observed", "assessor recommendation on latest certificate (context label)"
        else:
            u, p, n = "", "observed", ""
        md.append(f"| {c} | {u} | {p} | {n} |")
    (OUT_DIR / f"DATA_{REGION_NAME.lower()}.md").write_text("\n".join(md))


# ---------------- main ----------------
def main():
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    (OUT_DIR / "mappings").mkdir(exist_ok=True)
    gi = ROOT / ".gitignore"
    lines = gi.read_text().splitlines() if gi.exists() else []
    gi.write_text("\n".join(lines + [x for x in (".env", "dataset/", "data/") if x not in lines]) + "\n")

    # Step 1
    cache = OUT_DIR / "epc_certs_all.parquet"
    if "--reuse-extract" in sys.argv and cache.exists():  # dev speed-up; full runs re-stream the zip
        certs = pd.read_parquet(cache)
        certs = certs[[c for c in certs.columns if not c.startswith("c_") and c != "property_id"]]
        log("1_extract", "reused_cache", len(certs))
    else:
        certs = step1_extract()
    certs["property_id"] = property_ids(certs)
    canon = canonicalise(certs)
    certs_all = pd.concat([certs, canon.add_prefix("c_")], axis=1)
    certs_all.to_parquet(OUT_DIR / "epc_certs_all.parquet", index=False)

    # Step 2
    log("2_dedupe", "properties", int(certs.property_id.nunique()))
    log("2_dedupe", "properties_with_uprn", int(certs.drop_duplicates("property_id").property_id.str.startswith("U").sum()))
    history = step2_history(certs, canon)
    order = pd.concat([certs[["property_id", "certificate_number"]], canon["lodgement_date"]], axis=1)
    order = order.sort_values(["property_id", "lodgement_date", "certificate_number"], kind="mergesort")
    latest_idx = order.groupby("property_id").tail(1).index
    n_certs = certs.groupby("property_id").size()

    # Step 3
    raw_cols = [c for c in CERT_COLS if c not in ("certificate_number", "uprn", "postcode", "address", "lodgement_date")]
    homes = pd.concat([certs.loc[latest_idx, ["property_id", "certificate_number", "uprn", "address", "postcode"]],
                       canon.loc[latest_idx], certs.loc[latest_idx, raw_cols].add_prefix("raw_")], axis=1)
    homes["n_certificates"] = homes.property_id.map(n_certs)
    homes["need_property_type"] = map_need_property_type(homes.property_type, homes.built_form)
    homes["need_floor_area_band"] = map_floor_band(homes.floor_area_m2)
    homes["need_region"] = homes.raw_region
    homes["need_epc_band"] = homes.rating.map({"A": "A/B", "B": "A/B", "C": "C", "D": "D", "E": "E", "F": "F/G", "G": "F/G"})
    homes["need_main_fuel"] = np.where(homes.heating_type.eq("gas_boiler"), 1, np.where(homes.heating_type.isna(), np.nan, 2))
    homes["flag_floor_area_implausible"] = homes.floor_area_m2.notna() & ~homes.floor_area_m2.between(15, 1000)
    homes["flag_missing_rating"] = homes.rating.isna()
    homes["flag_missing_heating"] = homes.heating_type.isna()
    log("3_clean", "homes_before_drop", len(homes))
    drop = homes.rating.isna() & homes.floor_area_m2.isna()
    log("3_clean", "dropped_no_rating_and_no_floor_area", int(drop.sum()))
    homes = homes[~drop].sort_values("property_id").reset_index(drop=True)
    for f in ("flag_floor_area_implausible", "flag_missing_rating", "flag_missing_heating"):
        log("3_clean", f, int(homes[f].sum()))
    log("3_clean", "unmapped_controls_values", certs.loc[latest_idx, "mainheatcont_description"][canon.loc[latest_idx, "controls"].isna()].value_counts(dropna=False).head(15).to_dict())
    log("3_clean", "unmapped_heating_values", certs.loc[latest_idx, "mainheat_description"][canon.loc[latest_idx, "heating_type"].isna()].value_counts(dropna=False).head(15).to_dict())
    history = history[history.property_id.isin(homes.property_id)]
    history.to_parquet(OUT_DIR / "retrofit_history.parquet", index=False)

    # Step 4
    imp_map = improvement_mapping()
    recs_long, recs_wide = step4_recommendations(set(homes.certificate_number), homes, imp_map)
    recs_long.to_parquet(OUT_DIR / "recommendations_long.parquet", index=False)
    recs_wide.to_parquet(OUT_DIR / "recommendations_wide.parquet", index=False)

    # Step 5
    sales = step5_sales(homes, certs, canon)

    # Step 6/7
    bench, bench_src = step6_benchmarks()
    bench.to_parquet(OUT_DIR / "benchmarks.parquet", index=False)
    homes = step7_baselines(homes, bench)
    homes = homes.merge(recs_wide, on="property_id", how="left")

    # Step 8
    homes["split"] = split_for(homes.property_id)
    sales = sales.merge(homes[["property_id", "split"]], on="property_id", how="left")
    assert homes.groupby("property_id").split.nunique().max() == 1
    assert sales.dropna(subset=["property_id"]).groupby("property_id").split.nunique().max() == 1
    log("8_splits", "homes", homes.split.value_counts().to_dict())
    log("8_splits", "linked_sales", sales[sales.match_status == "linked"].split.value_counts().to_dict())

    # Step 9: outputs
    homes.to_parquet(OUT_DIR / "homes.parquet", index=False)
    sales.to_parquet(OUT_DIR / "sales_matched.parquet", index=False)
    linked = sales[sales.match_status == "linked"]
    audit = linked.sample(min(50, len(linked)), random_state=SEED)[
        ["transaction_id", "sale_date", "price", "postcode", "saon", "paon", "street", "locality", "sale_addr", "epc_address",
         "property_id", "match_method", "match_score"]].assign(correct="")
    audit.to_csv(OUT_DIR / "match_audit_sample.csv", index=False)

    mappings = {
        "improvement_to_measure": imp_map,
        "glazing": canon[["glazing"]].join(certs[["glazed_type", "windows_description"]]).fillna("<missing>").value_counts().reset_index(name="n"),
        "heating_type": canon[["heating_type"]].join(certs[["mainheat_description", "main_fuel"]]).fillna("<missing>").value_counts().reset_index(name="n").head(200),
        "controls": canon[["controls"]].join(certs[["mainheatcont_description"]]).fillna("<missing>").value_counts().reset_index(name="n"),
        "age_band": canon[["age_band", "age_start", "age_end"]].assign(need_age_band=canon.need_age_band.astype("string"), raw=certs.construction_age_band).fillna("<missing>").value_counts().reset_index(name="n"),
        "need_property_type": homes[["property_type", "built_form", "need_property_type"]].fillna("<missing>").value_counts().reset_index(name="n"),
        "need_floor_area_band": pd.DataFrame({"need_floor_area_band": [1, 2, 3, 4, 5], "floor_area_m2": ["<=50", "50-100", "100-150", "150-200", ">200"]}),
        "need_epc_band": pd.DataFrame({"rating": list("ABCDEFG"), "need_epc_band": ["A/B", "A/B", "C", "D", "E", "F/G", "F/G"]}),
        "need_main_fuel": pd.DataFrame({"heating_type": ["gas_boiler", "oil", "electric", "heat_pump", "other", "<missing>"],
                                        "need_main_fuel": ["1", "2", "2", "2", "2", "missing"]}),
        "controls_rules": pd.DataFrame(CONTROLS_RULES, columns=["regex", "level"]),
    }
    for name, df in mappings.items():
        df.to_csv(OUT_DIR / "mappings" / f"{name}.csv", index=False)

    canonical = ["rating", "sap_score", "potential_rating", "potential_sap", "floor_area_m2", "property_type", "built_form",
                 "age_band", "walls_rating", "roof_rating", "floor_rating", "windows_rating", "glazing", "heating_type",
                 "heating_rating", "controls", "solar_pv", "mains_gas", "epc_predicted_consumption_kwh_m2_primary",
                 "lodgement_date", "postcode", "address", "uprn", "need_property_type", "need_age_band",
                 "need_floor_area_band", "need_region", "need_epc_band", "need_main_fuel", "baseline_gas_kwh", "baseline_elec_kwh"]
    report["missing_pct"] = {c: round(100 * homes[c].isna().mean(), 2) for c in canonical}
    report["distributions"] = {c: homes[c].astype(str).value_counts().to_dict() for c in
                               ("rating", "property_type", "heating_type", "glazing", "controls", "need_property_type")}
    report["sales_match"] = {"by_status": sales.match_status.value_counts().to_dict(),
                             "by_method": sales.match_method.value_counts(dropna=False).to_dict(),
                             "link_rate_pct": round(100 * (sales.match_status == "linked").mean(), 1)}
    report["benchmark_levels"] = {"gas": homes.gas_benchmark_level.value_counts(dropna=False).to_dict(),
                                  "elec": homes.elec_benchmark_level.value_counts(dropna=False).to_dict()}
    outputs = {"homes.parquet": homes, "epc_certs_all.parquet": certs_all, "retrofit_history.parquet": history,
               "recommendations_long.parquet": recs_long, "recommendations_wide.parquet": recs_wide,
               "sales_matched.parquet": sales, "match_audit_sample.csv": audit, "benchmarks.parquet": bench}
    report["output_rows"] = {k: len(v) for k, v in outputs.items()}

    # ---------------- acceptance checks ----------------
    assert homes.property_id.is_unique, "property_id not unique"
    assert homes.groupby("property_id").split.nunique().max() == 1
    gas_zero = homes.baseline_gas_kwh.eq(0)
    assert (homes.loc[gas_zero, "gas_status"] == "no_mains_gas").all(), "gas zero without no_mains_gas"
    for c in ("sap_score", "floor_area_m2", "potential_sap", "baseline_elec_kwh"):
        assert not homes[c].eq(0).any(), f"zero in {c}"
    ec0 = homes.epc_predicted_consumption_kwh_m2_primary.eq(0)
    assert (homes.loc[ec0, "rating"] == "A").all(), "zero EPC consumption on non-A home"
    derived = [c for c in homes.columns if not c.startswith(("raw_", "rec_"))]
    undocumented = [c for c in derived if c not in PROVENANCE and not c.endswith(("_status", "_benchmark_level", "_benchmark_n"))
                    and c not in ("n_recommendations", "has_recommendations")]
    assert not undocumented, f"no provenance for {undocumented}"
    warnings = []
    if len(homes) < 20000:
        warnings.append(f"homes {len(homes)} < 20,000")
    if (sales.match_status == "linked").sum() < 1500:
        warnings.append(f"linked sales {(sales.match_status == 'linked').sum()} < 1,500")
    report["acceptance_warnings"] = warnings
    fp = {"rows": report["output_rows"],
          "split_hash": stable_hash("".join(homes.property_id + homes.split), 32),
          "sales_hash": stable_hash("".join(sales.transaction_id + sales.property_id.fillna("") + sales.match_status), 32)}
    fp_path = OUT_DIR / "_fingerprint.json"
    if fp_path.exists():
        prev = json.loads(fp_path.read_text())
        assert prev == fp, f"rerun differs: {prev} vs {fp}"
        report["rerun_identical"] = True
    else:
        report["rerun_identical"] = "first run (rerun to verify)"
    fp_path.write_text(json.dumps(fp, indent=1))
    (OUT_DIR / "quality_report.json").write_text(json.dumps(report, indent=1, default=str))
    write_docs(homes, mappings, bench_src)

    print("\n=== SUMMARY ===")
    for k, v in report["output_rows"].items():
        print(f"{k:32s} {v:>8,}")
    print("missing % (top):", dict(sorted(report["missing_pct"].items(), key=lambda kv: -kv[1])[:8]))
    print("sales:", report["sales_match"])
    print("warnings:", warnings, "| rerun identical:", report["rerun_identical"])


if __name__ == "__main__":
    main()
