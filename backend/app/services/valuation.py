"""Indicative property-value impact of a scenario (M3). Replaces the old gated stub in scenario_builder.

uplift % from the modelled ΔSAP (services/sap_model):
- hedonic: exp(β_SAP × ΔSAP) − 1 at the sector-clustered bootstrap p10 / p50 / p90 of β_SAP;
- GBM: the same home at its observed SAP and at SAP + ΔSAP, all else fixed, averaged over the 5 CV models;
- range: low = min(hedonic low, GBM), high = max(hedonic high, GBM), mid = hedonic p50.
Current value: GBM at the latest sale month with a split-conformal 80% interval.

Abstains (not_estimated + reason) when the value gate is closed (D10), a model is missing, there are no measures or
the SAP score is missing. An unseen outward code drops only the GBP figures. Association, not a causal effect.
"""
from __future__ import annotations

import math
from functools import lru_cache
from typing import Optional

import numpy as np

from .. import config
from ..ml import features as F
from ..ml import registry
from ..ml.value_data import GBM_COLS, lr_type_for_home, te_apply
from ..schemas.enums import MeasureId, Provenance, ValueStatus
from ..schemas.property import HomeRecord
from ..schemas.scenario import Valuation
from .sap_model import sap_change

LABEL = ("estimated potential property-value impact based on historical and market relationships in the dataset "
         "prepared by the team")
CAVEATS = [
    "association between EPC score and sale price, not a causal effect of retrofitting",
    "condition and micro-location are not observed and confound the relationship",
    "based on about 20 months of York sales (2025-01 to 2026-08)",
    "the EPC change is modelled (indicative), not an EPC re-assessment",
]


def _abstain(reason: str, **kw) -> Valuation:
    return Valuation(status=ValueStatus.not_estimated, reason=reason, caveats=CAVEATS, **kw)


def gate_open() -> tuple[bool, str]:
    g = config.value_gate()
    if g.get("status") == "enabled":
        return True, ""
    cov = g.get("coverage_check")
    cov_txt = cov.get("result") if isinstance(cov, dict) else cov
    return False, (f"value gate closed (D10): status '{g.get('status')}', coverage check: {cov_txt}; "
                   "property-value estimate not shown")


@lru_cache(maxsize=None)
def _cv_models(version: str) -> tuple:
    import lightgbm as lgb
    m = registry.get("value_gbm")
    d = registry.MODELS_DIR / "value_gbm"
    return tuple(lgb.Booster(model_file=str(d / f)) for f in m.meta.get("cv_models", []) if (d / f).exists())


def home_value_row(home: HomeRecord, meta: dict, sap: Optional[float] = None) -> dict:
    """Value features of a home that has not been sold: latest certificate state, Land Registry type from the
    property type and built form, tenure by type (flats leasehold, D35), not new build, latest sale month."""
    st = F.state_from_home(home)
    if sap is not None:
        st["sap_score"] = sap
    row = F.features(st, "value")
    lr = lr_type_for_home(home.property_type, home.built_form)
    row.update(F.sale_features(0, "L" if lr == "Flat/Maisonette" else "F", lr, None))
    row["sale_month_index"] = float(meta["latest_month_index"])
    row["te_sector"] = float(te_apply(meta["te_sector"], __import__("pandas").Series([home.postcode_sector]))[0])
    return {c: row[c] for c in GBM_COLS}


def estimate(home: HomeRecord, measures: list[MeasureId], explain: bool = False) -> Valuation:
    ok, why = gate_open()
    if not ok:
        return _abstain(why)
    gbm, hed = registry.get("value_gbm"), registry.get_json("value_hedonic")
    if gbm is None or hed is None:
        return _abstain("property-value model missing (not trained or did not pass its validation gate)")
    if not measures:
        return _abstain("no measures applied: no change in EPC score to value")
    ch = sap_change(home, measures)
    if ch["sap_change"] is None:
        return _abstain(f"EPC change not estimated: {ch['reason']}")
    if home.sap_score is None:
        return _abstain("SAP score missing: the value model needs the current EPC score")
    d = ch["sap_change"]
    b = hed["beta_sap_bootstrap"]
    hed_pct = sorted(100.0 * (math.exp(b[k] * d) - 1.0) for k in ("p10", "p50", "p90"))
    X0 = gbm.frame([home_value_row(home, gbm.meta, home.sap_score)])
    X1 = gbm.frame([home_value_row(home, gbm.meta, home.sap_score + d)])
    cv = _cv_models(gbm.version) or (gbm.booster,)
    gbm_pct = float(np.mean([100.0 * (math.exp(m.predict(X1)[0] - m.predict(X0)[0]) - 1.0) for m in cv]))
    low, mid, high = min(hed_pct[0], gbm_pct), hed_pct[1], max(hed_pct[2], gbm_pct)
    v = dict(status=ValueStatus.ok, reason=LABEL, low_pct=round(low, 2), mid_pct=round(mid, 2), high_pct=round(high, 2),
             sap_before=home.sap_score, sap_change=d, sap_after_indicative=ch["sap_after_indicative"],
             rating_before=home.rating, rating_after_indicative=ch["rating_after_indicative"],
             measures=list(measures), provenance=Provenance.modelled, caveats=CAVEATS,
             basis=(f"hedonic β_SAP bootstrap p10/p50/p90 {b['p10']:.5f}/{b['p50']:.5f}/{b['p90']:.5f} per SAP point "
                    f"(clustered by postcode sector) and gradient-boosted model, same home at SAP {home.sap_score:g} "
                    f"and {home.sap_score + d:g}"),
             model_versions={"value_gbm": gbm.version, "value_hedonic": hed["version"], "sap": ch["model_version"]})
    if explain:   # top-5 contributions to log(current value)
        row = home_value_row(home, gbm.meta, home.sap_score)
        v["explanation"] = registry.top_contributions(list(gbm.meta["features"]), gbm.contributions([row])[0][:-1], row, 5)
    seen = home.postcode_outward in set(gbm.meta["categories"].get("postcode_district", []))
    if not seen:
        where = f"outward code {home.postcode_outward!r}" if home.postcode_outward else "the home's outward code (not known)"
        v.update(value_status=ValueStatus.not_estimated,
                 value_reason=f"{where} not seen in training sales: GBP value not estimated")
        return Valuation(**v)
    p = float(math.exp(gbm.booster.predict(X0)[0]))
    q = gbm.meta["conformal"]["abs_log_residual_q"]
    v.update(current_value_gbp=round(p, -3), current_value_low_gbp=round(p * math.exp(-q), -3),
             current_value_high_gbp=round(p * math.exp(q), -3),
             potential_value_low_gbp=round(p * (1 + low / 100.0), -3), potential_value_high_gbp=round(p * (1 + high / 100.0), -3),
             value_status=ValueStatus.ok,
             value_reason=f"model estimate at the latest sale month with an {int(100 * gbm.meta['conformal']['level'])}% "
                          "split-conformal interval (not a valuation or survey)")
    return Valuation(**v)
