# models/comercial/vehiculo.py
# -*- coding: utf-8 -*-
from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import BigInteger, Boolean, DateTime, ForeignKey, Index, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from db.base_class import Base

if TYPE_CHECKING:
    from models.comercial.orden_servicio import OrdenServicio
    from models.maestros.cliente import Cliente


class Vehiculo(Base):
    """Vehículo asociado a un cliente (taller automotriz)."""

    __tablename__ = "vehiculos"

    __table_args__ = (
        Index("ix_vehiculos_cliente", "cliente_id"),
        Index("ix_vehiculos_patente", "patente"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    cliente_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("clientes.id", ondelete="RESTRICT"),
        nullable=False,
    )
    patente: Mapped[str] = mapped_column(String(20), nullable=False)
    marca: Mapped[str] = mapped_column(String(80), nullable=False)
    modelo: Mapped[str] = mapped_column(String(120), nullable=False)
    color: Mapped[str | None] = mapped_column(String(60), nullable=True)
    anio: Mapped[int | None] = mapped_column(Integer, nullable=True)
    vin: Mapped[str | None] = mapped_column(String(32), nullable=True)
    km_actual: Mapped[int | None] = mapped_column(Integer, nullable=True)

    activo: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default="true")

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

    cliente: Mapped["Cliente"] = relationship("Cliente", back_populates="vehiculos")
    ordenes_servicio: Mapped[list["OrdenServicio"]] = relationship(
        "OrdenServicio",
        back_populates="vehiculo",
    )
