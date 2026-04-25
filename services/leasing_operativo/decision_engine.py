# services/leasing_operativo/decision_engine.py
# -*- coding: utf-8 -*-
"""Motor de decisión: APROBAR / OBSERVAR / RECHAZAR según VAN, TIR, margen, LTV."""
from __future__ import annotations

from decimal import Decimal
from typing import Any


def evaluar_decision(
    *,
    van: Decimal,
    tir_anual_pct: Decimal | None,
    margen_op_promedio_pct: Decimal,
    ltv_pct: Decimal,
    params: dict[str, Any],
) -> dict[str, Any]:
    van_min = Decimal(str(params.get("van_minimo", 0)))
    tir_min = Decimal(str(params.get("tir_minima_anual_pct", 10)))
    margen_min = Decimal(str(params.get("margen_op_minimo_pct", 5)))
    ltv_max = Decimal(str(params.get("ltv_max_pct", 92)))

    motivos: list[str] = []
    critico = False
    observar = False

    if van < van_min:
        critico = True
        motivos.append(f"VAN ({float(van):,.0f}) inferior al mínimo ({float(van_min):,.0f}).")

    if tir_anual_pct is not None and tir_anual_pct < tir_min:
        critico = True
        motivos.append(f"TIR anual ({float(tir_anual_pct):.2f}%) bajo mínimo ({float(tir_min):.2f}%).")

    if margen_op_promedio_pct < margen_min:
        observar = True
        motivos.append(f"Margen operacional promedio ({float(margen_op_promedio_pct):.2f}%) bajo objetivo ({float(margen_min):.2f}%).")

    if ltv_pct > ltv_max:
        critico = True
        motivos.append(f"LTV ({float(ltv_pct):.2f}%) supera tope ({float(ltv_max):.2f}%).")

    if critico:
        codigo = "RECHAZAR"
    elif observar:
        codigo = "OBSERVAR"
    else:
        codigo = "APROBAR"
        motivos.append("VAN, TIR y LTV dentro de política; margen operativo aceptable.")

    return {
        "decision_codigo": codigo,
        "decision_detalle": " ".join(motivos)[:4000],
    }
