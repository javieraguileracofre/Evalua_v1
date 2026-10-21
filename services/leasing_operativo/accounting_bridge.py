# services/leasing_operativo/accounting_bridge.py
# -*- coding: utf-8 -*-
"""
Puente contable LOP residual.

NO genera asientos definitivos hasta validar naturaleza tributaria/contable.
Expone payload listo para el módulo de contabilización EvaluaERP.
"""
from __future__ import annotations

from typing import Any


def build_accounting_payload(
    *,
    costo_activo: float,
    depreciacion_acumulada: float,
    valor_libro: float,
    precio_venta_esperado: float | None = None,
    costos_venta: float | None = None,
    iva_pct: float = 19.0,
    tipo_contrato: str = "ARRENDAMIENTO_OPERATIVO",
) -> dict[str, Any]:
    venta = float(precio_venta_esperado or 0)
    costos = float(costos_venta or 0)
    resultado = venta - float(valor_libro) if precio_venta_esperado is not None else None
    return {
        "ready_for_posting": False,
        "motivo_bloqueo": (
            "Asientos diferidos: validar naturaleza tributaria/contable del contrato "
            f"({tipo_contrato}) antes de contabilizar venta/depreciación definitiva."
        ),
        "payload": {
            "costo_activo": float(costo_activo),
            "depreciacion_acumulada": float(depreciacion_acumulada),
            "valor_libro": float(valor_libro),
            "venta_activo": venta if precio_venta_esperado is not None else None,
            "costo_venta": costos if costos_venta is not None else None,
            "resultado_venta": resultado,
            "iva_pct": float(iva_pct),
            "ganancia_perdida": (
                "GANANCIA" if resultado is not None and resultado >= 0 else ("PERDIDA" if resultado is not None else None)
            ),
            "tipo_contrato": tipo_contrato,
        },
    }
