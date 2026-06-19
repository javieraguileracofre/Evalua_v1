# services/leasing_operativo/decision_engine.py
# -*- coding: utf-8 -*-
"""Motor de decisión LOP v2: APROBAR / OBSERVAR / RECHAZAR."""
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
    spread_sobre_costo_pct: Decimal | None = None,
    payback_meses: int | None = None,
    recovery_rate_pct: Decimal | None = None,
    warnings: list[str] | None = None,
) -> dict[str, Any]:
    van_min = Decimal(str(params.get("van_minimo", 0)))
    tir_min = Decimal(str(params.get("tir_minima_anual_pct", 10)))
    margen_min = Decimal(str(params.get("margen_op_minimo_pct", 5)))
    ltv_max = Decimal(str(params.get("ltv_max_pct", 92)))
    spread_min = Decimal(str(params.get("spread_minimo_sobre_costo_pct", 0)))
    payback_max = int(params.get("payback_max_meses", 0) or 0)
    recovery_min = Decimal(str(params.get("recovery_min_pct", 0)))

    motivos: list[str] = []
    reglas: list[dict[str, Any]] = []
    critico = False
    observar = False

    def _reg(codigo: str, ok: bool, detalle: str, severidad: str = "CRITICO") -> None:
        reglas.append({"codigo": codigo, "ok": ok, "detalle": detalle, "severidad": severidad})
        if not ok:
            if severidad == "CRITICO":
                nonlocal_critico[0] = True
            else:
                nonlocal_observar[0] = True
            motivos.append(detalle)

    nonlocal_critico = [critico]
    nonlocal_observar = [observar]

    _reg(
        "VAN_MIN",
        van >= van_min,
        f"VAN ({float(van):,.0f}) inferior al mínimo ({float(van_min):,.0f}).",
    )

    if tir_anual_pct is not None:
        _reg(
            "TIR_MIN",
            tir_anual_pct >= tir_min,
            f"TIR anual ({float(tir_anual_pct):.2f}%) bajo mínimo ({float(tir_min):.2f}%).",
        )
    else:
        _reg("TIR_MIN", False, "No se pudo calcular TIR anual.", "CRITICO")

    _reg(
        "MARGEN_OP",
        margen_op_promedio_pct >= margen_min,
        f"Margen operacional promedio ({float(margen_op_promedio_pct):.2f}%) bajo objetivo ({float(margen_min):.2f}%).",
        "OBSERVACION",
    )

    _reg(
        "LTV_MAX",
        ltv_pct <= ltv_max,
        f"LTV ({float(ltv_pct):.2f}%) supera tope ({float(ltv_max):.2f}%).",
    )

    if spread_sobre_costo_pct is not None and spread_min > 0:
        _reg(
            "SPREAD_MIN",
            spread_sobre_costo_pct >= spread_min,
            f"Spread sobre costo ({float(spread_sobre_costo_pct):.2f}%) bajo mínimo ({float(spread_min):.2f}%).",
            "OBSERVACION",
        )

    if payback_max > 0 and payback_meses is not None:
        _reg(
            "PAYBACK_MAX",
            payback_meses <= payback_max,
            f"Payback ({payback_meses} meses) supera máximo ({payback_max}).",
            "OBSERVACION",
        )

    if recovery_min > 0 and recovery_rate_pct is not None:
        _reg(
            "RECOVERY_MIN",
            recovery_rate_pct >= recovery_min,
            f"Recovery rate ({float(recovery_rate_pct):.2f}%) bajo mínimo ({float(recovery_min):.2f}%).",
            "OBSERVACION",
        )

    if warnings:
        for w in warnings:
            observar = True
            nonlocal_observar[0] = True
            motivos.append(w)

    critico = nonlocal_critico[0]
    observar = nonlocal_observar[0]

    if critico:
        codigo = "RECHAZAR"
    elif observar:
        codigo = "OBSERVAR"
    else:
        codigo = "APROBAR"
        motivos.append("Indicadores dentro de política comercial LOP v2.")

    return {
        "decision_codigo": codigo,
        "decision_detalle": " ".join(motivos)[:4000],
        "decision_reglas": reglas,
    }
