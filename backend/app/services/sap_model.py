"""Modelled EPC change (M2): ΔSAP of a home's state after a set of measures, from the shipped SAP model.

ΔSAP = model(after state) - model(before state), both at the model's reference lodgement year (D32), so only the
state change counts. The indicative SAP after = clip(observed SAP + ΔSAP, 1, 100) (provenance modelled). Abstains
(status not_estimated + reason) when the model is absent, there are no measures, or the observed SAP is missing.
"""
from __future__ import annotations

from typing import Optional

from ..ml import features as F
from ..ml import registry
from ..ml.metrics import sap_band
from ..schemas.enums import MeasureId, Provenance, ValueStatus
from ..schemas.property import HomeRecord

LABEL = "indicative EPC after retrofit, modelled from York certificates (not an EPC re-assessment)"


def model():
    return registry.get("sap")


def predict_sap(state: dict, lodgement_year: Optional[int] = None) -> Optional[float]:
    """Model SAP for a canonical state (features.state_from_home / state_from_certificate); None without a model."""
    m = model()
    if m is None:
        return None
    yr = lodgement_year if lodgement_year is not None else m.meta["reference_year"]
    return float(m.predict([F.features(state, "sap", yr)])[0])


def band(sap: Optional[float]) -> Optional[str]:
    return None if sap is None else str(sap_band([sap])[0])


def sap_change(home: HomeRecord, measures: list[MeasureId], explain: bool = False) -> dict:
    """{status, reason, sap_before, sap_change, sap_after_indicative, rating_before, rating_after_indicative,
    model_version, provenance, label}. Missing values are None with a status, never 0."""
    m = model()
    out = {"status": ValueStatus.not_estimated.value, "reason": None, "sap_before": home.sap_score,
           "sap_change": None, "sap_after_indicative": None, "rating_before": home.rating,
           "rating_after_indicative": None, "model_version": m.version if m else None,
           "provenance": Provenance.modelled.value, "label": LABEL}
    if m is None:
        out["reason"] = "SAP model not available (not trained or did not pass its validation gates)"
        return out
    if not measures:
        out["reason"] = "no measures applied"
        return out
    yr = m.meta["reference_year"]
    before = F.features(F.state_from_home(home), "sap", yr)
    after = F.after_features(home, measures, "sap", yr)
    pb, pa = m.predict([before, after])
    delta = float(pa - pb)
    out["sap_change"] = round(delta, 2)
    if explain:   # which inputs drive the modelled change: contribution(after) - contribution(before), top 5
        cb, ca = m.contributions([before, after])
        names = m.meta["features"]
        out["explanation"] = registry.top_contributions(names, (ca - cb)[:-1], after, 5)
    if home.sap_score is None:
        out["reason"] = "observed SAP score missing: change modelled but no indicative SAP after"
        return out
    after_sap = min(max(home.sap_score + delta, 1.0), 100.0)
    out.update(status=ValueStatus.ok.value, sap_after_indicative=round(after_sap, 1),
               rating_after_indicative=band(after_sap))
    return out
