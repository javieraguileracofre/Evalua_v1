# models/finanzas/compras_finanzas.py
# -*- coding: utf-8 -*-
from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
import uuid
from typing import TYPE_CHECKING

from sqlalchemy import (
    BigInteger,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.schema import Computed
from sqlalchemy.dialects.postgresql import UUID, ENUM as PGEnum
from sqlalchemy.orm import Mapped, mapped_column, relationship

from db.base_class import Base

if TYPE_CHECKING:
    from models.maestros.proveedor import Proveedor, ProveedorBanco


FIN_SCHEMA = "fin"

PROVEEDOR_ESTADO_ENUM = PGEnum(
    "ACTIVO",
    "INACTIVO",
    "BLOQUEADO",
    name="estado_simple",
    schema=FIN_SCHEMA,
    create_type=False,
)

CATEGORIA_TIPO_ENUM = PGEnum(
    "OPERACIONAL",
    "ADMINISTRATIVO",
    "VENTA",
    "FINANCIERO",
    "TRIBUTARIO",
    "OTRO",
    name="categoria_gasto_tipo",
    schema=FIN_SCHEMA,
    create_type=False,
)

PERIODO_ESTADO_ENUM = PGEnum(
    "ABIERTO",
    "CERRADO",
    name="periodo_estado",
    schema=FIN_SCHEMA,
    create_type=False,
)

AP_DOC_TIPO_ENUM = PGEnum(
    "FACTURA",
    "BOLETA",
    "NC",
    "ND",
    "OTRO",
    name="ap_doc_tipo",
    schema=FIN_SCHEMA,
    create_type=False,
)

AP_DOC_ESTADO_ENUM = PGEnum(
    "BORRADOR",
    "INGRESADO",
    "PAGADO",
    "ANULADO",
    "VENCIDO",
    name="ap_doc_estado",
    schema=FIN_SCHEMA,
    create_type=False,
)

MONEDA_ISO_ENUM = PGEnum(
    "CLP",
    "USD",
    "EUR",
    "UF",
    name="moneda_iso",
    schema=FIN_SCHEMA,
    create_type=False,
)

IMPUESTO_TIPO_ENUM = PGEnum(
    "IVA",
    "RETENCION",
    "PERCEPCION",
    "OTRO",
    name="impuesto_tipo",
    schema=FIN_SCHEMA,
    create_type=False,
)

AP_PAGO_ESTADO_ENUM = PGEnum(
    "BORRADOR",
    "APLICADO",
    "CONFIRMADO",
    "ANULADO",
    name="ap_pago_estado",
    schema=FIN_SCHEMA,
    create_type=False,
)

MEDIO_PAGO_ENUM = PGEnum(
    "TRANSFERENCIA",
    "EFECTIVO",
    "CHEQUE",
    "TARJETA",
    "DEPOSITO",
    "OTRO",
    name="medio_pago",
    schema=FIN_SCHEMA,
    create_type=False,
)


class ProveedorFin(Base):
    __tablename__ = "proveedor_fin"
    __table_args__ = (
        Index("ix_proveedor_fin_proveedor", "proveedor_id"),
        UniqueConstraint("proveedor_id", name="ux_proveedor_fin_proveedor"),
        {"schema": FIN_SCHEMA},
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    proveedor_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("proveedor.id", ondelete="CASCADE"),
        nullable=False,
    )
    condicion_pago_dias: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=30,
        server_default=text("30"),
    )
    limite_credito: Mapped[Decimal] = mapped_column(
        Numeric(18, 2),
        nullable=False,
        default=Decimal("0.00"),
        server_default=text("0"),
    )
    estado: Mapped[str] = mapped_column(
        PROVEEDOR_ESTADO_ENUM,
        nullable=False,
        default="ACTIVO",
        server_default=text("'ACTIVO'::fin.estado_simple"),
    )
    notas: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    proveedor: Mapped["Proveedor"] = relationship(
        "Proveedor",
        back_populates="finanzas",
    )


