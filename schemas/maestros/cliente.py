# schemas/maestros/cliente.py
# -*- coding: utf-8 -*-
from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, EmailStr, Field, field_validator

from core.validators import (
    formatear_rut,
    normalizar_telefono_chileno,
    normalizar_texto,
)


class ClienteBase(BaseModel):
    rut: str = Field(..., max_length=20)
    razon_social: str = Field(..., min_length=2, max_length=200)
    nombre_fantasia: str | None = Field(default=None, max_length=200)
    giro: str | None = Field(default=None, max_length=200)
    direccion: str | None = Field(default=None, max_length=250)
    comuna: str | None = Field(default=None, max_length=100)
    ciudad: str | None = Field(default=None, max_length=100)
    telefono: str | None = Field(default=None, max_length=50)
    email: EmailStr | None = None
    activo: bool = True

    @field_validator("rut")
    @classmethod
    def validar_rut(cls, v: str) -> str:
        return formatear_rut(v)

    @field_validator("razon_social")
    @classmethod
    def validar_razon_social(cls, v: str) -> str:
        s = normalizar_texto(v)
        if not s or len(s) < 2:
            raise ValueError("La razón social debe tener al menos 2 caracteres.")
        return s

    @field_validator(
        "nombre_fantasia",
        "giro",
        "direccion",
        "comuna",
        "ciudad",
        mode="before",
    )
    @classmethod
    def normalizar_campos_texto(cls, v: str | None) -> str | None:
        return normalizar_texto(v)

    @field_validator("telefono", mode="before")
    @classmethod
    def validar_telefono(cls, v: str | None) -> str | None:
        if v in (None, ""):
            return None
        return normalizar_telefono_chileno(str(v))

    @field_validator("email", mode="before")
    @classmethod
    def normalizar_email(cls, v: str | None) -> str | None:
        s = normalizar_texto(v)
        return s.lower() if s else None


class ClienteCreate(ClienteBase):
    pass


class ClienteUpdate(BaseModel):
    razon_social: str | None = Field(default=None, min_length=2, max_length=200)
    nombre_fantasia: str | None = Field(default=None, max_length=200)
    giro: str | None = Field(default=None, max_length=200)
    direccion: str | None = Field(default=None, max_length=250)
    comuna: str | None = Field(default=None, max_length=100)
    ciudad: str | None = Field(default=None, max_length=100)
    telefono: str | None = Field(default=None, max_length=50)
    email: EmailStr | None = None
    activo: bool | None = None

    @field_validator("razon_social")
    @classmethod
    def validar_razon_social(cls, v: str | None) -> str | None:
        if v is None:
            return None
        s = normalizar_texto(v)
        if not s or len(s) < 2:
            raise ValueError("La razón social debe tener al menos 2 caracteres.")
        return s

    @field_validator(
        "nombre_fantasia",
        "giro",
        "direccion",
        "comuna",
        "ciudad",
        mode="before",
    )
    @classmethod
    def normalizar_campos_texto(cls, v: str | None) -> str | None:
        return normalizar_texto(v)

    @field_validator("telefono", mode="before")
    @classmethod
    def validar_telefono(cls, v: str | None) -> str | None:
        if v in (None, ""):
            return None
        return normalizar_telefono_chileno(str(v))

    @field_validator("email", mode="before")
    @classmethod
    def normalizar_email(cls, v: str | None) -> str | None:
        s = normalizar_texto(v)
        return s.lower() if s else None


class ClienteOut(ClienteBase):
    id: int
    fecha_creacion: datetime
    fecha_actualizacion: datetime

    model_config = {
        "from_attributes": True,
    }
