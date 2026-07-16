# schemas/comercial/leasing_credito.py
# -*- coding: utf-8 -*-
from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field

TipoPersona = Literal["NATURAL", "JURIDICA"]
ComportamientoPago = Literal["BUENO", "REGULAR", "MALO", "SIN_HISTORIAL"]
Rating = Literal["A", "B", "C", "D", "E"]
Recomendacion = Literal["APROBADO", "RECHAZADO", "APROBADA_CONDICIONES"]
NivelRiesgo = Literal["BAJO", "MEDIO", "ALTO"]


class LeasingCreditoInput(BaseModel):
    tipo_persona: TipoPersona = "NATURAL"
    tipo_producto: str = "leasing_financiero"
    moneda_referencia: str = "CLP"

    ingreso_neto_mensual: Decimal = Field(default=Decimal("0"), ge=0)
    carga_financiera_mensual: Decimal = Field(default=Decimal("0"), ge=0)
    antiguedad_laboral_meses: int = Field(default=0, ge=0)

    ventas_anuales: Decimal = Field(default=Decimal("0"), ge=0)
    ebitda_anual: Decimal = Field(default=Decimal("0"))
    deuda_financiera_total: Decimal = Field(default=Decimal("0"), ge=0)
    patrimonio: Decimal = Field(default=Decimal("0"), ge=0)
    anios_operacion: int = Field(default=0, ge=0)

    activo_corriente: Decimal = Field(default=Decimal("0"), ge=0)
    pasivo_corriente: Decimal = Field(default=Decimal("0"), ge=0)
    activo_total: Decimal = Field(default=Decimal("0"), ge=0)
    pasivo_total: Decimal = Field(default=Decimal("0"), ge=0)
    utilidad_neta_anual: Decimal = Field(default=Decimal("0"))
    gastos_financieros_anual: Decimal = Field(default=Decimal("0"), ge=0)
    ventas_12m_iva: Decimal = Field(default=Decimal("0"), ge=0)
    iva_debito_12m: Decimal = Field(default=Decimal("0"), ge=0)
    iva_credito_12m: Decimal = Field(default=Decimal("0"), ge=0)

    score_buro: Optional[int] = Field(default=None, ge=0, le=1000)
    comportamiento_pago: ComportamientoPago = "SIN_HISTORIAL"
    ltv_pct: Decimal = Field(default=Decimal("0"), ge=0, le=300)
    dscr: Optional[Decimal] = None
    leverage_ratio: Optional[Decimal] = None
    supuestos: str = ""


class LeasingRatios(BaseModel):
    dscr: Optional[Decimal] = None
    leverage_ratio: Optional[Decimal] = None
    margen_ebitda_pct: Optional[Decimal] = None
    liquidez_corriente: Optional[Decimal] = None
    endeudamiento_pct: Optional[Decimal] = None
    capital_trabajo: Optional[Decimal] = None
    cobertura_gastos_fin: Optional[Decimal] = None
    rentabilidad_neta_pct: Optional[Decimal] = None
    servicio_deuda_proxy: Optional[Decimal] = None
    ventas_base: Optional[Decimal] = None
    alertas: list[str] = Field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        def f(x: Decimal | None) -> float | None:
            return float(x) if x is not None else None

        return {
            "dscr": f(self.dscr),
            "leverage_ratio": f(self.leverage_ratio),
            "margen_ebitda_pct": f(self.margen_ebitda_pct),
            "liquidez_corriente": f(self.liquidez_corriente),
            "endeudamiento_pct": f(self.endeudamiento_pct),
            "capital_trabajo": f(self.capital_trabajo),
            "cobertura_gastos_fin": f(self.cobertura_gastos_fin),
            "rentabilidad_neta_pct": f(self.rentabilidad_neta_pct),
            "servicio_deuda_proxy": f(self.servicio_deuda_proxy),
            "ventas_base": f(self.ventas_base),
            "alertas": list(self.alertas),
        }


class LeasingCreditoResultado(BaseModel):
    score_total: Decimal = Field(default=Decimal("0"), ge=0, le=100)
    rating: Rating = "E"
    recomendacion: Recomendacion = "RECHAZADO"
    nivel_riesgo: NivelRiesgo = "ALTO"
    motivo_resumen: str = ""
    dscr_calculado: Optional[Decimal] = None
    leverage_calculado: Optional[Decimal] = None
    liquidez_corriente: Optional[Decimal] = None
    margen_ebitda_pct: Optional[Decimal] = None
    endeudamiento_pct: Optional[Decimal] = None
    capital_trabajo: Optional[Decimal] = None
    cobertura_gastos_fin: Optional[Decimal] = None
    rentabilidad_neta_pct: Optional[Decimal] = None
    ratios_json: dict[str, Any] = Field(default_factory=dict)


class LeasingCreditoOut(LeasingCreditoInput, LeasingCreditoResultado):
    id: int
    cotizacion_id: int
    cliente_id: int
    analista: str = "sistema"
    creado_en: Optional[datetime] = None
    actualizado_en: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)