class CategoriaGasto(Base):
    __tablename__ = "categoria_gasto"
    __table_args__ = (
        UniqueConstraint("codigo", name="ux_cat_gasto_codigo"),
        {"schema": FIN_SCHEMA},
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    codigo: Mapped[str] = mapped_column(String(30), nullable=False)
    nombre: Mapped[str] = mapped_column(String(160), nullable=False)
    tipo: Mapped[str] = mapped_column(
        CATEGORIA_TIPO_ENUM,
        nullable=False,
        default="OPERACIONAL",
        server_default=text("'OPERACIONAL'::fin.categoria_gasto_tipo"),
    )
    estado: Mapped[str] = mapped_column(
        PROVEEDOR_ESTADO_ENUM,
        nullable=False,
        default="ACTIVO",
        server_default=text("'ACTIVO'::fin.estado_simple"),
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    detalles_documento: Mapped[list["APDocumentoDetalle"]] = relationship(
        "APDocumentoDetalle",
        back_populates="categoria_gasto",
    )


class CentroCosto(Base):
    __tablename__ = "centro_costo"
    __table_args__ = (
        UniqueConstraint("codigo", name="ux_centro_costo_codigo"),
        {"schema": FIN_SCHEMA},
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    codigo: Mapped[str] = mapped_column(String(30), nullable=False)
    nombre: Mapped[str] = mapped_column(String(120), nullable=False)
    estado: Mapped[str] = mapped_column(
        PROVEEDOR_ESTADO_ENUM,
        nullable=False,
        default="ACTIVO",
        server_default=text("'ACTIVO'::fin.estado_simple"),
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    detalles_documento: Mapped[list["APDocumentoDetalle"]] = relationship(
        "APDocumentoDetalle",
        back_populates="centro_costo",
    )


class Periodo(Base):
    __tablename__ = "periodo"
    __table_args__ = (
        UniqueConstraint("anio", "mes", name="ux_periodo"),
        {"schema": FIN_SCHEMA},
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    anio: Mapped[int] = mapped_column(Integer, nullable=False)
    mes: Mapped[int] = mapped_column(Integer, nullable=False)
    estado: Mapped[str] = mapped_column(
        PERIODO_ESTADO_ENUM,
        nullable=False,
        default="ABIERTO",
        server_default=text("'ABIERTO'::fin.periodo_estado"),
    )
    cerrado_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    cerrado_por: Mapped[str | None] = mapped_column(String(180), nullable=True)
    notas: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )


class APDocumento(Base):
    __tablename__ = "ap_documento"
    __table_args__ = (
        Index("ix_ap_doc_estado", "estado"),
        Index("ix_ap_doc_fechas", "fecha_emision", "fecha_vencimiento"),
        Index("ix_ap_doc_proveedor", "proveedor_id"),
        UniqueConstraint("proveedor_id", "tipo", "folio", name="ux_ap_doc_unique"),
        UniqueConstraint("uuid", name="ux_ap_documento_uuid"),
        {"schema": FIN_SCHEMA},
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    uuid: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        nullable=False,
        default=uuid.uuid4,
        server_default=text("gen_random_uuid()"),
    )
    proveedor_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("proveedor.id", ondelete="RESTRICT"),
        nullable=False,
    )
    tipo: Mapped[str] = mapped_column(AP_DOC_TIPO_ENUM, nullable=False)
    estado: Mapped[str] = mapped_column(
        AP_DOC_ESTADO_ENUM,
        nullable=False,
        default="BORRADOR",
        server_default=text("'BORRADOR'::fin.ap_doc_estado"),
    )
    folio: Mapped[str] = mapped_column(String(40), nullable=False)
    fecha_emision: Mapped[date] = mapped_column(Date, nullable=False)
    fecha_recepcion: Mapped[date | None] = mapped_column(Date, nullable=True)
    fecha_vencimiento: Mapped[date] = mapped_column(Date, nullable=False)
    moneda: Mapped[str] = mapped_column(
        MONEDA_ISO_ENUM,
        nullable=False,
        default="CLP",
        server_default=text("'CLP'::fin.moneda_iso"),
    )
    tipo_cambio: Mapped[Decimal] = mapped_column(
        Numeric(18, 6),
        nullable=False,
        default=Decimal("1.000000"),
        server_default=text("1"),
    )
    neto: Mapped[Decimal] = mapped_column(
        Numeric(18, 2),
        nullable=False,
        default=Decimal("0.00"),
        server_default=text("0"),
    )
    exento: Mapped[Decimal] = mapped_column(
        Numeric(18, 2),
        nullable=False,
        default=Decimal("0.00"),
        server_default=text("0"),
    )
    iva: Mapped[Decimal] = mapped_column(
        Numeric(18, 2),
        nullable=False,
        default=Decimal("0.00"),
        server_default=text("0"),
    )
    otros_impuestos: Mapped[Decimal] = mapped_column(
        Numeric(18, 2),
        nullable=False,
        default=Decimal("0.00"),
        server_default=text("0"),
    )
    total: Mapped[Decimal] = mapped_column(
        Numeric(18, 2),
        nullable=False,
        default=Decimal("0.00"),
        server_default=text("0"),
    )
    saldo_pendiente: Mapped[Decimal] = mapped_column(
        Numeric(18, 2),
        nullable=False,
        default=Decimal("0.00"),
        server_default=text("0"),
    )
    referencia: Mapped[str | None] = mapped_column(String(180), nullable=True)
    observaciones: Mapped[str | None] = mapped_column(Text, nullable=True)

    tipo_compra_contable: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="GASTO",
        server_default=text("'GASTO'"),
    )
    cuenta_gasto_codigo: Mapped[str | None] = mapped_column(String(30), nullable=True)
    cuenta_proveedores_codigo: Mapped[str | None] = mapped_column(String(30), nullable=True)
    asiento_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    proveedor: Mapped["Proveedor"] = relationship(
        "Proveedor",
        back_populates="documentos_ap",
    )

    detalles: Mapped[list["APDocumentoDetalle"]] = relationship(
        "APDocumentoDetalle",
        back_populates="documento",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="APDocumentoDetalle.linea",
    )

    impuestos: Mapped[list["APDocumentoImpuesto"]] = relationship(
        "APDocumentoImpuesto",
        back_populates="documento",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )

    aplicaciones_pago: Mapped[list["APPagoAplicacion"]] = relationship(
        "APPagoAplicacion",
        back_populates="documento",
    )


class APDocumentoDetalle(Base):
    __tablename__ = "ap_documento_detalle"
    __table_args__ = (
        Index("ix_ap_doc_det_categoria", "categoria_gasto_id"),
        Index("ix_ap_doc_det_centro", "centro_costo_id"),
        Index("ix_ap_doc_det_documento", "documento_id"),
        UniqueConstraint("documento_id", "linea", name="ux_ap_doc_det_linea"),
        {"schema": FIN_SCHEMA},
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    documento_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey(f"{FIN_SCHEMA}.ap_documento.id", ondelete="CASCADE"),
        nullable=False,
    )
    linea: Mapped[int] = mapped_column(Integer, nullable=False)
    descripcion: Mapped[str] = mapped_column(String(260), nullable=False)
    cantidad: Mapped[Decimal] = mapped_column(
        Numeric(18, 6),
        nullable=False,
        default=Decimal("1.000000"),
        server_default=text("1"),
    )
    precio_unitario: Mapped[Decimal] = mapped_column(
        Numeric(18, 6),
        nullable=False,
        default=Decimal("0.000000"),
        server_default=text("0"),
    )
    descuento: Mapped[Decimal] = mapped_column(
        Numeric(18, 2),
        nullable=False,
        default=Decimal("0.00"),
        server_default=text("0"),
    )
    neto_linea: Mapped[Decimal] = mapped_column(
        Numeric(18, 2),
        nullable=False,
        default=Decimal("0.00"),
        server_default=text("0"),
    )
    iva_linea: Mapped[Decimal] = mapped_column(
        Numeric(18, 2),
        nullable=False,
        default=Decimal("0.00"),
        server_default=text("0"),
    )
    otros_impuestos: Mapped[Decimal] = mapped_column(
        Numeric(18, 2),
        nullable=False,
        default=Decimal("0.00"),
        server_default=text("0"),
    )
    total_linea: Mapped[Decimal] = mapped_column(
        Numeric(18, 2),
        Computed("(neto_linea + iva_linea)", persisted=True),
        nullable=False,
    )
    categoria_gasto_id: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey(f"{FIN_SCHEMA}.categoria_gasto.id", ondelete="SET NULL"),
        nullable=True,
    )
    centro_costo_id: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey(f"{FIN_SCHEMA}.centro_costo.id", ondelete="SET NULL"),
        nullable=True,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    documento: Mapped["APDocumento"] = relationship(
        "APDocumento",
        back_populates="detalles",
    )

    categoria_gasto: Mapped["CategoriaGasto | None"] = relationship(
        "CategoriaGasto",
        back_populates="detalles_documento",
    )

    centro_costo: Mapped["CentroCosto | None"] = relationship(
        "CentroCosto",
        back_populates="detalles_documento",
    )


class APDocumentoImpuesto(Base):
    __tablename__ = "ap_documento_impuesto"
    __table_args__ = (
        Index("ix_ap_doc_imp_documento", "documento_id"),
        UniqueConstraint("documento_id", "tipo", "codigo", name="ux_ap_doc_imp_unique"),
        {"schema": FIN_SCHEMA},
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    documento_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey(f"{FIN_SCHEMA}.ap_documento.id", ondelete="CASCADE"),
        nullable=False,
    )
    tipo: Mapped[str] = mapped_column(
        IMPUESTO_TIPO_ENUM,
        nullable=False,
        default="OTRO",
        server_default=text("'OTRO'::fin.impuesto_tipo"),
    )
    codigo: Mapped[str | None] = mapped_column(String(40), nullable=True)
    nombre: Mapped[str | None] = mapped_column(String(120), nullable=True)
    monto: Mapped[Decimal] = mapped_column(
        Numeric(18, 2),
        nullable=False,
        default=Decimal("0.00"),
        server_default=text("0"),
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    documento: Mapped["APDocumento"] = relationship(
        "APDocumento",
        back_populates="impuestos",
    )


class APPago(Base):
    __tablename__ = "ap_pago"
    __table_args__ = (
        Index("ix_ap_pago_proveedor_fecha", "proveedor_id", "fecha_pago"),
        {"schema": FIN_SCHEMA},
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    uuid: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        nullable=False,
        default=uuid.uuid4,
        server_default=text("gen_random_uuid()"),
    )
    proveedor_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("proveedor.id", ondelete="RESTRICT"),
        nullable=False,
    )
    estado: Mapped[str] = mapped_column(
        AP_PAGO_ESTADO_ENUM,
        nullable=False,
        default="BORRADOR",
        server_default=text("'BORRADOR'::fin.ap_pago_estado"),
    )
    fecha_pago: Mapped[date] = mapped_column(Date, nullable=False)
    medio_pago: Mapped[str] = mapped_column(
        MEDIO_PAGO_ENUM,
        nullable=False,
        default="TRANSFERENCIA",
        server_default=text("'TRANSFERENCIA'::fin.medio_pago"),
    )
    referencia: Mapped[str | None] = mapped_column(String(180), nullable=True)
    banco_proveedor_id: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey("proveedor_banco.id", ondelete="SET NULL"),
        nullable=True,
    )
    moneda: Mapped[str] = mapped_column(
        MONEDA_ISO_ENUM,
        nullable=False,
        default="CLP",
        server_default=text("'CLP'::fin.moneda_iso"),
    )
    tipo_cambio: Mapped[Decimal] = mapped_column(
        Numeric(18, 6),
        nullable=False,
        default=Decimal("1.000000"),
        server_default=text("1"),
    )
    monto_total: Mapped[Decimal] = mapped_column(
        Numeric(18, 2),
        nullable=False,
        default=Decimal("0.00"),
        server_default=text("0"),
    )
    observaciones: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    proveedor: Mapped["Proveedor"] = relationship(
        "Proveedor",
        back_populates="pagos_ap",
    )

    banco_proveedor: Mapped["ProveedorBanco | None"] = relationship(
        "ProveedorBanco",
        back_populates="pagos_ap",
    )

    aplicaciones: Mapped[list["APPagoAplicacion"]] = relationship(
        "APPagoAplicacion",
        back_populates="pago",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )


class APPagoAplicacion(Base):
    __tablename__ = "ap_pago_aplicacion"
    __table_args__ = (
        UniqueConstraint("pago_id", "documento_id", name="ux_pago_doc"),
        Index("ix_ap_pago_aplicacion_documento", "documento_id"),
        {"schema": FIN_SCHEMA},
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    pago_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey(f"{FIN_SCHEMA}.ap_pago.id", ondelete="CASCADE"),
        nullable=False,
    )
    documento_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey(f"{FIN_SCHEMA}.ap_documento.id", ondelete="RESTRICT"),
        nullable=False,
    )
    monto_aplicado: Mapped[Decimal] = mapped_column(
        Numeric(18, 2),
        nullable=False,
        default=Decimal("0.00"),
        server_default=text("0"),
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    pago: Mapped["APPago"] = relationship(
        "APPago",
        back_populates="aplicaciones",
    )

    documento: Mapped["APDocumento"] = relationship(
        "APDocumento",
        back_populates="aplicaciones_pago",
    )