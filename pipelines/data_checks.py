"""Data integrity and leakage checks against the real York files.

Each check returns (ok: bool, detail: str). Used by pipelines/check_data.py (PASS/FAIL table)
and tests/data/test_data_integrity.py (pytest), so both run identical logic.
"""
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
YORK = ROOT / "data/processed/region=york"
CONFIGS = ROOT / "configs"
N_HOMES = 65872
EXPECTED_FLAGS = {"flag_gas_boiler_no_mains_gas": 56, "flag_energy_zero_or_negative": 144, "flag_no_heating_description": 55,
                  "flag_gas_connection_unknown": 3299, "flag_stale_epc": 21358}
EXPECTED_UNAVAILABLE_IP = 4415
ALLOWED_PROV = {"observed", "user_provided", "modelled", "population_benchmark", "assumption", "synthetic", "unavailable"}
ADDRESS_KEYS = {"address", "address1", "address2", "address3", "raw_address1", "raw_address2", "raw_address3", "postcode", "raw_posttown"}


@lru_cache(maxsize=None)
def homes() -> pd.DataFrame:
    return pd.read_parquet(YORK / "homes_tagged.parquet")


@lru_cache(maxsize=None)
def sales() -> pd.DataFrame:
    return pd.read_parquet(YORK / "sales_matched.parquet")


def check_unique_ids():
    h = homes()
    ok = h.property_id.is_unique and len(h) == N_HOMES
    return ok, f"rows={len(h)} (expected {N_HOMES}), unique={h.property_id.is_unique}"


def check_split_isolation():
    h, s = homes(), sales()
    per_home = h.groupby("property_id").split.nunique().max()
    linked = s[s.match_status == "linked"].merge(h[["property_id", "split"]], on="property_id", how="left", suffixes=("", "_home"))
    mismatch = int((linked.split != linked.split_home).sum())
    unlinked_with_split = int(s[s.match_status != "linked"].split.notna().sum())
    ok = per_home == 1 and mismatch == 0 and unlinked_with_split == 0 and set(h.split) == {"train", "val", "test"}
    return ok, f"max splits per home={per_home}; linked sales with split != home split={mismatch}; unlinked sales with a split={unlinked_with_split}"


def check_no_future_epc_at_sale():
    s = sales()
    linked = s[s.match_status == "linked"]
    certs = pd.read_parquet(YORK / "epc_certs_all.parquet", columns=["certificate_number", "property_id", "c_lodgement_date"])
    j = linked.merge(certs, left_on="epc_cert_at_sale", right_on="certificate_number", how="left")
    has = j.epc_cert_at_sale.notna()
    after = int((j.loc[has, "c_lodgement_date"] > j.loc[has, "sale_date"]).sum())
    wrong_home = int((j.loc[has, "property_id_y"] != j.loc[has, "property_id_x"]).sum())
    # and no later-but-still-before-sale cert was skipped (the at-sale cert is the latest on/before the sale)
    c = certs.dropna(subset=["c_lodgement_date"])
    m = linked[["transaction_id", "property_id", "sale_date", "epc_lodged_at_sale"]].merge(c, on="property_id")
    m = m[m.c_lodgement_date <= m.sale_date]
    latest = m.groupby("transaction_id").c_lodgement_date.max()
    chk = linked.set_index("transaction_id").epc_lodged_at_sale.reindex(latest.index)
    not_latest = int((chk != latest).sum())
    ok = after == 0 and wrong_home == 0 and not_latest == 0
    return ok, f"linked={len(linked)}; at-sale cert after sale={after}; cert of other home={wrong_home}; not latest-before-sale={not_latest}"


def check_baselines_not_zero_filled():
    h = homes()
    neg = int((h.baseline_gas_kwh < 0).sum() + (h.baseline_elec_kwh < 0).sum())
    gas0_bad = int((h.baseline_gas_kwh.eq(0) & h.gas_status.ne("no_mains_gas")).sum())
    elec0 = int(h.baseline_elec_kwh.eq(0).sum())
    unavailable = h.gas_status.isin(["unavailable", "unknown_mains_gas", "gas_supply_not_main_heating_no_benchmark"])
    unavail_not_null = int(h.loc[unavailable, "baseline_gas_kwh"].notna().sum())
    elec_unavail_not_null = int(h.loc[h.elec_status.eq("unavailable"), "baseline_elec_kwh"].notna().sum())
    no_status = int((h.baseline_gas_kwh.isna() & h.gas_status.isna()).sum() + (h.baseline_elec_kwh.isna() & h.elec_status.isna()).sum())
    ok = neg == gas0_bad == elec0 == unavail_not_null == elec_unavail_not_null == no_status == 0
    return ok, (f"negative={neg}; gas 0 without no_mains_gas={gas0_bad}; elec 0={elec0}; unavailable-status gas not null={unavail_not_null}; "
                f"unavailable elec not null={elec_unavail_not_null}; null without status={no_status}")


def check_flag_counts():
    h = homes()
    got = {k: int(h[k].sum()) for k in EXPECTED_FLAGS}
    ip = int((h.improvement_potential_status == "unavailable").sum())
    ok = got == EXPECTED_FLAGS and ip == EXPECTED_UNAVAILABLE_IP
    return ok, f"{got}; improvement_potential unavailable={ip} (expected {EXPECTED_UNAVAILABLE_IP})"


