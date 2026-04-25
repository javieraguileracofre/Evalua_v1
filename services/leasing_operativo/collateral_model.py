# services/leasing_operativo/collateral_model.py
# -*- coding: utf-8 -*-
"""Collateral / recupero: valor neto de liquidación, LTV, LGD, recovery rate."""
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


def analizar_collateral(
    *,
    valor_mercado: Decimal,
    costo_repossession: Decimal,
    costo_legal: Decimal,
    transporte: Decimal,
    reacondicionamiento: Decimal,
    descuento_venta_forzada_pct: Decimal,
    meses_liquidacion: int,
    tasa_fin_liquidacion_mensual: Decimal,
    ead: Decimal,
) -> dict[str, Any]:
    desc = valor_mercado * (descuento_venta_forzada_pct / Decimal("100"))
    base_costs = costo_repossession + costo_legal + transporte + reacondicionamiento + desc
    m = max(int(meses_liquidacion), 0)
    fin_liq = valor_mercado * tasa_fin_liquidacion_mensual * Decimal(m)
    net_recovery = valor_mercado - base_costs - fin_liq
    net_recovery = max(net_recovery, Decimal("0")).quantize(Decimal("1"))

    ltv = Decimal("0")
    if valor_mercado > 0:
        ltv = (ead / valor_mercado * Decimal("100")).quantize(Decimal("0.01"))

    recovery_rate = Decimal("0")
    if ead > 0:
        recovery_rate = (net_recovery / ead * Decimal("100")).quantize(Decimal("0.01"))
    recovery_rate = min(recovery_rate, Decimal("100"))

    lgd = max(Decimal("0"), min(Decimal("100"), Decimal("100") - recovery_rate))

    return {
        "collateral_valor_mercado": float(valor_mercado),
        "collateral_neto_liquidacion": float(net_recovery),
        "ltv_pct": float(ltv),
        "lgd_pct": float(lgd),
        "recovery_rate_pct": float(recovery_rate),
        "costos_recupero_total": float(base_costs + fin_liq),
    }
