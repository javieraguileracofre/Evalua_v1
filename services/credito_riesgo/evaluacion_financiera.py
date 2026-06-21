# services/credito_riesgo/evaluacion_financiera.py
# -*- coding: utf-8 -*-
"""Ratios y métricas financieras para evaluación crediticia empresarial."""
from __future__ import annotations

from dataclasses import dataclass, field
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


@dataclass
class EvaluacionFinanciera:
    liquidez_corriente: Decimal | None
    endeudamiento_total_pct: Decimal | None
    endeudamiento_financiero_pct: Decimal | None
    margen_ebitda_pct: Decimal | None
    cobertura_gastos_financieros: Decimal | None
    flujo_operacional_mensual: Decimal
    dscr: Decimal | None
    rentabilidad_neta_pct: Decimal | None
    patrimonio: Decimal
    capital_trabajo: Decimal
    morosidad_historica_dias: int
    alertas: list[str] = field(default_factory=list)
    detalle: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        def f(x: Decimal | None) -> float | None:
            return float(x) if x is not None else None

        return {
            "liquidez_corriente": f(self.liquidez_corriente),
            "endeudamiento_total_pct": f(self.endeudamiento_total_pct),
            "endeudamiento_financiero_pct": f(self.endeudamiento_financiero_pct),
            "margen_ebitda_pct": f(self.margen_ebitda_pct),
            "cobertura_gastos_financieros": f(self.cobertura_gastos_financieros),
            "flujo_operacional_mensual": float(self.flujo_operacional_mensual),
            "dscr": f(self.dscr),
            "rentabilidad_neta_pct": f(self.rentabilidad_neta_pct),
            "patrimonio": float(self.patrimonio),
            "capital_trabajo": float(self.capital_trabajo),
            "morosidad_historica_dias": self.morosidad_historica_dias,
            "alertas": self.alertas,
            **self.detalle,
        }


def evaluar_financiero(
    *,
    segmento: str,
    ventas_anual: Any,
    ebitda_anual: Any,
    utilidad_neta_anual: Any,
    deuda_total: Any,
    deuda_financiera: Any,
    patrimonio: Any,
    liquidez_corriente: Any | None,
    flujo_caja_mensual: Any,
    capital_trabajo: Any,
    gastos_financieros_anual: Any,
    cuota_propuesta: Any,
    mora_max_dias_12m: Any,
) -> EvaluacionFinanciera:
    ventas = _d(ventas_anual)
    ebitda = _d(ebitda_anual)
    utilidad = _d(utilidad_neta_anual)
    deuda = _d(deuda_total)
    deuda_fin = _d(deuda_financiera) if _d(deuda_financiera) > 0 else deuda
    pat = _d(patrimonio)
    liq = _d(liquidez_corriente) if liquidez_corriente is not None else None
    fcf = _d(flujo_caja_mensual)
    ct = _d(capital_trabajo)
    gf = _d(gastos_financieros_anual)
    cuota = _d(cuota_propuesta)
    mora = int(mora_max_dias_12m or 0)
    alertas: list[str] = []

    endeud_total = (deuda / pat * Decimal("100")) if pat > 0 else None
    endeud_fin = (deuda_fin / pat * Decimal("100")) if pat > 0 else None
    margen_ebitda = (ebitda / ventas * Decimal("100")) if ventas > 0 else None
    rent_neta = (utilidad / ventas * Decimal("100")) if ventas > 0 else None
    cob_gf = (ebitda / gf) if gf > 0 else None
    dscr = (fcf / cuota) if cuota > 0 else None

    if liq is not None and liq < Decimal("1"):
        alertas.append("Liquidez corriente inferior a 1,0: riesgo de caja.")
    if endeud_total is not None and endeud_total > Decimal("300"):
        alertas.append("Endeudamiento total/patrimonio superior a 300%.")
    if margen_ebitda is not None and margen_ebitda < Decimal("5") and segmento != "PYME":
        alertas.append("Margen EBITDA bajo para segmento analizado.")
    if dscr is not None and dscr < Decimal("1.15"):
        alertas.append(f"DSCR {float(dscr):.2f} bajo umbral de aprobación típico (1,15).")
    if mora >= 90:
        alertas.append("Morosidad histórica 90+ días: deterioro de comportamiento de pago.")
    if ct < 0:
        alertas.append("Capital de trabajo negativo.")

    seg = segmento.upper()
    if seg == "PYME" and fcf <= 0:
        alertas.append("Flujo de caja operacional nulo o negativo (crítico en PYME).")
    if seg == "GRAN_EMPRESA" and cob_gf is not None and cob_gf < Decimal("2"):
        alertas.append("Cobertura de gastos financieros débil (<2x EBITDA) en Gran Empresa.")

    return EvaluacionFinanciera(
        liquidez_corriente=liq,
        endeudamiento_total_pct=endeud_total,
        endeudamiento_financiero_pct=endeud_fin,
        margen_ebitda_pct=margen_ebitda,
        cobertura_gastos_financieros=cob_gf,
        flujo_operacional_mensual=fcf,
        dscr=dscr,
        rentabilidad_neta_pct=rent_neta,
        patrimonio=pat,
        capital_trabajo=ct,
        morosidad_historica_dias=mora,
        alertas=alertas,
        detalle={"segmento_evaluado": seg},
    )
