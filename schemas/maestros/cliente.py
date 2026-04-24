# schemas/maestros/cliente.py
# -*- coding: utf-8 -*-
from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, EmailStr, Field


class ClienteBase(BaseModel):
    rut: str = Field(..., max_length=20)
    razon_social: str = Field(..., max_length=200)
    nombre_fantasia: str | None = Field(default=None, max_length=200)
    giro: str | None = Field(default=None, max_length=200)
    direccion: str | None = Field(default=None, max_length=250)
    comuna: str | None = Field(default=None, max_length=100)
    ciudad: str | None = Field(default=None, max_length=100)
    telefono: str | None = Field(default=None, max_length=50)
    email: EmailStr | None = None
    activo: bool = True


class ClienteCreate(ClienteBase):
    pass


class ClienteUpdate(BaseModel):
    razon_social: str | None = Field(default=None, max_length=200)
    nombre_fantasia: str | None = Field(default=None, max_length=200)
    giro: str | None = Field(default=None, max_length=200)
    direccion: str | None = Field(default=None, max_length=250)
    comuna: str | None = Field(default=None, max_length=100)
    ciudad: str | None = Field(default=None, max_length=100)
    telefono: str | None = Field(default=None, max_length=50)
    email: EmailStr | None = None
    activo: bool | None = None


class ClienteOut(ClienteBase):
    id: int
    fecha_creacion: datetime
    fecha_actualizacion: datetime

    model_config = {
        "from_attributes": True,
    }