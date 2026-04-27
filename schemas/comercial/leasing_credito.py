# schemas/comercial/leasing_credito.py
# -*- coding: utf-8 -*-
from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Literal, Optional

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

    score_buro: Optional[int] = Field(default=None, ge=0, le=1000)
    comportamiento_pago: ComportamientoPago = "SIN_HISTORIAL"
    ltv_pct: Decimal = Field(default=Decimal("0"), ge=0, le=300)
    dscr: Optional[Decimal] = None
    leverage_ratio: Optional[Decimal] = None
    supuestos: str = ""


class LeasingCreditoResultado(BaseModel):
    score_total: Decimal = Field(default=Decimal("0"), ge=0, le=100)
    rating: Rating = "E"
    recomendacion: Recomendacion = "RECHAZADO"
    nivel_riesgo: NivelRiesgo = "ALTO"
    motivo_resumen: str = ""
    dscr_calculado: Optional[Decimal] = None
    leverage_calculado: Optional[Decimal] = None


class LeasingCreditoOut(LeasingCreditoInput, LeasingCreditoResultado):
    id: int
    cotizacion_id: int
    cliente_id: int
    analista: str = "sistema"
    creado_en: Optional[datetime] = None
    actualizado_en: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)
