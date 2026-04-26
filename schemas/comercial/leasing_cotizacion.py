# schemas/comercial/leasing_cotizacion.py
# -*- coding: utf-8 -*-
from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


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

    estado: str = Field(default="PENDIENTE", max_length=40)
    contrato_activo: bool = False


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

    model_config = ConfigDict(extra="forbid")


class LeasingCotizacionRead(LeasingCotizacionBase):
    id: int
    creado_en: Optional[datetime] = None
    actualizado_en: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)
