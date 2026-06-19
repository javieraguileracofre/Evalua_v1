# schemas/leasing_operativo/simulacion.py
# -*- coding: utf-8 -*-
"""Esquemas Pydantic para leasing operativo."""
from __future__ import annotations

from decimal import Decimal
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator


EscenarioLOP = Literal["CONSERVADOR", "BASE", "OPTIMISTA", "ESTRES"]
MetodoPricingLOP = Literal["COSTO_SPREAD", "MARGEN_VENTA", "TIR_OBJETIVO"]
IndexacionTipoLOP = Literal["NINGUNA", "UF", "IPC"]


class SimulacionLOPCreate(BaseModel):
    tipo_activo_id: int = Field(..., gt=0)
    cliente_id: int | None = None
    nombre: str = Field("", max_length=200)
    plazo_meses: int = Field(36, ge=1, le=120)
    escenario: EscenarioLOP = "BASE"
    metodo_pricing: MetodoPricingLOP = "COSTO_SPREAD"
    margen_pct: Decimal | None = None
    spread_pct: Decimal | None = None
    tir_objetivo: Decimal | None = None
    moneda: str = Field("CLP", max_length=8)
    iva_pct: Decimal = Field(Decimal("19"), ge=0, le=100)
    indexacion_tipo: IndexacionTipoLOP = "NINGUNA"
    indexacion_pct: Decimal = Field(Decimal("0"), ge=0, le=50)
    pie_inicial_pct: Decimal = Field(Decimal("0"), ge=0, le=100)
    opcion_compra_pct: Decimal = Field(Decimal("0"), ge=0, le=100)

    @field_validator("nombre")
    @classmethod
    def strip_nombre(cls, v: str) -> str:
        return (v or "").strip()


class ContratoLOPCreate(BaseModel):
    simulacion_id: int = Field(..., gt=0)
    fecha_inicio: str | None = None
    indexacion_tipo: IndexacionTipoLOP = "NINGUNA"
    indexacion_pct: Decimal = Field(Decimal("0"), ge=0, le=50)


class FacturacionPeriodoLOP(BaseModel):
    periodo_yyyymm: str = Field(..., min_length=6, max_length=6, pattern=r"^\d{6}$")

    @field_validator("periodo_yyyymm")
    @classmethod
    def validar_mes(cls, v: str) -> str:
        m = int(v[4:6])
        if m < 1 or m > 12:
            raise ValueError("Mes del periodo debe estar entre 01 y 12.")
        return v


class RenovacionLOPCreate(BaseModel):
    plazo_meses: int = Field(12, ge=1, le=120)
    renta_mensual: Decimal = Field(..., gt=0)
    indexacion_tipo: IndexacionTipoLOP = "NINGUNA"
    indexacion_pct: Decimal = Field(Decimal("0"), ge=0, le=50)
    motivo: str = Field("", max_length=2000)


class HubResumenLOP(BaseModel):
    kpis: dict[str, int]
    funnel: list[dict[str, Any]]
    pipeline_montos: dict[str, float]
    cartera_montos: dict[str, float]
    tasa_cierre_pct: float | None = None
    margen_pipeline_pct: float | None = None
    tir_pipeline_pct: float | None = None
    alertas_observar: int = 0


class LOPPreviewRequest(BaseModel):
    tipo_activo_id: int = Field(..., gt=0)
    cliente_id: int | None = None
    plazo_meses: int = Field(36, ge=1, le=120)
    escenario: EscenarioLOP = "BASE"
    metodo_pricing: MetodoPricingLOP = "COSTO_SPREAD"
    spread_pct: Decimal | None = None
    margen_pct: Decimal | None = None
    tir_objetivo: Decimal | None = None
    moneda: str = Field("CLP", max_length=8)
    iva_pct: Decimal = Field(Decimal("19"), ge=0, le=100)
    indexacion_tipo: IndexacionTipoLOP = "NINGUNA"
    indexacion_pct: Decimal = Field(Decimal("0"), ge=0, le=50)
    pie_inicial_pct: Decimal = Field(Decimal("0"), ge=0, le=100)
    opcion_compra_pct: Decimal = Field(Decimal("0"), ge=0, le=100)
    inputs: dict[str, Any] = Field(default_factory=dict)
    incluir_sensibilidad: bool = False
    incluir_escenarios: bool = False


class LOPPreviewResponse(BaseModel):
    inputs: dict[str, Any]
    result: dict[str, Any]
    sensibilidad: dict[str, Any] | None = None
    escenarios: dict[str, Any] | None = None
