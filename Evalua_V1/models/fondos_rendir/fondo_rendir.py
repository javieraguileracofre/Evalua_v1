# models/fondos_rendir/fondo_rendir.py
# -*- coding: utf-8 -*-
from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import (
    BigInteger,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from db.base_class import Base

if TYPE_CHECKING:
    from models.fondos_rendir.empleado import Empleado
    from models.fondos_rendir.vehiculo_transporte import VehiculoTransporte
    from models.transporte.viaje import TransporteViaje


# Estados del ciclo de vida del anticipo / rendición
ESTADOS_FONDO = (
    "ABIERTO",
    "PENDIENTE_APROBACION",
    "APROBADO",
    "RECHAZADO",
)


class FondoRendir(Base):
    """Anticipo entregado a un trabajador; se liquida con líneas de gasto y aprobación."""

    __tablename__ = "fondos_rendir"

    __table_args__ = (
        Index("ix_fondos_rendir_folio", "folio"),
        Index("ix_fondos_rendir_empleado", "empleado_id"),
        Index("ix_fondos_rendir_estado", "estado"),
        Index("ix_fondos_rendir_fecha_entrega", "fecha_entrega"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    folio: Mapped[str] = mapped_column(String(32), nullable=False, unique=True)

    empleado_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("empleados.id", ondelete="RESTRICT"),
        nullable=False,
    )
    vehiculo_transporte_id: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey("vehiculos_transporte.id", ondelete="SET NULL"),
        nullable=True,
    )

    monto_anticipo: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    fecha_entrega: Mapped[datetime] = mapped_column(DateTime(timezone=False), nullable=False)

    estado: Mapped[str] = mapped_column(String(32), nullable=False, default="ABIERTO")
    fecha_envio_rendicion: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=False),
        nullable=True,
    )
    fecha_aprobacion: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=False),
        nullable=True,
    )
    motivo_rechazo: Mapped[str | None] = mapped_column(Text, nullable=True)
    observaciones: Mapped[str | None] = mapped_column(Text, nullable=True)

    asiento_id_entrega: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    asiento_id_liquidacion: Mapped[int | None] = mapped_column(BigInteger, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=False),
        nullable=False,
        default=datetime.utcnow,
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=False),
        nullable=False,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
        server_default=func.now(),
    )

    empleado: Mapped["Empleado"] = relationship("Empleado", back_populates="fondos")
    vehiculo: Mapped["VehiculoTransporte | None"] = relationship(
        "VehiculoTransporte",
        back_populates="fondos",
    )
    lineas_gasto: Mapped[list["FondoRendirGasto"]] = relationship(
        "FondoRendirGasto",
        back_populates="fondo",
        cascade="all, delete-orphan",
        order_by="FondoRendirGasto.linea",
    )
    viajes_transporte: Mapped[list["TransporteViaje"]] = relationship(
        "TransporteViaje",
        back_populates="fondo",
    )


class FondoRendirGasto(Base):
    __tablename__ = "fondos_rendir_gastos"

    __table_args__ = (
        UniqueConstraint("fondo_id", "linea", name="uq_fondos_rendir_gastos_fondo_linea"),
        Index("ix_fondos_rendir_gastos_fondo", "fondo_id"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    fondo_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("fondos_rendir.id", ondelete="CASCADE"),
        nullable=False,
    )
    linea: Mapped[int] = mapped_column(Integer, nullable=False)

    fecha_gasto: Mapped[datetime] = mapped_column(DateTime(timezone=False), nullable=False)
    rubro: Mapped[str] = mapped_column(String(80), nullable=False)
    descripcion: Mapped[str | None] = mapped_column(String(500), nullable=True)
    monto: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    nro_documento: Mapped[str | None] = mapped_column(String(64), nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=False),
        nullable=False,
        default=datetime.utcnow,
        server_default=func.now(),
    )

    fondo: Mapped["FondoRendir"] = relationship("FondoRendir", back_populates="lineas_gasto")
