# models/cobranza/cuentas_por_cobrar.py
# -*- coding: utf-8 -*-
from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import BigInteger, Date, DateTime, ForeignKey, Index, Numeric, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from db.base_class import Base

if TYPE_CHECKING:
    from models.comercial.nota_venta import NotaVenta
    from models.finanzas.caja import Caja
    from models.maestros.cliente import Cliente


class CuentaPorCobrar(Base):
    __tablename__ = "cuentas_por_cobrar"

    __table_args__ = (
        Index("ix_cxc_cliente_estado", "cliente_id", "estado"),
        Index("ix_cxc_fecha_vencimiento", "fecha_vencimiento"),
        Index("ix_cxc_nota_venta", "nota_venta_id"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)

    cliente_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("clientes.id", ondelete="RESTRICT"),
        nullable=False,
    )

    nota_venta_id: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey("notas_venta.id", ondelete="SET NULL"),
        nullable=True,
    )

    fecha_emision: Mapped[date] = mapped_column(Date, nullable=False)
    fecha_vencimiento: Mapped[date] = mapped_column(Date, nullable=False)

    monto_original: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    saldo_pendiente: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)

    estado: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="PENDIENTE",
        server_default="PENDIENTE",
    )

    observacion: Mapped[str | None] = mapped_column(Text, nullable=True)

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
        back_populates="cuentas_por_cobrar",
    )

    nota_venta: Mapped["NotaVenta | None"] = relationship(
        "NotaVenta",
        back_populates="cuentas_por_cobrar",
    )

    pagos: Mapped[list["PagoCliente"]] = relationship(
        "PagoCliente",
        back_populates="cuenta_cobrar",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )


class PagoCliente(Base):
    __tablename__ = "pagos_clientes"

    __table_args__ = (
        Index("ix_pagos_clientes_cuenta", "cuenta_cobrar_id"),
        Index("ix_pagos_clientes_fecha_pago", "fecha_pago"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)

    cuenta_cobrar_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("cuentas_por_cobrar.id", ondelete="CASCADE"),
        nullable=False,
    )

    fecha_pago: Mapped[datetime] = mapped_column(
        DateTime(timezone=False),
        nullable=False,
        default=datetime.utcnow,
        server_default=func.now(),
    )

    monto_pago: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    forma_pago: Mapped[str] = mapped_column(String(50), nullable=False)

    caja_id: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey("cajas.id", ondelete="SET NULL"),
        nullable=True,
    )

    referencia: Mapped[str | None] = mapped_column(String(100), nullable=True)
    observacion: Mapped[str | None] = mapped_column(Text, nullable=True)

    cuenta_cobrar: Mapped["CuentaPorCobrar"] = relationship(
        "CuentaPorCobrar",
        back_populates="pagos",
    )

    caja: Mapped["Caja | None"] = relationship("Caja")