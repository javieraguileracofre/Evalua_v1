# models/comercial/leasing_financiero_operacion.py
# -*- coding: utf-8 -*-
from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import (
    BigInteger,
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from db.base_class import Base

if TYPE_CHECKING:
    from models.comercial.leasing_financiero_cotizacion import LeasingFinancieroCotizacion
    from models.maestros.proveedor import Proveedor


class LeasingFinancieroActivo(Base):
    __tablename__ = "comercial_lf_activo"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    cotizacion_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("comercial_lf_cotizaciones.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
    )
    proveedor_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("proveedor.id", ondelete="SET NULL"))
    categoria: Mapped[str | None] = mapped_column(String(80))
    marca: Mapped[str | None] = mapped_column(String(120))
    modelo: Mapped[str | None] = mapped_column(String(120))
    descripcion: Mapped[str] = mapped_column(String(500), nullable=False, default="", server_default="")
    numero_serie: Mapped[str | None] = mapped_column(String(120))
    numero_chasis: Mapped[str | None] = mapped_column(String(120))
    valor_neto: Mapped[Decimal | None] = mapped_column(Numeric(18, 2))
    iva_monto: Mapped[Decimal | None] = mapped_column(Numeric(18, 2))
    valor_total: Mapped[Decimal | None] = mapped_column(Numeric(18, 2))
    estado: Mapped[str] = mapped_column(String(40), nullable=False, default="COTIZADO", server_default="COTIZADO")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=datetime.utcnow, server_default=text("CURRENT_TIMESTAMP")
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
        server_default=text("CURRENT_TIMESTAMP"),
    )

    cotizacion: Mapped["LeasingFinancieroCotizacion"] = relationship(
        "LeasingFinancieroCotizacion", back_populates="activo", lazy="selectin"
    )
    proveedor: Mapped["Proveedor | None"] = relationship("Proveedor", lazy="selectin")


class LeasingFinancieroAmortizacionLinea(Base):
    __tablename__ = "comercial_lf_amortizacion_linea"
    __table_args__ = (UniqueConstraint("cotizacion_id", "version_n", "numero_cuota", name="uq_lf_amort_cot_ver_cuota"),)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    cotizacion_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("comercial_lf_cotizaciones.id", ondelete="CASCADE"), nullable=False, index=True
    )
    version_n: Mapped[int] = mapped_column(Integer, nullable=False, default=1, server_default="1")
    numero_cuota: Mapped[int] = mapped_column(Integer, nullable=False)
    fecha_cuota: Mapped[date | None] = mapped_column(Date)
    saldo_inicial: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False, default=Decimal("0"))
    cuota: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False, default=Decimal("0"))
    interes: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False, default=Decimal("0"))
    amortizacion: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False, default=Decimal("0"))
    saldo_final: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False, default=Decimal("0"))
    iva_cuota: Mapped[Decimal | None] = mapped_column(Numeric(18, 2))
    otros_cargos: Mapped[Decimal | None] = mapped_column(Numeric(18, 2))
    es_gracia: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default=text("false"))
    es_opcion_compra: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default=text("false"))
    es_oficial: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default=text("false"))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=datetime.utcnow, server_default=text("CURRENT_TIMESTAMP")
    )

    cotizacion: Mapped["LeasingFinancieroCotizacion"] = relationship(
        "LeasingFinancieroCotizacion", back_populates="amortizacion_lineas", lazy="selectin"
    )


class LeasingFinancieroOrdenCompra(Base):
    __tablename__ = "comercial_lf_orden_compra"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    cotizacion_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("comercial_lf_cotizaciones.id", ondelete="CASCADE"), nullable=False, index=True
    )
    proveedor_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("proveedor.id"), nullable=False)
    numero: Mapped[str] = mapped_column(String(50), nullable=False)
    fecha_emision: Mapped[date] = mapped_column(Date, nullable=False)
    fecha_entrega_estimada: Mapped[date | None] = mapped_column(Date)
    neto: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    iva: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False, default=Decimal("0"))
    total: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    moneda: Mapped[str] = mapped_column(String(10), nullable=False, default="CLP", server_default="CLP")
    condiciones: Mapped[str | None] = mapped_column(Text)
    estado: Mapped[str] = mapped_column(String(30), nullable=False, default="BORRADOR", server_default="BORRADOR")
    usuario: Mapped[str] = mapped_column(String(200), nullable=False, default="sistema", server_default="sistema")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=datetime.utcnow, server_default=text("CURRENT_TIMESTAMP")
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
        server_default=text("CURRENT_TIMESTAMP"),
    )

    cotizacion: Mapped["LeasingFinancieroCotizacion"] = relationship(
        "LeasingFinancieroCotizacion", back_populates="ordenes_compra", lazy="selectin"
    )
    proveedor: Mapped["Proveedor"] = relationship("Proveedor", lazy="selectin")
    facturas: Mapped[list["LeasingFinancieroFacturaCompra"]] = relationship(
        "LeasingFinancieroFacturaCompra", back_populates="orden_compra", lazy="selectin"
    )


