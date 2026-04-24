# models/finanzas/caja.py
# -*- coding: utf-8 -*-
from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Numeric,
    String,
    Text,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from db.base_class import Base

if TYPE_CHECKING:
    from models.comercial.nota_venta import NotaVenta


class Caja(Base):
    __tablename__ = "cajas"

    __table_args__ = (
        Index("ix_cajas_nombre", "nombre"),
        Index("ix_cajas_estado", "estado"),
        Index("ix_cajas_activa", "activa"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    nombre: Mapped[str] = mapped_column(String(100), nullable=False)
    descripcion: Mapped[str | None] = mapped_column(String(255), nullable=True)

    saldo_inicial: Mapped[Decimal] = mapped_column(
        Numeric(14, 2),
        nullable=False,
        default=Decimal("0.00"),
        server_default="0",
    )

    saldo_actual: Mapped[Decimal] = mapped_column(
        Numeric(14, 2),
        nullable=False,
        default=Decimal("0.00"),
        server_default="0",
    )

    fecha_apertura: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=False),
        nullable=True,
    )

    fecha_cierre: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=False),
        nullable=True,
    )

    estado: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="CERRADA",
        server_default="CERRADA",
    )

    activa: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
        server_default="true",
    )

    notas_venta: Mapped[list[NotaVenta]] = relationship(
        "NotaVenta",
        back_populates="caja",
    )

    movimientos: Mapped[list[MovimientoCaja]] = relationship(
        "MovimientoCaja",
        back_populates="caja",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )


class MovimientoCaja(Base):
    __tablename__ = "movimientos_caja"

    __table_args__ = (
        Index("ix_movimientos_caja_caja", "caja_id"),
        Index("ix_movimientos_caja_fecha", "fecha"),
        Index("ix_movimientos_caja_tipo", "tipo_movimiento"),
        Index("ix_movimientos_caja_referencia", "referencia_tipo", "referencia_id"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)

    caja_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("cajas.id", ondelete="CASCADE"),
        nullable=False,
    )

    fecha: Mapped[datetime] = mapped_column(
        DateTime(timezone=False),
        nullable=False,
        default=datetime.utcnow,
        server_default=func.now(),
    )

    tipo_movimiento: Mapped[str] = mapped_column(String(20), nullable=False)
    medio_pago: Mapped[str] = mapped_column(String(20), nullable=False)

    monto: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)

    referencia_tipo: Mapped[str | None] = mapped_column(String(30), nullable=True)
    referencia_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    observacion: Mapped[str | None] = mapped_column(Text, nullable=True)

    caja: Mapped[Caja] = relationship(
        "Caja",
        back_populates="movimientos",
    )