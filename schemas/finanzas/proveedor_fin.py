# schemas/finanzas/proveedor_fin.py
# -*- coding: utf-8 -*-
from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator


def _to_decimal(v) -> Decimal:
    if v in (None, "", "null"):
        return Decimal("0")
    return Decimal(str(v))


class ProveedorFinBase(BaseModel):
    condicion_pago_dias: int = Field(default=30, ge=0, le=365)
    limite_credito: Decimal = Field(default=Decimal("0"))
    estado: str = Field(default="ACTIVO", min_length=1, max_length=30)
    notas: Optional[str] = None

    @field_validator("limite_credito", mode="before")
    @classmethod
    def _decimalizar(cls, v):
        return _to_decimal(v)

    @field_validator("estado", mode="before")
    @classmethod
    def _normalizar_estado(cls, v):
        if v is None:
            return "ACTIVO"
        return str(v).strip().upper() or "ACTIVO"


class ProveedorFinCreate(ProveedorFinBase):
    proveedor_id: int


class ProveedorFinUpdate(BaseModel):
    condicion_pago_dias: int = Field(default=30, ge=0, le=365)
    limite_credito: Decimal = Field(default=Decimal("0"))
    estado: str = Field(default="ACTIVO", min_length=1, max_length=30)
    notas: Optional[str] = None

    @field_validator("limite_credito", mode="before")
    @classmethod
    def _decimalizar(cls, v):
        return _to_decimal(v)

    @field_validator("estado", mode="before")
    @classmethod
    def _normalizar_estado(cls, v):
        if v is None:
            return "ACTIVO"
        return str(v).strip().upper() or "ACTIVO"


class ProveedorFinOut(ProveedorFinBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    proveedor_id: int
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None