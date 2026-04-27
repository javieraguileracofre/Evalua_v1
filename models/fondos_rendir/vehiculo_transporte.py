# models/fondos_rendir/vehiculo_transporte.py
# -*- coding: utf-8 -*-
"""Camión / vehículo de flota (transporte) — distinto del vehículo de cliente (taller)."""
from __future__ import annotations

from datetime import date, datetime
from typing import TYPE_CHECKING

from decimal import Decimal

from sqlalchemy import BigInteger, Boolean, Date, DateTime, Index, Integer, Numeric, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from db.base_class import Base

if TYPE_CHECKING:
    from models.fondos_rendir.fondo_rendir import FondoRendir
    from models.fondos_rendir.flota_mantencion import FlotaMantencion
    from models.transporte.viaje import TransporteViaje


class VehiculoTransporte(Base):
    __tablename__ = "vehiculos_transporte"

    __table_args__ = (
        Index("ix_vehiculos_transporte_patente", "patente"),
        Index("ix_vehiculos_transporte_activo", "activo"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    patente: Mapped[str] = mapped_column(String(20), nullable=False, unique=True)
    marca: Mapped[str] = mapped_column(String(80), nullable=False)
    modelo: Mapped[str] = mapped_column(String(120), nullable=False)
    anio: Mapped[int | None] = mapped_column(Integer, nullable=True)
    observaciones: Mapped[str | None] = mapped_column(String(500), nullable=True)
    # Litros / 100 km de referencia (tablero comparativo vs consumo real del viaje).
    consumo_referencial_l100km: Mapped[Decimal | None] = mapped_column(Numeric(8, 2), nullable=True)
    tipo_vehiculo: Mapped[str | None] = mapped_column(String(40), nullable=True)
    capacidad_carga: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)
    odometro_actual: Mapped[int | None] = mapped_column(Integer, nullable=True)
    estado_operativo: Mapped[str] = mapped_column(
        String(24),
        nullable=False,
        default="DISPONIBLE",
        server_default="DISPONIBLE",
    )
    fecha_revision_tecnica: Mapped[date | None] = mapped_column(Date, nullable=True)
    fecha_permiso_circulacion: Mapped[date | None] = mapped_column(Date, nullable=True)
    fecha_seguro: Mapped[date | None] = mapped_column(Date, nullable=True)
    fecha_proxima_mantencion: Mapped[date | None] = mapped_column(Date, nullable=True)
    km_proxima_mantencion: Mapped[int | None] = mapped_column(Integer, nullable=True)

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

    fondos: Mapped[list["FondoRendir"]] = relationship(
        "FondoRendir",
        back_populates="vehiculo",
    )
    viajes: Mapped[list["TransporteViaje"]] = relationship(
        "TransporteViaje",
        back_populates="vehiculo",
    )
    mantenciones: Mapped[list["FlotaMantencion"]] = relationship(
        "FlotaMantencion",
        back_populates="vehiculo",
        cascade="all, delete-orphan",
        order_by="FlotaMantencion.fecha.desc()",
    )
