# services/leasing_operativo/lease_profitability_service.py
# -*- coding: utf-8 -*-
"""Deal score y clasificación de calidad económica (umbrales desde políticas)."""
from __future__ import annotations

from decimal import Decimal
from typing import Any


def _d(v: Any, default: str = "0") -> Decimal:
    try:
        return Decimal(str(v).replace(",", ".")) if v is not None else Decimal(default)
    except Exception:
        return Decimal(default)


DEFAULT_DEAL_THRESHOLDS: dict[str, Any] = {
    "minimum_irr": 10.0,
    "minimum_npv": 0.0,
    "minimum_margin": 5.0,
    "residual_min_pct": 25.0,
    "maximum_residual_risk": 70.0,
    "ltv_max_pct": 92.0,
    "weights": {
        "tir": 0.30,
        "van": 0.20,
        "margen": 0.15,
        "residual": 0.15,
        "riesgo": 0.20,
    },
}


def merge_deal_thresholds(policy: dict[str, Any] | None) -> dict[str, Any]:
    out = dict(DEFAULT_DEAL_THRESHOLDS)
    if isinstance(policy, dict):
        w = dict(out["weights"])
        out.update({k: v for k, v in policy.items() if k != "weights"})
        if isinstance(policy.get("weights"), dict):
            w.update(policy["weights"])
        out["weights"] = w
    return out


def _clamp(x: float, lo: float = 0.0, hi: float = 100.0) -> float:
    return max(lo, min(hi, x))


def compute_deal_score(
    *,
    tir_anual_pct: Any,
    van: Any,
    margen_pct: Any,
    residual_pct: Any,
    residual_risk_score: Any,
    ltv_pct: Any = None,
    thresholds: dict[str, Any] | None = None,
) -> dict[str, Any]:
    th = merge_deal_thresholds(thresholds)
    w = th.get("weights") or {}
    has_pricing = tir_anual_pct is not None or van is not None
    tir = float(_d(tir_anual_pct)) if tir_anual_pct is not None else None
    van_v = float(_d(van)) if van is not None else None
    margen = float(_d(margen_pct)) if margen_pct is not None else None
    res_pct = float(_d(residual_pct))
    risk = float(_d(residual_risk_score))
    ltv = float(_d(ltv_pct)) if ltv_pct is not None else None

    tir_min = float(_d(th.get("minimum_irr"), "10"))
    van_min = float(_d(th.get("minimum_npv"), "0"))
    margen_min = float(_d(th.get("minimum_margin"), "5"))
    res_min = float(_d(th.get("residual_min_pct"), "25"))
    risk_max = float(_d(th.get("maximum_residual_risk"), "70"))
    ltv_max = float(_d(th.get("ltv_max_pct"), "92"))

    s_tir = _clamp(50 + ((tir if tir is not None else tir_min) - tir_min) * 4.0) if has_pricing else 60.0
    if van_v is not None:
        s_van = _clamp(55 + (van_v - van_min) / max(abs(van_min) + 1_000_000, 1) * 40)
        if van_v >= van_min:
            s_van = max(s_van, 60.0)
    else:
        s_van = 60.0
    s_margen = _clamp(50 + ((margen if margen is not None else margen_min) - margen_min) * 5.0) if margen is not None else 60.0
    s_res = _clamp(40 + (res_pct - res_min) * 2.0)
    s_risk = _clamp(100 - risk)

    score = (
        s_tir * float(w.get("tir", 0.3))
        + s_van * float(w.get("van", 0.2))
        + s_margen * float(w.get("margen", 0.15))
        + s_res * float(w.get("residual", 0.15))
        + s_risk * float(w.get("riesgo", 0.2))
    )
    score = round(_clamp(score), 1)

    fails_hard = []
    if has_pricing and tir is not None and tir < tir_min:
        fails_hard.append("TIR bajo mínimo de política")
    if has_pricing and van_v is not None and van_v < van_min:
        fails_hard.append("VAN bajo mínimo de política")
    if risk > risk_max:
        fails_hard.append("Riesgo residual sobre máximo de política")
    if ltv is not None and ltv > ltv_max:
        fails_hard.append("LTV sobre máximo de política")

    if not has_pricing:
        clase = "ACEPTABLE" if score >= 55 else "RIESGOSO"
        decision = "REVISAR" if fails_hard else "PENDIENTE_PRICING"
    elif fails_hard and score < 45:
        clase = "NO_RECOMENDADO"
        decision = "NO RECOMENDADO"
    elif fails_hard:
        clase = "RIESGOSO"
        decision = "REVISAR"
    elif score >= 85 and not fails_hard:
        clase = "EXCELENTE"
        decision = "APROBAR"
    elif score >= 70:
        clase = "BUENO"
        decision = "APROBAR"
    elif score >= 55:
        clase = "ACEPTABLE"
        decision = "APROBAR CON CONDICIONES"
    elif score >= 40:
        clase = "RIESGOSO"
        decision = "REVISAR"
    else:
        clase = "NO_RECOMENDADO"
        decision = "NO RECOMENDADO"

    return {
        "DEAL_SCORE": score,
        "DEAL_CLASS": clase,
        "DECISION": decision,
        "umbrales": {
            "minimum_irr": tir_min,
            "minimum_npv": van_min,
            "minimum_margin": margen_min,
            "residual_min_pct": res_min,
            "maximum_residual_risk": risk_max,
            "ltv_max_pct": ltv_max,
        },
        "componentes": {
            "tir": round(s_tir, 1),
            "van": round(s_van, 1),
            "margen": round(s_margen, 1),
            "residual": round(s_res, 1),
            "riesgo": round(s_risk, 1),
        },
        "alertas": fails_hard,
    }
