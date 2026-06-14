# services/leasing_operativo/amortizacion.py
# -*- coding: utf-8 -*-
"""
Tabla de amortización operacional LOP (lessor).

A diferencia del leasing financiero (principal + interés), la renta se descompone en:
recupero de inversión (depreciación económica), costo de fondo, costos operativos,
prima de riesgo, costo comercial y margen operacional.
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal, ROUND_HALF_UP
from typing import Any

from schemas.leasing_operativo.amortizacion import AmortizacionOperacionalCuota


def _q2(v: Decimal) -> Decimal:
    return v.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def calcular_tabla_amortizacion_operacional(
    *,
    capex_total: Decimal,
    valor_residual: Decimal,
    plazo_meses: int,
    flujo_mensual: list[dict[str, Any]],
    fecha_inicio: date | None = None,
) -> list[AmortizacionOperacionalCuota]:
    """Construye cronograma de recupero de inversión desde flujo del motor económico."""
    n = max(int(plazo_meses), 1)
    capex = _q2(Decimal(str(capex_total or 0)))
    residual = _q2(Decimal(str(valor_residual or 0)))
    if residual > capex:
        residual = capex
    filas_flujo = flujo_mensual or []
    if len(filas_flujo) < n:
        filas_flujo = filas_flujo + [{}] * (n - len(filas_flujo))

    dep_uniforme = _q2((capex - residual) / Decimal(n)) if n else Decimal("0")
    saldo = capex
    tabla: list[AmortizacionOperacionalCuota] = []
    fi = fecha_inicio

    for i in range(n):
        row = filas_flujo[i] if i < len(filas_flujo) else {}
        mes = int(row.get("mes") or (i + 1))
        renta = _q2(Decimal(str(row.get("venta") or 0)))
        costo_fondo = _q2(Decimal(str(row.get("costo_fondo") or 0)))
        dep = _q2(Decimal(str(row.get("depreciacion") or dep_uniforme)))
        op = _q2(Decimal(str(row.get("costos_operativos") or 0)))
        riesgo = _q2(Decimal(str(row.get("prima_riesgo") or 0)))
        comercial = _q2(Decimal(str(row.get("comercial") or 0)))
        margen = _q2(Decimal(str(row.get("resultado_operacional") or (renta - costo_fondo - dep - op - riesgo - comercial))))

        saldo_inicial = _q2(saldo)
        recupero = min(dep, saldo_inicial - residual) if saldo_inicial > residual else Decimal("0")
        if recupero < 0:
            recupero = Decimal("0")
        saldo_final = _q2(max(saldo_inicial - recupero, residual))
        saldo = saldo_final

        fv = None
        if fi is not None:
            from services.leasing_operativo.cronograma import _add_months

            fv = _add_months(fi, mes)

        tabla.append(
            AmortizacionOperacionalCuota(
                numero_cuota=mes,
                fecha_cuota=fv,
                saldo_inversion_inicial=saldo_inicial,
                renta_neta=renta,
                costo_fondo=costo_fondo,
                recupero_inversion=recupero,
                costos_operativos=op,
                prima_riesgo=riesgo,
                costo_comercial=comercial,
                margen_operacional=margen,
                flujo_neto_inversionista=_q2(margen + costo_fondo),
                saldo_inversion_final=saldo_final,
            )
        )
    return tabla


def totales_amortizacion_operacional(tabla: list[AmortizacionOperacionalCuota]) -> dict[str, Decimal]:
    if not tabla:
        return {
            "total_rentas": Decimal("0"),
            "total_recupero": Decimal("0"),
            "total_margen": Decimal("0"),
            "total_costo_fondo": Decimal("0"),
        }
    return {
        "total_rentas": _q2(sum((c.renta_neta for c in tabla), Decimal("0"))),
        "total_recupero": _q2(sum((c.recupero_inversion for c in tabla), Decimal("0"))),
        "total_margen": _q2(sum((c.margen_operacional for c in tabla), Decimal("0"))),
        "total_costo_fondo": _q2(sum((c.costo_fondo for c in tabla), Decimal("0"))),
    }
