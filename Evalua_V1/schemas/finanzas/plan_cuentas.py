# schemas/finanzas/plan_cuentas.py
# -*- coding: utf-8 -*-
from __future__ import annotations

from pydantic import BaseModel, Field


class PlanCuentaBase(BaseModel):
    codigo: str = Field(..., min_length=1, max_length=30)
    nombre: str = Field(..., min_length=1, max_length=180)
    nivel: int = Field(default=1, ge=1, le=9)
    cuenta_padre_id: int | None = None
    tipo: str = Field(..., min_length=1, max_length=30)
    clasificacion: str = Field(..., min_length=1, max_length=50)
    naturaleza: str = Field(..., min_length=1, max_length=20)
    acepta_movimiento: bool = True
    requiere_centro_costo: bool = False
    estado: str = Field(default="ACTIVO", min_length=1, max_length=20)
    descripcion: str | None = None


class PlanCuentaCreate(PlanCuentaBase):
    pass


class PlanCuentaUpdate(BaseModel):
    codigo: str | None = Field(default=None, min_length=1, max_length=30)
    nombre: str | None = Field(default=None, min_length=1, max_length=180)
    nivel: int | None = Field(default=None, ge=1, le=9)
    cuenta_padre_id: int | None = None
    tipo: str | None = Field(default=None, min_length=1, max_length=30)
    clasificacion: str | None = Field(default=None, min_length=1, max_length=50)
    naturaleza: str | None = Field(default=None, min_length=1, max_length=20)
    acepta_movimiento: bool | None = None
    requiere_centro_costo: bool | None = None
    estado: str | None = Field(default=None, min_length=1, max_length=20)
    descripcion: str | None = None