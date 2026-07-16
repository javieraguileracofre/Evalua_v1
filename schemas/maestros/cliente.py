# schemas/maestros/cliente.py
# -*- coding: utf-8 -*-
from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, EmailStr, Field, field_validator, model_validator

from core.validators import (
    formatear_rut,
    normalizar_telefono_chileno,
    normalizar_texto,
)

TIPOS_PERSONA = Literal["NATURAL", "JURIDICA"]


class ClienteBase(BaseModel):
    rut: str = Field(..., max_length=20)
    tipo_persona: TIPOS_PERSONA = "JURIDICA"
    razon_social: str = Field(..., min_length=2, max_length=200)
    nombres: str | None = Field(default=None, max_length=120)
    apellido_paterno: str | None = Field(default=None, max_length=80)
    apellido_materno: str | None = Field(default=None, max_length=80)
    nombre_fantasia: str | None = Field(default=None, max_length=200)
    giro: str | None = Field(default=None, max_length=200)
    direccion: str | None = Field(default=None, max_length=250)
    comuna: str | None = Field(default=None, max_length=100)
    ciudad: str | None = Field(default=None, max_length=100)
    region: str | None = Field(default=None, max_length=100)
    representante_legal_nombre: str | None = Field(default=None, max_length=200)
    representante_legal_rut: str | None = Field(default=None, max_length=20)
    telefono: str | None = Field(default=None, max_length=50)
    email: EmailStr | None = None
    activo: bool = True

    @field_validator("rut")
    @classmethod
    def validar_rut(cls, v: str) -> str:
        return formatear_rut(v)

    @field_validator("representante_legal_rut", mode="before")
    @classmethod
    def validar_rut_rep(cls, v: str | None) -> str | None:
        if v in (None, ""):
            return None
        return formatear_rut(str(v))

    @field_validator("tipo_persona", mode="before")
    @classmethod
    def normalizar_tipo_persona(cls, v: str | None) -> str:
        t = str(v or "JURIDICA").strip().upper()
        return t if t in {"NATURAL", "JURIDICA"} else "JURIDICA"

    @field_validator("razon_social")
    @classmethod
    def validar_razon_social(cls, v: str) -> str:
        s = normalizar_texto(v)
        if not s or len(s) < 2:
            raise ValueError("La razón social debe tener al menos 2 caracteres.")
        return s

    @field_validator(
        "nombres",
        "apellido_paterno",
        "apellido_materno",
        "nombre_fantasia",
        "giro",
        "direccion",
        "comuna",
        "ciudad",
        "region",
        "representante_legal_nombre",
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

    @model_validator(mode="after")
    def validar_por_tipo_persona(self) -> ClienteBase:
        if self.tipo_persona == "NATURAL":
            if not self.nombres or not self.apellido_paterno:
                raise ValueError("Persona natural requiere nombres y apellido paterno.")
            if not self.razon_social or self.razon_social == "Pendiente":
                self.razon_social = " ".join(
                    x for x in [self.nombres, self.apellido_paterno, self.apellido_materno] if x
                ).strip()
        if self.tipo_persona == "JURIDICA":
            if not self.giro:
                raise ValueError("Persona jurídica requiere giro comercial.")
        if not self.direccion or not self.comuna:
            raise ValueError("Dirección y comuna son obligatorias.")
        return self


class ClienteCreate(ClienteBase):
    pass


class ClienteUpdate(BaseModel):
    tipo_persona: TIPOS_PERSONA | None = None
    razon_social: str | None = Field(default=None, min_length=2, max_length=200)
    nombres: str | None = Field(default=None, max_length=120)
    apellido_paterno: str | None = Field(default=None, max_length=80)
    apellido_materno: str | None = Field(default=None, max_length=80)
    nombre_fantasia: str | None = Field(default=None, max_length=200)
    giro: str | None = Field(default=None, max_length=200)
    direccion: str | None = Field(default=None, max_length=250)
    comuna: str | None = Field(default=None, max_length=100)
    ciudad: str | None = Field(default=None, max_length=100)
    region: str | None = Field(default=None, max_length=100)
    representante_legal_nombre: str | None = Field(default=None, max_length=200)
    representante_legal_rut: str | None = Field(default=None, max_length=20)
    telefono: str | None = Field(default=None, max_length=50)
    email: EmailStr | None = None
    activo: bool | None = None

    @field_validator("representante_legal_rut", mode="before")
    @classmethod
    def validar_rut_rep(cls, v: str | None) -> str | None:
        if v in (None, ""):
            return None
        return formatear_rut(str(v))

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
        "nombres",
        "apellido_paterno",
        "apellido_materno",
        "nombre_fantasia",
        "giro",
        "direccion",
        "comuna",
        "ciudad",
        "region",
        "representante_legal_nombre",
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