def check_score_params_train_only():
    import sys
    sys.path.insert(0, str(Path(__file__).parent))
    from freeze_score_params import exclusion_reason, scaled_baselines
    p = json.loads((CONFIGS / "score_params.json").read_text())["intensity"]
    h = pd.read_parquet(YORK / "homes_tagged.parquet")
    tr = h[h.split == "train"].copy()
    tr["baseline_gas_kwh"], tr["baseline_elec_kwh"], _ = scaled_baselines(tr)   # v2: same area scaling as the freeze (D21)
    used = tr[exclusion_reason(tr).isna()]
    inten = (used.baseline_gas_kwh + used.baseline_elec_kwh) / used.floor_area_m2
    p10, p90 = float(np.percentile(inten, 10)), float(np.percentile(inten, 90))
    allh = h[exclusion_reason(h).isna()]
    p10_all = float(np.percentile((allh.baseline_gas_kwh + allh.baseline_elec_kwh) / allh.floor_area_m2, 10))
    ok = (p["p10"] < p["p90"] and p["n"] == len(used) and abs(round(p10, 3) - p["p10"]) < 1e-6
          and abs(round(p90, 3) - p["p90"]) < 1e-6)
    return ok, (f"saved p10={p['p10']} p90={p['p90']} n={p['n']}; recomputed train p10={p10:.3f} p90={p90:.3f} n={len(used)}; "
                f"(all-splits p10 would be {p10_all:.3f})")


def check_provenance_values():
    h = homes()
    bad = {}
    for c in [c for c in h.columns if c.startswith("prov_")]:
        extra = set(h[c].dropna().unique()) - ALLOWED_PROV
        if extra or h[c].isna().any():
            bad[c] = sorted(map(str, extra)) + (["<null>"] if h[c].isna().any() else [])
    return not bad, f"{len([c for c in h.columns if c.startswith('prov_')])} prov_ columns; invalid={bad or 'none'}"


def check_feature_availability():
    fa = json.loads((CONFIGS / "feature_availability.json").read_text())
    roles = fa["roles"]
    cols = set(homes().columns)
    missing = sorted(cols - set(roles))
    extra = sorted(set(roles) - cols)
    feature_ok = {c for c, r in roles.items() if r == "feature_ok"}
    label_leak = sorted(feature_ok & {c for c, r in roles.items() if r == "label_only"} | {c for c in feature_ok if c.startswith("rec_")})
    addr_leak = sorted(c for c in feature_ok if c in ADDRESS_KEYS)
    allowed = {"feature_ok", "label_only", "identifier", "metadata", "deprecated", "restricted_address"}
    bad_roles = sorted(set(roles.values()) - allowed)
    addr_role = all(roles.get(c) == "restricted_address" for c in ADDRESS_KEYS if c in cols)
    ok = not (missing or extra or label_leak or addr_leak or bad_roles) and addr_role
    return ok, (f"columns={len(cols)}; unlisted={missing or 0}; stale={extra or 0}; label_only in feature_ok={label_leak or 0}; "
                f"address in feature_ok={addr_leak or 0}; address role ok={addr_role}")


FULL_POSTCODE = r"\b[A-Z]{1,2}[0-9][0-9A-Z]? ?[0-9][A-Z]{2}\b"
DEMO_INTERNAL = YORK / "demo_homes_internal.json"


def check_demo_homes_licence_safe():
    """Committed demo_homes.json has no address/full postcode; the internal address file (if present) is
    git-ignored and untracked. Works on a fresh clone (internal file absent)."""
    import re
    import subprocess
    path = CONFIGS / "demo_homes.json"
    text = path.read_text()
    d = json.loads(text)
    problems = []

    def keys(o):
        if isinstance(o, dict):
            for k, v in o.items():
                yield k
                yield from keys(v)
        elif isinstance(o, list):
            for v in o:
                yield from keys(v)
    leaked = (ADDRESS_KEYS | {"internal", "internal_only"}) & set(keys(d))
    if leaked:
        problems.append(f"forbidden keys {sorted(leaked)}")
    if re.search(FULL_POSTCODE, text):
        problems.append("full postcode pattern in committed file")
    for h in d["homes"]:
        if " " in str(h.get("public_fields", {}).get("postcode_outward", "")):
            problems.append(f"{h.get('home_id')}: postcode_outward is not an outward code")
    internal = "absent (fresh clone)"
    if DEMO_INTERNAL.exists():
        rel = str(DEMO_INTERNAL.relative_to(ROOT))
        tracked = subprocess.run(["git", "ls-files", "--error-unmatch", rel], cwd=ROOT, capture_output=True).returncode == 0
        ignored = subprocess.run(["git", "check-ignore", "-q", rel], cwd=ROOT).returncode == 0
        ids_pub = [h["home_id"] for h in d["homes"]]
        ids_int = [h["home_id"] for h in json.loads(DEMO_INTERNAL.read_text())["homes"]]
        if tracked or not ignored:
            problems.append(f"internal file tracked={tracked} ignored={ignored}")
        if ids_pub != ids_int:
            problems.append("home_ids differ between public and internal files")
        internal = f"present, tracked={tracked}, ignored={ignored}"
    return not problems, f"{len(d['homes'])} demo homes; internal file {internal}; problems={problems or 'none'}"


CHECKS = {
    "property_id unique, 65,872 rows": check_unique_ids,
    "split isolation (homes and sales)": check_split_isolation,
    "no future EPC at sale": check_no_future_epc_at_sale,
    "baselines null-with-status, never 0-filled": check_baselines_not_zero_filled,
    "flag counts": check_flag_counts,
    "score_params from TRAIN only": check_score_params_train_only,
    "provenance values allowed": check_provenance_values,
    "feature availability / no label leakage": check_feature_availability,
    "demo homes licence-safe": check_demo_homes_licence_safe,
}
