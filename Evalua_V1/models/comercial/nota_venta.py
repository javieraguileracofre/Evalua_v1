# models/comercial/nota_venta.py
# -*- coding: utf-8 -*-
from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import BigInteger, Date, DateTime, ForeignKey, Index, Numeric, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from db.base_class import Base

if TYPE_CHECKING:
    from models.cobranza.cuentas_por_cobrar import CuentaPorCobrar
    from models.finanzas.caja import Caja
    from models.inventario.inventario import Producto
    from models.maestros.cliente import Cliente


class NotaVenta(Base):
    __tablename__ = "notas_venta"

    __table_args__ = (
        Index("ix_notas_venta_numero", "numero"),
        Index("ix_notas_venta_fecha", "fecha"),
        Index("ix_notas_venta_fecha_vencimiento", "fecha_vencimiento"),
        Index("ix_notas_venta_cliente_estado", "cliente_id", "estado"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    numero: Mapped[str] = mapped_column(String(50), nullable=False, unique=True)

    fecha: Mapped[datetime] = mapped_column(
        DateTime(timezone=False),
        nullable=False,
        default=datetime.utcnow,
        server_default=func.now(),
    )

    fecha_vencimiento: Mapped[date | None] = mapped_column(Date, nullable=True)

    cliente_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("clientes.id", ondelete="RESTRICT"),
        nullable=False,
    )

    caja_id: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey("cajas.id", ondelete="SET NULL"),
        nullable=True,
    )

    tipo_pago: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="CONTADO",
        server_default="CONTADO",
    )

    estado: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="EMITIDA",
        server_default="EMITIDA",
    )

    subtotal_neto: Mapped[Decimal] = mapped_column(
        Numeric(14, 2),
        nullable=False,
        default=Decimal("0.00"),
        server_default="0",
    )

    descuento_total: Mapped[Decimal] = mapped_column(
        Numeric(14, 2),
        nullable=False,
        default=Decimal("0.00"),
        server_default="0",
    )

    total_neto: Mapped[Decimal] = mapped_column(
        Numeric(14, 2),
        nullable=False,
        default=Decimal("0.00"),
        server_default="0",
    )

    total_iva: Mapped[Decimal] = mapped_column(
        Numeric(14, 2),
        nullable=False,
        default=Decimal("0.00"),
        server_default="0",
    )

    total_total: Mapped[Decimal] = mapped_column(
        Numeric(14, 2),
        nullable=False,
        default=Decimal("0.00"),
        server_default="0",
    )

    observacion: Mapped[str | None] = mapped_column(Text, nullable=True)
    usuario_emisor: Mapped[str | None] = mapped_column(String(100), nullable=True)

    fecha_creacion: Mapped[datetime] = mapped_column(
        DateTime(timezone=False),
        nullable=False,
        default=datetime.utcnow,
        server_default=func.now(),
    )

    fecha_actualizacion: Mapped[datetime] = mapped_column(
        DateTime(timezone=False),
        nullable=False,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
        server_default=func.now(),
    )

    cliente: Mapped["Cliente"] = relationship(
        "Cliente",
        back_populates="notas_venta",
    )

    caja: Mapped["Caja | None"] = relationship(
        "Caja",
        back_populates="notas_venta",
    )

    detalles: Mapped[list["NotaVentaDetalle"]] = relationship(
        "NotaVentaDetalle",
        back_populates="nota_venta",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )

    cuentas_por_cobrar: Mapped[list["CuentaPorCobrar"]] = relationship(
        "CuentaPorCobrar",
        back_populates="nota_venta",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )


class NotaVentaDetalle(Base):
    __tablename__ = "notas_venta_detalle"

    __table_args__ = (
        Index("ix_notas_venta_detalle_nota", "nota_venta_id"),
        Index("ix_notas_venta_detalle_producto", "producto_id"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)

    nota_venta_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("notas_venta.id", ondelete="CASCADE"),
        nullable=False,
    )

    producto_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("productos.id", ondelete="RESTRICT"),
        nullable=False,
    )

    descripcion: Mapped[str | None] = mapped_column(String(250), nullable=True)

    cantidad: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    precio_unitario: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)

    descuento_porcentaje: Mapped[Decimal] = mapped_column(
        Numeric(5, 2),
        nullable=False,
        default=Decimal("0.00"),
        server_default="0",
    )

    descuento_monto: Mapped[Decimal] = mapped_column(
        Numeric(14, 2),
        nullable=False,
        default=Decimal("0.00"),
        server_default="0",
    )

    subtotal: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)

    nota_venta: Mapped["NotaVenta"] = relationship(
        "NotaVenta",
        back_populates="detalles",
    )

    producto: Mapped["Producto"] = relationship("Producto")