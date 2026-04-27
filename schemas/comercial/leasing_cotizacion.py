# schemas/comercial/leasing_cotizacion.py
# -*- coding: utf-8 -*-
from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field

ESTADOS_LF = {
    "BORRADOR",
    "COTIZADA",
    "EN_ANALISIS_COMERCIAL",
    "EN_ANALISIS_CREDITO",
    "APROBADA_CONDICIONES",
    "APROBADA",
    "RECHAZADA",
    "EN_FORMALIZACION",
    "DOCUMENTACION_COMPLETA",
    "ACTIVADA",
    "VIGENTE",
    "ANULADA",
    "PERDIDA_CLIENTE",
}


class LeasingCotizacionBase(BaseModel):
    cliente_id: int
    monto: Optional[Decimal] = None
    moneda: str = "CLP"
    tasa: Optional[Decimal] = None
    plazo: Optional[int] = None
    opcion_compra: Optional[Decimal] = None
    periodos_gracia: Optional[int] = 0
    fecha_inicio: Optional[date] = None

    valor_neto: Optional[Decimal] = None
    pago_inicial_tipo: Optional[str] = None
    pago_inicial_valor: Optional[Decimal] = None

    financia_seguro: bool = False
    seguro_monto_uf: Optional[Decimal] = None
    otros_montos_pesos: Optional[Decimal] = None
    concesionario: Optional[str] = None
    ejecutivo: Optional[str] = None
    fecha_cotizacion: Optional[date] = None
    uf_valor: Optional[Decimal] = None
    monto_financiado: Optional[Decimal] = None
    dolar_valor: Optional[Decimal] = None

    estado: str = Field(default="BORRADOR", max_length=40)
    contrato_activo: bool = False
    numero_operacion: Optional[str] = None
    numero_contrato: Optional[str] = None
    asiento_id: Optional[int] = None
    fecha_aprobacion: Optional[date] = None
    fecha_formalizacion: Optional[date] = None
    fecha_activacion: Optional[date] = None
    fecha_vigencia_desde: Optional[date] = None
    fecha_vigencia_hasta: Optional[date] = None


class LeasingCotizacionCreate(LeasingCotizacionBase):
    pass


class LeasingCotizacionUpdate(BaseModel):
    monto: Optional[Decimal] = None
    moneda: Optional[str] = None
    tasa: Optional[Decimal] = None
    plazo: Optional[int] = None
    opcion_compra: Optional[Decimal] = None
    periodos_gracia: Optional[int] = None
    fecha_inicio: Optional[date] = None
    valor_neto: Optional[Decimal] = None
    pago_inicial_tipo: Optional[str] = None
    pago_inicial_valor: Optional[Decimal] = None
    financia_seguro: Optional[bool] = None
    seguro_monto_uf: Optional[Decimal] = None
    otros_montos_pesos: Optional[Decimal] = None
    concesionario: Optional[str] = None
    ejecutivo: Optional[str] = None
    fecha_cotizacion: Optional[date] = None
    uf_valor: Optional[Decimal] = None
    monto_financiado: Optional[Decimal] = None
    dolar_valor: Optional[Decimal] = None
    estado: Optional[str] = None
    contrato_activo: Optional[bool] = None
    numero_operacion: Optional[str] = None
    numero_contrato: Optional[str] = None
    asiento_id: Optional[int] = None
    fecha_aprobacion: Optional[date] = None
    fecha_formalizacion: Optional[date] = None
    fecha_activacion: Optional[date] = None
    fecha_vigencia_desde: Optional[date] = None
    fecha_vigencia_hasta: Optional[date] = None

    model_config = ConfigDict(extra="forbid")


class LeasingCotizacionRead(LeasingCotizacionBase):
    id: int
    creado_en: Optional[datetime] = None
    actualizado_en: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)
