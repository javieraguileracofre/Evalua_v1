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
    capital_financiado: Decimal | None = None,
    valor_vehiculo: Decimal | None = None,
) -> dict[str, Any]:
    """
    LTV comercial (leasing): capital_financiado / valor_vehiculo.

    - capital_financiado: CAPEX neto de pie (exposición inicial del lessor).
    - valor_vehiculo: precio/valor del bien (no el neto de liquidación forzosa).
    EAD se usa solo para recovery rate / LGD de recupero.
    """
    desc = valor_mercado * (descuento_venta_forzada_pct / Decimal("100"))
    base_costs = costo_repossession + costo_legal + transporte + reacondicionamiento + desc
    m = max(int(meses_liquidacion), 0)
    fin_liq = valor_mercado * tasa_fin_liquidacion_mensual * Decimal(m)
    net_recovery = valor_mercado - base_costs - fin_liq
    net_recovery = max(net_recovery, Decimal("0")).quantize(Decimal("1"))

    # Numerador / denominador LTV explícitos
    capital = _d(capital_financiado if capital_financiado is not None else ead)
    vehiculo = _d(valor_vehiculo if valor_vehiculo is not None else valor_mercado)
    ltv = Decimal("0")
    if vehiculo > 0:
        ltv = (capital / vehiculo * Decimal("100")).quantize(Decimal("0.01"))

    recovery_rate = Decimal("0")
    if ead > 0:
        recovery_rate = (net_recovery / ead * Decimal("100")).quantize(Decimal("0.01"))
    recovery_rate = min(recovery_rate, Decimal("100"))

    lgd = max(Decimal("0"), min(Decimal("100"), Decimal("100") - recovery_rate))

    return {
        "collateral_valor_mercado": float(valor_mercado),
        "collateral_neto_liquidacion": float(net_recovery),
        "valor_vehiculo": float(vehiculo),
        "capital_financiado": float(capital),
        "ltv_pct": float(ltv),
        "ltv_formula": "capital_financiado / valor_vehiculo",
        "lgd_pct": float(lgd),
        "recovery_rate_pct": float(recovery_rate),
        "costos_recupero_total": float(base_costs + fin_liq),
    }
