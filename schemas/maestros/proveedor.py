# schemas/maestros/proveedor.py
# -*- coding: utf-8 -*-
from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


def _to_decimal(v) -> Decimal:
    if v in (None, "", "null"):
        return Decimal("0")
    return Decimal(str(v))


class ProveedorBancoBase(BaseModel):
    banco: str = Field(..., min_length=2, max_length=120)
    tipo_cuenta: str = Field(..., min_length=2, max_length=60)
    numero_cuenta: str = Field(..., min_length=1, max_length=60)
    titular: Optional[str] = Field(default=None, max_length=180)
    rut_titular: Optional[str] = Field(default=None, max_length=20)
    email_pago: Optional[str] = Field(default=None, max_length=180)
    es_principal: bool = False
    activo: bool = True


class ProveedorBancoCreate(ProveedorBancoBase):
    pass


class ProveedorBancoOut(ProveedorBancoBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    proveedor_id: int
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


class ProveedorContactoBase(BaseModel):
    nombre: str = Field(..., min_length=2, max_length=120)
    cargo: Optional[str] = Field(default=None, max_length=120)
    email: Optional[str] = Field(default=None, max_length=180)
    telefono: Optional[str] = Field(default=None, max_length=50)
    es_principal: bool = False
    activo: bool = True


class ProveedorContactoCreate(ProveedorContactoBase):
    pass


class ProveedorContactoOut(ProveedorContactoBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    proveedor_id: int
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


class ProveedorDireccionBase(BaseModel):
    linea1: str = Field(..., min_length=2, max_length=180)
    linea2: Optional[str] = Field(default=None, max_length=180)
    comuna: Optional[str] = Field(default=None, max_length=120)
    ciudad: Optional[str] = Field(default=None, max_length=120)
    region: Optional[str] = Field(default=None, max_length=120)
    pais: str = Field(default="Chile", max_length=120)
    codigo_postal: Optional[str] = Field(default=None, max_length=20)
    es_principal: bool = False
    activo: bool = True


class ProveedorDireccionCreate(ProveedorDireccionBase):
    pass


class ProveedorDireccionOut(ProveedorDireccionBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    proveedor_id: int
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


class ProveedorBase(BaseModel):
    rut: str = Field(..., min_length=3, max_length=20)
    razon_social: str = Field(..., min_length=2, max_length=180)
    nombre_fantasia: Optional[str] = Field(default=None, max_length=180)
    giro: Optional[str] = Field(default=None, max_length=180)
    email: Optional[str] = Field(default=None, max_length=180)
    telefono: Optional[str] = Field(default=None, max_length=50)
    sitio_web: Optional[str] = Field(default=None, max_length=180)
    condicion_pago_dias: int = Field(default=30, ge=0, le=365)
    limite_credito: Decimal = Field(default=Decimal("0"))
    activo: bool = True
    notas: Optional[str] = None

    bancos: list[ProveedorBancoCreate] = Field(default_factory=list)
    contactos: list[ProveedorContactoCreate] = Field(default_factory=list)
    direcciones: list[ProveedorDireccionCreate] = Field(default_factory=list)

    @field_validator("limite_credito", mode="before")
    @classmethod
    def _decimalizar(cls, v):
        return _to_decimal(v)

    @field_validator("rut")
    @classmethod
    def _normalizar_rut_usuario(cls, v: str) -> str:
        return v.strip().upper()

    @model_validator(mode="after")
    def validar_principales(self):
        if sum(1 for x in self.bancos if x.es_principal and x.activo) > 1:
            raise ValueError("Solo puede existir una cuenta bancaria principal activa.")
        if sum(1 for x in self.contactos if x.es_principal and x.activo) > 1:
            raise ValueError("Solo puede existir un contacto principal activo.")
        if sum(1 for x in self.direcciones if x.es_principal and x.activo) > 1:
            raise ValueError("Solo puede existir una dirección principal activa.")
        return self


class ProveedorCreate(ProveedorBase):
    pass


class ProveedorUpdate(ProveedorBase):
    pass


class ProveedorOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    rut: str
    rut_normalizado: Optional[str] = None
    razon_social: str
    nombre_fantasia: Optional[str] = None
    giro: Optional[str] = None
    email: Optional[str] = None
    telefono: Optional[str] = None
    sitio_web: Optional[str] = None
    condicion_pago_dias: int
    limite_credito: Decimal
    activo: bool
    notas: Optional[str] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    bancos: list[ProveedorBancoOut] = Field(default_factory=list)
    contactos: list[ProveedorContactoOut] = Field(default_factory=list)
    direcciones: list[ProveedorDireccionOut] = Field(default_factory=list)