class LeasingFinancieroFacturaCompra(Base):
    __tablename__ = "comercial_lf_factura_compra"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    cotizacion_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("comercial_lf_cotizaciones.id", ondelete="CASCADE"), nullable=False, index=True
    )
    orden_compra_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("comercial_lf_orden_compra.id", ondelete="SET NULL")
    )
    proveedor_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("proveedor.id"), nullable=False)
    folio: Mapped[str] = mapped_column(String(50), nullable=False)
    fecha_factura: Mapped[date] = mapped_column(Date, nullable=False)
    neto: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    iva: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False, default=Decimal("0"))
    total: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    diferencia_cotizacion: Mapped[Decimal | None] = mapped_column(Numeric(18, 2))
    diferencia_oc: Mapped[Decimal | None] = mapped_column(Numeric(18, 2))
    ap_documento_id: Mapped[int | None] = mapped_column(BigInteger)
    estado: Mapped[str] = mapped_column(String(30), nullable=False, default="REGISTRADA", server_default="REGISTRADA")
    usuario: Mapped[str] = mapped_column(String(200), nullable=False, default="sistema", server_default="sistema")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=datetime.utcnow, server_default=text("CURRENT_TIMESTAMP")
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
        server_default=text("CURRENT_TIMESTAMP"),
    )

    cotizacion: Mapped["LeasingFinancieroCotizacion"] = relationship(
        "LeasingFinancieroCotizacion", back_populates="facturas_compra", lazy="selectin"
    )
    orden_compra: Mapped["LeasingFinancieroOrdenCompra | None"] = relationship(
        "LeasingFinancieroOrdenCompra", back_populates="facturas", lazy="selectin"
    )
    proveedor: Mapped["Proveedor"] = relationship("Proveedor", lazy="selectin")
    solicitudes_pago: Mapped[list["LeasingFinancieroSolicitudPago"]] = relationship(
        "LeasingFinancieroSolicitudPago", back_populates="factura_compra", lazy="selectin"
    )


class LeasingFinancieroSolicitudPago(Base):
    __tablename__ = "comercial_lf_solicitud_pago"
    __table_args__ = (UniqueConstraint("idempotency_key", name="uq_lf_solicitud_pago_idem"),)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    cotizacion_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("comercial_lf_cotizaciones.id", ondelete="CASCADE"), nullable=False, index=True
    )
    factura_compra_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("comercial_lf_factura_compra.id", ondelete="CASCADE"), nullable=False
    )
    proveedor_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("proveedor.id"), nullable=False)
    monto: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    moneda: Mapped[str] = mapped_column(String(10), nullable=False, default="CLP", server_default="CLP")
    estado: Mapped[str] = mapped_column(String(30), nullable=False, default="BORRADOR", server_default="BORRADOR")
    idempotency_key: Mapped[str] = mapped_column(String(80), nullable=False)
    aprobado_por: Mapped[str | None] = mapped_column(String(200))
    fecha_aprobacion: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    ap_pago_id: Mapped[int | None] = mapped_column(BigInteger)
    usuario: Mapped[str] = mapped_column(String(200), nullable=False, default="sistema", server_default="sistema")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=datetime.utcnow, server_default=text("CURRENT_TIMESTAMP")
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
        server_default=text("CURRENT_TIMESTAMP"),
    )

    cotizacion: Mapped["LeasingFinancieroCotizacion"] = relationship(
        "LeasingFinancieroCotizacion", back_populates="solicitudes_pago", lazy="selectin"
    )
    factura_compra: Mapped["LeasingFinancieroFacturaCompra"] = relationship(
        "LeasingFinancieroFacturaCompra", back_populates="solicitudes_pago", lazy="selectin"
    )
    proveedor: Mapped["Proveedor"] = relationship("Proveedor", lazy="selectin")


class LeasingFinancieroChecklistItem(Base):
    __tablename__ = "comercial_lf_checklist_item"
    __table_args__ = (UniqueConstraint("cotizacion_id", "codigo", name="uq_lf_checklist_cot_codigo"),)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    cotizacion_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("comercial_lf_cotizaciones.id", ondelete="CASCADE"), nullable=False, index=True
    )
    codigo: Mapped[str] = mapped_column(String(50), nullable=False)
    titulo: Mapped[str] = mapped_column(String(200), nullable=False)
    es_automatico: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default=text("false"))
    es_bloqueante: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default=text("true"))
    estado: Mapped[str] = mapped_column(String(20), nullable=False, default="PENDIENTE", server_default="PENDIENTE")
    responsable: Mapped[str | None] = mapped_column(String(200))
    fecha_limite: Mapped[date | None] = mapped_column(Date)
    fecha_cumplimiento: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    aprobado_por: Mapped[str | None] = mapped_column(String(200))
    evidencia_ref: Mapped[str | None] = mapped_column(String(200))
    comentario: Mapped[str | None] = mapped_column(Text)
    orden: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=datetime.utcnow, server_default=text("CURRENT_TIMESTAMP")
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
        server_default=text("CURRENT_TIMESTAMP"),
    )

    cotizacion: Mapped["LeasingFinancieroCotizacion"] = relationship(
        "LeasingFinancieroCotizacion", back_populates="checklist_items", lazy="selectin"
    )
