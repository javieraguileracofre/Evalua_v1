# schemas/finanzas/cuentas_por_pagar.py
# -*- coding: utf-8 -*-
from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import List, Literal, Optional

from pydantic import BaseModel, Field, field_validator, model_validator


DocumentoTipo = Literal["FACTURA", "BOLETA", "NC", "ND", "OTRO"]
DocumentoEstado = Literal["BORRADOR", "INGRESADO", "PAGADO", "ANULADO", "VENCIDO"]
TipoCompraContable = Literal["INVENTARIO", "GASTO"]
PagoEstado = Literal["BORRADOR", "APLICADO", "CONFIRMADO", "ANULADO"]
MedioPago = Literal["TRANSFERENCIA", "EFECTIVO", "CHEQUE", "TARJETA", "DEPOSITO", "OTRO"]
SiNo = Literal["SI", "NO"]


def _to_decimal(v) -> Decimal:
    if v in (None, "", "null", "None"):
        return Decimal("0")
    return Decimal(str(v))


class DocumentoDetalleBase(BaseModel):
    descripcion: str = Field(..., min_length=1, max_length=260)
    cantidad: Decimal = Field(default=Decimal("1"))
    precio_unitario: Decimal = Field(default=Decimal("0"))
    descuento: Decimal = Field(default=Decimal("0"))
    categoria_gasto_id: Optional[int] = None
    centro_costo_id: Optional[int] = None

    @field_validator("cantidad", "precio_unitario", "descuento", mode="before")
    @classmethod
    def _decimalizar(cls, v):
        return _to_decimal(v)

    @model_validator(mode="after")
    def validar(self):
        if self.cantidad <= 0:
            raise ValueError("La cantidad debe ser mayor a 0.")
        if self.precio_unitario < 0:
            raise ValueError("El precio unitario no puede ser negativo.")
        if self.descuento < 0:
            raise ValueError("El descuento no puede ser negativo.")
        return self


class DocumentoDetalleCreate(DocumentoDetalleBase):
    pass


class DocumentoImpuestoCreate(BaseModel):
    tipo: str = "OTRO"
    codigo: Optional[str] = None
    nombre: Optional[str] = None
    monto: Decimal = Decimal("0")

    @field_validator("monto", mode="before")
    @classmethod
    def _decimalizar(cls, v):
        return _to_decimal(v)

    @model_validator(mode="after")
    def validar(self):
        if self.monto < 0:
            raise ValueError("El monto del impuesto no puede ser negativo.")
        return self


class DocumentoCreate(BaseModel):
    proveedor_id: int
    tipo: DocumentoTipo
    folio: str = Field(..., min_length=1, max_length=40)
    fecha_emision: date
    fecha_recepcion: Optional[date] = None
    fecha_vencimiento: date
    moneda: str = "CLP"
    tipo_cambio: Decimal = Decimal("1")
    es_exento: SiNo = "NO"

    @field_validator("es_exento", mode="before")
    @classmethod
    def _normalizar_es_exento(cls, v) -> str:
        s = str(v or "NO").strip().upper()
        if s in ("SI", "SÍ", "TRUE", "1", "YES", "ON"):
            return "SI"
        return "NO"
    referencia: Optional[str] = Field(default=None, max_length=180)
    observaciones: Optional[str] = None
    detalles: List[DocumentoDetalleCreate] = Field(default_factory=list)
    impuestos: List[DocumentoImpuestoCreate] = Field(default_factory=list)
    tipo_compra_contable: TipoCompraContable = "GASTO"
    cuenta_gasto_codigo: Optional[str] = Field(default=None, max_length=30)
    cuenta_proveedores_codigo: Optional[str] = Field(default=None, max_length=30)
    generar_asiento_contable: bool = True

    @field_validator("tipo_cambio", mode="before")
    @classmethod
    def _decimalizar(cls, v):
        return _to_decimal(v)

    @field_validator("moneda")
    @classmethod
    def _normalizar_moneda(cls, v: str) -> str:
        return str(v).strip().upper()

    @field_validator("cuenta_gasto_codigo", "cuenta_proveedores_codigo", mode="before")
    @classmethod
    def _strip_codigo_cuenta(cls, v):
        if v in (None, "", "null", "None"):
            return None
        s = str(v).strip()
        return s or None

    @model_validator(mode="after")
    def validar(self):
        if self.fecha_vencimiento < self.fecha_emision:
            raise ValueError("La fecha de vencimiento no puede ser menor a la fecha de emisión.")
        if self.fecha_recepcion and self.fecha_recepcion < self.fecha_emision:
            raise ValueError("La fecha de recepción no puede ser menor a la fecha de emisión.")
        if self.tipo_cambio <= 0:
            raise ValueError("El tipo de cambio debe ser mayor a 0.")
        if not self.detalles:
            raise ValueError("Debes ingresar al menos una línea de detalle.")
        return self


class DocumentoUpdate(DocumentoCreate):
    estado: Optional[DocumentoEstado] = None


class PagoAplicacionCreate(BaseModel):
    documento_id: int
    monto_aplicado: Decimal

    @field_validator("monto_aplicado", mode="before")
    @classmethod
    def _decimalizar(cls, v):
        return _to_decimal(v)

    @model_validator(mode="after")
    def validar(self):
        if self.monto_aplicado <= 0:
            raise ValueError("El monto aplicado debe ser mayor a 0.")
        return self


class PagoCreate(BaseModel):
    proveedor_id: int
    fecha_pago: date
    medio_pago: MedioPago = "TRANSFERENCIA"
    referencia: Optional[str] = Field(default=None, max_length=180)
    banco_proveedor_id: Optional[int] = None
    moneda: str = "CLP"
    tipo_cambio: Decimal = Decimal("1")
    observaciones: Optional[str] = None
    aplicaciones: List[PagoAplicacionCreate] = Field(default_factory=list)

    @field_validator("tipo_cambio", mode="before")
    @classmethod
    def _decimalizar(cls, v):
        return _to_decimal(v)

    @field_validator("moneda")
    @classmethod
    def _normalizar_moneda(cls, v: str) -> str:
        return str(v).strip().upper()

    @model_validator(mode="after")
    def validar(self):
        if self.tipo_cambio <= 0:
            raise ValueError("El tipo de cambio debe ser mayor a 0.")
        if not self.aplicaciones:
            raise ValueError("Debes ingresar al menos una aplicación de pago.")
        total = sum((a.monto_aplicado for a in self.aplicaciones), Decimal("0"))
        if total <= 0:
            raise ValueError("El monto total del pago debe ser mayor a 0.")
        return self