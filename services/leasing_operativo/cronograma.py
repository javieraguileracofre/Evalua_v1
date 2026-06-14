# services/leasing_operativo/cronograma.py
# -*- coding: utf-8 -*-
"""Cronograma de cuotas de renta con indexación UF/IPC para leasing operativo."""
from __future__ import annotations

import calendar
from datetime import date
from decimal import Decimal, ROUND_HALF_UP
from typing import Any


def _add_months(d: date, months: int) -> date:
    m0 = d.month - 1 + months
    y = d.year + m0 // 12
    m = m0 % 12 + 1
    last = calendar.monthrange(y, m)[1]
    return date(y, m, min(d.day, last))


def _q4(v: Decimal) -> Decimal:
    return v.quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP)


def calcular_monto_cuota_indexada(
    *,
    nro: int,
    renta_base: Decimal,
    indexacion_tipo: str,
    indexacion_pct: Decimal,
) -> Decimal:
    """Calcula monto de cuota n con reajuste compuesto mensual (IPC) o anual prorrateado (UF)."""
    if nro <= 1 or indexacion_tipo == "NINGUNA" or indexacion_pct <= 0:
        return _q4(renta_base)
    pct = indexacion_pct / Decimal("100")
    if indexacion_tipo == "IPC":
        factor = (Decimal("1") + pct) ** Decimal(nro - 1)
        return _q4(renta_base * factor)
    if indexacion_tipo == "UF":
        # Reajuste anual en aniversario de contrato (cuotas 13, 25, …)
        anios = (nro - 1) // 12
        factor = (Decimal("1") + pct) ** Decimal(anios)
        return _q4(renta_base * factor)
    return _q4(renta_base)


def generar_cronograma_cuotas(
    *,
    plazo_meses: int,
    renta_base: Decimal,
    fecha_inicio: date,
    indexacion_tipo: str = "NINGUNA",
    indexacion_pct: Decimal | float = Decimal("0"),
) -> list[dict[str, Any]]:
    """Genera lista de cuotas con montos indexados y fechas de vencimiento."""
    n = max(int(plazo_meses), 1)
    idx_tipo = (indexacion_tipo or "NINGUNA").strip().upper()
    if idx_tipo not in {"NINGUNA", "UF", "IPC"}:
        idx_tipo = "NINGUNA"
    idx_pct = Decimal(str(indexacion_pct or 0))
    rows: list[dict[str, Any]] = []
    for k in range(1, n + 1):
        fv = _add_months(fecha_inicio, k)
        monto = calcular_monto_cuota_indexada(
            nro=k,
            renta_base=renta_base,
            indexacion_tipo=idx_tipo,
            indexacion_pct=idx_pct,
        )
        rows.append(
            {
                "nro": k,
                "fecha_vencimiento": fv,
                "monto_renta_base": _q4(renta_base),
                "monto_renta": monto,
                "estado": "PENDIENTE",
            }
        )
    return rows


def resumen_cronograma(cuotas: list[dict[str, Any]]) -> dict[str, Any]:
    """Totales del plan de cuotas para reportes."""
    if not cuotas:
        return {"cuotas": 0, "total_renta": Decimal("0"), "promedio": Decimal("0")}
    total = sum((Decimal(str(c.get("monto_renta") or 0)) for c in cuotas), Decimal("0"))
    n = len(cuotas)
    return {
        "cuotas": n,
        "total_renta": _q4(total),
        "promedio": _q4(total / Decimal(n)) if n else Decimal("0"),
        "primera": cuotas[0].get("monto_renta"),
        "ultima": cuotas[-1].get("monto_renta"),
    }
