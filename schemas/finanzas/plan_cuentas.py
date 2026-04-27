# schemas/finanzas/plan_cuentas.py
# -*- coding: utf-8 -*-
from __future__ import annotations

import re
from typing import Literal

from pydantic import BaseModel, Field, field_validator

TIPOS_PLAN_CUENTA = ("ACTIVO", "PASIVO", "PATRIMONIO", "INGRESO", "COSTO", "GASTO", "ORDEN")
NATURALEZAS_PLAN_CUENTA = ("DEUDORA", "ACREEDORA")
ESTADOS_PLAN_CUENTA = ("ACTIVO", "INACTIVO")
CODIGO_CUENTA_REGEX = re.compile(r"^\d{6}$")
CODIGO_CUENTA_ERROR = "El código de cuenta debe tener 6 dígitos y no debe incluir puntos."


def _validar_codigo_cuenta(value: str | None) -> str | None:
    if value is None:
        return value
    normalized = value.strip()
    if not CODIGO_CUENTA_REGEX.fullmatch(normalized):
        raise ValueError(CODIGO_CUENTA_ERROR)
    return normalized


class PlanCuentaBase(BaseModel):
    codigo: str = Field(..., min_length=6, max_length=6)
    nombre: str = Field(..., min_length=1, max_length=180)
    nivel: int = Field(default=1, ge=1, le=9)
    cuenta_padre_id: int | None = None
    tipo: Literal["ACTIVO", "PASIVO", "PATRIMONIO", "INGRESO", "COSTO", "GASTO", "ORDEN"]
    clasificacion: str = Field(..., min_length=1, max_length=50)
    naturaleza: Literal["DEUDORA", "ACREEDORA"]
    acepta_movimiento: bool = True
    requiere_centro_costo: bool = False
    estado: Literal["ACTIVO", "INACTIVO"] = "ACTIVO"
    descripcion: str | None = None

    @field_validator("codigo")
    @classmethod
    def validar_codigo(cls, value: str) -> str:
        return _validar_codigo_cuenta(value) or ""


class PlanCuentaCreate(PlanCuentaBase):
    pass


class PlanCuentaUpdate(BaseModel):
    codigo: str | None = Field(default=None, min_length=6, max_length=6)
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

    @field_validator("codigo")
    @classmethod
    def validar_codigo(cls, value: str | None) -> str | None:
        return _validar_codigo_cuenta(value)

    @field_validator("tipo")
    @classmethod
    def validar_tipo(cls, value: str | None) -> str | None:
        if value is None:
            return value
        normalized = value.strip().upper()
        if normalized not in TIPOS_PLAN_CUENTA:
            raise ValueError(f"tipo invalido: {normalized}")
        return normalized

    @field_validator("naturaleza")
    @classmethod
    def validar_naturaleza(cls, value: str | None) -> str | None:
        if value is None:
            return value
        normalized = value.strip().upper()
        if normalized not in NATURALEZAS_PLAN_CUENTA:
            raise ValueError(f"naturaleza invalida: {normalized}")
        return normalized

    @field_validator("estado")
    @classmethod
    def validar_estado(cls, value: str | None) -> str | None:
        if value is None:
            return value
        normalized = value.strip().upper()
        if normalized not in ESTADOS_PLAN_CUENTA:
            raise ValueError(f"estado invalido: {normalized}")
        return normalized