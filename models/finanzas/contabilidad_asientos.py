# models/finanzas/contabilidad_asientos.py
# -*- coding: utf-8 -*-
from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from sqlalchemy import BigInteger, DateTime, ForeignKey, Index, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from db.base_class import Base


class AsientoContable(Base):
    """
    Cabecera del asiento contable.
    Tabla física esperada: public.asientos_contables
    """
    __tablename__ = "asientos_contables"

    __table_args__ = (
        Index("ix_asientos_contables_origen", "origen_tipo", "origen_id"),
        Index("ix_asientos_contables_fecha", "fecha"),
        Index("ix_asientos_contables_estado", "estado"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)

    fecha: Mapped[datetime] = mapped_column(
        DateTime(timezone=False),
        nullable=False,
        default=datetime.utcnow,
    )

    origen_tipo: Mapped[str] = mapped_column(String(30), nullable=False)
    origen_id: Mapped[int] = mapped_column(BigInteger, nullable=False)

    glosa: Mapped[str] = mapped_column(String(255), nullable=False)
    moneda: Mapped[str] = mapped_column(String(10), nullable=False, default="CLP")
    estado: Mapped[str] = mapped_column(String(20), nullable=False, default="PUBLICADO")
    usuario: Mapped[str | None] = mapped_column(String(100), nullable=True)

    fecha_creacion: Mapped[datetime] = mapped_column(
        DateTime(timezone=False),
        nullable=False,
        default=datetime.utcnow,
    )
    fecha_actualizacion: Mapped[datetime] = mapped_column(
        DateTime(timezone=False),
        nullable=False,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
    )

    detalles: Mapped[list["AsientoDetalle"]] = relationship(
        "AsientoDetalle",
        back_populates="asiento",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="AsientoDetalle.id",
    )


class AsientoDetalle(Base):
    """
    Detalle del asiento.
    Tabla física esperada: public.asientos_detalle
    """
    __tablename__ = "asientos_detalle"

    __table_args__ = (
        Index("ix_asientos_detalle_cuenta", "codigo_cuenta"),
        Index("ix_asientos_detalle_asiento", "asiento_id"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)

    asiento_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("asientos_contables.id", ondelete="CASCADE"),
        nullable=False,
    )

    codigo_cuenta: Mapped[str] = mapped_column(String(20), nullable=False)
    nombre_cuenta: Mapped[str] = mapped_column(String(255), nullable=False)
    descripcion: Mapped[str | None] = mapped_column(String(255), nullable=True)

    debe: Mapped[Decimal] = mapped_column(
        Numeric(14, 2),
        nullable=False,
        default=Decimal("0.00"),
    )
    haber: Mapped[Decimal] = mapped_column(
        Numeric(14, 2),
        nullable=False,
        default=Decimal("0.00"),
    )

    asiento: Mapped["AsientoContable"] = relationship(
        "AsientoContable",
        back_populates="detalles",
    )