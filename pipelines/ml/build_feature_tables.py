"""M1/M2 data: features of every York EPC certificate -> data/processed/region=york/ml_cert_features.parquet.

One row per certificate: property_id, certificate_number, split (the home's split), is_latest, lodgement date, the
SAP target (c_sap_score), floor-area plausibility, and every derived feature (features.derive). Address columns are
never loaded; the outward code and sector are derived and the postcode dropped (privacy.safe_read_parquet).

Usage: .venv/bin/python pipelines/ml/build_feature_tables.py
"""
from __future__ import annotations

import time

import pandas as pd

from common import CERT_FEATURES, YORK, homes  # noqa: E402  (sys.path set in common)
from backend.app.ml import features as F  # noqa: E402
from backend.app.ml.privacy import assert_no_restricted, safe_read_parquet  # noqa: E402
from backend.app.ml.splits import attach_home_split  # noqa: E402


def build() -> pd.DataFrame:
    t = time.time()
    certs = safe_read_parquet(YORK / "epc_certs_all.parquet", columns=[*F.CERT_COLUMNS, "certificate_number"],
                              derive_postcode=True)
    h = homes(["property_id", "split", "certificate_number"]).rename(columns={"certificate_number": "latest_cert"})
    states = [F.state_from_certificate(r) for r in certs.to_dict("records")]
    feats = pd.DataFrame([F.derive(s) for s in states], index=certs.index)
    out = pd.DataFrame({
        "property_id": certs.property_id.astype(str),
        "certificate_number": certs.certificate_number.astype(str),
        "lodgement_date": pd.to_datetime(certs.c_lodgement_date),
        "sap_target": pd.to_numeric(certs.c_sap_score, errors="coerce"),
        "rating": certs.c_rating,
        "floor_area_m2": pd.to_numeric(certs.c_floor_area_m2, errors="coerce"),
        "property_type_raw": certs.c_property_type, "built_form_raw": certs.c_built_form,
        "age_band_raw": certs.c_age_band, "heating_type_raw": certs.c_heating_type,
    })
    out = pd.concat([out, feats.drop(columns=[c for c in feats.columns if c in out.columns])], axis=1)
    out = attach_home_split(out, h)
    out = out.merge(h[["property_id", "latest_cert"]], on="property_id", how="left")
    out["is_latest"] = out.certificate_number == out.latest_cert
    out = out.drop(columns="latest_cert")
    out["area_plausible"] = out.floor_area_m2.between(15, 1000)
    # certificate order within a home: lodgement date, then certificate number (deterministic)
    out = out.sort_values(["property_id", "lodgement_date", "certificate_number"]).reset_index(drop=True)
    out["cert_seq"] = out.groupby("property_id").cumcount()
    assert_no_restricted(out.columns)
    print(f"built {len(out):,} certificate rows in {time.time() - t:.1f}s; latest {out.is_latest.sum():,}; "
          f"split {out.split.value_counts().to_dict()}")
    return out


if __name__ == "__main__":
    df = build()
    df.to_parquet(CERT_FEATURES, index=False)
    print(f"wrote {CERT_FEATURES}")
