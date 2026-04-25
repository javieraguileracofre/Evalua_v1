# services/leasing_operativo/residual_model.py
# -*- coding: utf-8 -*-
"""Valor residual automático: base por tipo/plazo + factores (marca, uso, liquidez, escenario)."""
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


def residual_base_valor(
    capex_total: Decimal,
    residual_base_pct: Decimal,
    plazo_meses: int,
) -> Decimal:
    """% base del tipo ajustado levemente por plazo (plazos largos reducen % residual típico)."""
    n = max(int(plazo_meses), 1)
    adj = Decimal("1") - (min(n, 84) * Decimal("0.0008"))
    adj = max(adj, Decimal("0.88"))
    pct = (residual_base_pct / Decimal("100")) * adj
    return (capex_total * pct).quantize(Decimal("1"))


def residual_ajustado(
    *,
    valor_base: Decimal,
    capex_total: Decimal,
    residual_max_pct: Decimal,
    scenario_mult: Decimal,
    liquidez_factor: Decimal,
    obsolescencia_factor: Decimal,
    desgaste_km_factor: Decimal,
    desgaste_hora_factor: Decimal,
    haircut_pct: Decimal,
    km_anual: Decimal,
    horas_anual: Decimal,
    marca_modelo_factor: Decimal,
    sector_economico_mult: Decimal,
    inflacion_activo_pct_anual: Decimal,
    condicion_factor: Decimal,
) -> dict[str, Any]:
    """
    valor_residual_ajustado = base * Π factores, tope % máximo sobre CAPEX, haircut conservador.
    """
    f_uso = Decimal("1") - (km_anual * desgaste_km_factor) - (horas_anual * desgaste_hora_factor)
    f_uso = max(f_uso, Decimal("0.65"))

    f_marca = max(min(marca_modelo_factor, Decimal("1.15")), Decimal("0.85"))
    f_cond = max(min(condicion_factor, Decimal("1.05")), Decimal("0.80"))
    f_inf = Decimal("1") + (inflacion_activo_pct_anual / Decimal("100")) * Decimal("0.35")

    raw = (
        valor_base
        * scenario_mult
        * liquidez_factor
        * obsolescencia_factor
        * f_uso
        * f_marca
        * sector_economico_mult
        * f_inf
        * f_cond
    )
    cap_max = capex_total * (residual_max_pct / Decimal("100"))
    capped = min(raw, cap_max)
    hc = haircut_pct / Decimal("100")
    final = capped * (Decimal("1") - hc)
    final = max(final, Decimal("0")).quantize(Decimal("1"))

    return {
        "valor_residual_base": float(valor_base),
        "valor_residual_ajustado": float(final),
        "factor_uso": float(f_uso),
        "factor_marca": float(f_marca),
        "tope_capex_pct": float(residual_max_pct),
        "haircut_pct": float(haircut_pct),
    }
