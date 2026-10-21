# schemas/leasing_operativo/residual_value.py
# -*- coding: utf-8 -*-
from __future__ import annotations

from decimal import Decimal
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class ResidualCalculateRequest(BaseModel):
    marca: str = ""
    modelo: str = ""
    version: str = ""
    anio: int | None = None
    valor_adquisicion: Decimal = Decimal("0")
    plazo_meses: int = Field(36, ge=1, le=120)
    km_inicial: Decimal = Decimal("0")
    km_anual: Decimal = Decimal("40000")
    km_mensual: Decimal | None = None
    tipo_uso: str = "MIXTO"
    tipo_contrato: str = "ARRENDAMIENTO_OPERATIVO"
    tipo_activo_id: int | None = None
    consultar_mercado: bool = True


class ResidualOverrideRequest(BaseModel):
    model_config = ConfigDict(protected_namespaces=())

    cotizacion_id: int | None = None
    unidad_id: str = ""
    valor_anterior: Decimal
    valor_nuevo: Decimal
    motivo: str = Field(..., min_length=3, max_length=200)
    observacion: str = ""
    model_version: str = ""


class ResidualEngineResponse(BaseModel):
    model_config = ConfigDict(protected_namespaces=())

    model_version: str
    valor_residual_sugerido: float
    escenarios: dict[str, Any] = Field(default_factory=dict)
    VALOR_RECUPERO_NETO: float | None = None
    VALOR_LIBROS_FINAL: float | None = None
    RESULTADO_ESPERADO_VENTA: float | None = None
    MANUAL_OVERRIDE: bool = False
