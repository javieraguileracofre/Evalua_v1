# schemas/inventario/inventario.py
# -*- coding: utf-8 -*-
from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class CategoriaProductoBase(BaseModel):
    nombre: str = Field(..., max_length=150)
    descripcion: str | None = None
    activo: bool = True


class CategoriaProductoCreate(CategoriaProductoBase):
    pass


class CategoriaProductoOut(CategoriaProductoBase):
    id: int
    fecha_creacion: datetime

    model_config = {
        "from_attributes": True,
    }


class UnidadMedidaBase(BaseModel):
    codigo: str = Field(..., max_length=20)
    nombre: str = Field(..., max_length=100)
    simbolo: str | None = Field(default=None, max_length=20)
    activo: bool = True


class UnidadMedidaCreate(UnidadMedidaBase):
    pass


class UnidadMedidaOut(UnidadMedidaBase):
    id: int
    fecha_creacion: datetime

    model_config = {
        "from_attributes": True,
    }


class ProductoBase(BaseModel):
    codigo: str | None = Field(default=None, max_length=50)
    codigo_barra: str | None = Field(default=None, max_length=80)
    nombre: str = Field(..., max_length=200)
    descripcion: str | None = None
    categoria_id: int | None = None
    unidad_medida_id: int | None = None
    precio_compra: float = 0
    precio_venta: float = 0
    stock_minimo: float = 0
    stock_actual: float = 0
    controla_stock: bool = True
    permite_venta_fraccionada: bool = False
    es_servicio: bool = False
    activo: bool = True


class ProductoCreate(ProductoBase):
    pass


class ProductoUpdate(BaseModel):
    nombre: str | None = Field(default=None, max_length=200)
    descripcion: str | None = None
    categoria_id: int | None = None
    unidad_medida_id: int | None = None
    codigo_barra: str | None = Field(default=None, max_length=80)
    precio_compra: float | None = None
    precio_venta: float | None = None
    stock_minimo: float | None = None
    controla_stock: bool | None = None
    permite_venta_fraccionada: bool | None = None
    es_servicio: bool | None = None
    activo: bool | None = None


class ProductoOut(ProductoBase):
    id: int
    fecha_creacion: datetime
    fecha_actualizacion: datetime

    model_config = {
        "from_attributes": True,
    }


class InventarioAjusteCreate(BaseModel):
    producto_id: int
    tipo_ajuste: str = Field(..., max_length=20)
    cantidad: float = Field(..., gt=0)
    costo_unitario: float = 0
    observacion: str | None = None


class InventarioIngresoStockCreate(BaseModel):
    producto_id: int
    cantidad: float = Field(..., gt=0)
    costo_unitario: float = Field(default=0, ge=0)
    observacion: str | None = None