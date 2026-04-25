# services/leasing_operativo/risk_model.py
# -*- coding: utf-8 -*-
"""Prima de riesgo: PD × LGD × EAD (mensualizado). Segmentos y multiplicadores de activo/uso."""
from __future__ import annotations

from decimal import Decimal
from typing import Any


def _d(v: Any, default: str = "0") -> Decimal:
    if v is None:
        return Decimal(default)
    if isinstance(v, Decimal):
        return v
    try:
        return Decimal(str(v))
    except Exception:
        return Decimal(default)


def pick_pd(segmento: str, riesgo_json: dict[str, Any]) -> Decimal:
    s = (segmento or "MEDIO").strip().upper()
    key = f"PD_{s}"
    if key in riesgo_json:
        return _d(riesgo_json[key])
    mapping = {
        "BAJO": _d(riesgo_json.get("PD_BAJO"), "0.012"),
        "MEDIO": _d(riesgo_json.get("PD_MEDIO"), "0.035"),
        "ALTO": _d(riesgo_json.get("PD_ALTO"), "0.09"),
        "CRITICO": _d(riesgo_json.get("PD_CRITICO"), "0.18"),
    }
    return mapping.get(s, mapping["MEDIO"])


def prima_riesgo_mensual(
    *,
    pd: Decimal,
    lgd_pct: Decimal,
    ead: Decimal,
    plazo_meses: int,
    riesgo_sector_mult: Decimal,
    riesgo_activo_mult: Decimal,
    uso_intensivo_mult: Decimal,
    liquidez_mult: Decimal,
) -> dict[str, Any]:
    n = max(int(plazo_meses), 1)
    lgd = lgd_pct / Decimal("100")
    el = pd * lgd * ead * riesgo_sector_mult * riesgo_activo_mult * uso_intensivo_mult * liquidez_mult
    mensual = (el / Decimal(n)).quantize(Decimal("1"))
    return {
        "pd": float(pd),
        "lgd_decimal": float(lgd),
        "ead": float(ead),
        "prima_riesgo_total_esperada": float(el),
        "prima_riesgo_mensual": float(mensual),
    }
