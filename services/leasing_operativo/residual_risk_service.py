# services/leasing_operativo/residual_risk_service.py
# -*- coding: utf-8 -*-
from __future__ import annotations

from typing import Any


def _band(score: float) -> str:
    if score >= 75:
        return "CRITICAL"
    if score >= 55:
        return "HIGH"
    if score >= 35:
        return "MEDIUM"
    return "LOW"


def residual_risk_score(
    *,
    n_comps: int,
    dispersion_pct: float | None,
    edad_fin_anios: float,
    km_fin: float,
    tipo_uso: str,
    comparability_avg: float | None = None,
) -> dict[str, Any]:
    score = 20.0
    if n_comps < 3:
        score += 25
    elif n_comps < 6:
        score += 12
    elif n_comps < 10:
        score += 5
    if dispersion_pct is not None:
        if dispersion_pct > 45:
            score += 22
        elif dispersion_pct > 30:
            score += 14
        elif dispersion_pct > 18:
            score += 7
    if edad_fin_anios > 7:
        score += 18
    elif edad_fin_anios > 5:
        score += 10
    elif edad_fin_anios > 3.5:
        score += 5
    if km_fin > 180_000:
        score += 18
    elif km_fin > 120_000:
        score += 10
    elif km_fin > 80_000:
        score += 5
    uso = str(tipo_uso or "").upper()
    if uso in {"USO_MINERO", "MINERO", "USO_TERRITORIO_EXTREMO", "USO_CONSTRUCCION", "FAENA", "USO_INTENSIVO"}:
        score += 12
    elif uso in {"USO_LOGISTICO", "USO_REPARTO", "USO_COMERCIAL", "MIXTO"}:
        score += 6
    if comparability_avg is not None and comparability_avg < 55:
        score += 10
    elif comparability_avg is not None and comparability_avg < 70:
        score += 5
    score = max(0.0, min(100.0, round(score, 1)))
    return {
        "RESIDUAL_RISK_SCORE": score,
        "RESIDUAL_RISK_LEVEL": _band(score),
        "drivers": {
            "n_comps": n_comps,
            "dispersion_pct": dispersion_pct,
            "edad_fin_anios": edad_fin_anios,
            "km_fin": km_fin,
            "tipo_uso": uso,
            "comparability_avg": comparability_avg,
        },
    }


def valuation_confidence(
    *,
    n_comps: int,
    comparability_avg: float | None,
    dispersion_pct: float | None,
    data_age_hours: float | None = 0,
    version_match_ratio: float | None = None,
) -> dict[str, Any]:
    score = 35.0
    score += min(n_comps * 4.5, 36.0)
    if comparability_avg is not None:
        score += max(0.0, (comparability_avg - 50.0) * 0.45)
    if dispersion_pct is not None:
        score -= min(max(dispersion_pct - 12.0, 0) * 0.7, 20.0)
    if data_age_hours and data_age_hours > 72:
        score -= 8
    if version_match_ratio is not None:
        score += version_match_ratio * 8.0
    score = max(0.0, min(100.0, round(score, 0)))
    if score >= 85:
        label = "Alta"
    elif score >= 65:
        label = "Media"
    elif score >= 45:
        label = "Moderada"
    else:
        label = "Baja"
    return {
        "VALUATION_CONFIDENCE": int(score),
        "VALUATION_CONFIDENCE_LABEL": label,
        "display": f"{int(score)}/100 — {label}",
    }
