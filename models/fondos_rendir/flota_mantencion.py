# -*- coding: utf-8 -*-
from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import BigInteger, Date, DateTime, ForeignKey, Index, Numeric, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from db.base_class import Base

if TYPE_CHECKING:
    from models.fondos_rendir.vehiculo_transporte import VehiculoTransporte


TIPOS_MANTENCION = ("PREVENTIVA", "CORRECTIVA", "NEUMATICOS", "ACEITE", "OTRO")


class FlotaMantencion(Base):
    __tablename__ = "flota_mantenciones"

    __table_args__ = (
        Index("ix_flota_mantenciones_vehiculo", "vehiculo_transporte_id"),
        Index("ix_flota_mantenciones_fecha", "fecha"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    vehiculo_transporte_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("vehiculos_transporte.id", ondelete="CASCADE"),
        nullable=False,
    )
    fecha: Mapped[date] = mapped_column(Date, nullable=False)
    odometro: Mapped[int | None] = mapped_column(nullable=True)
    tipo: Mapped[str] = mapped_column(String(24), nullable=False, default="PREVENTIVA")
    proveedor: Mapped[str | None] = mapped_column(String(160), nullable=True)
    documento: Mapped[str | None] = mapped_column(String(100), nullable=True)
    costo: Mapped[Decimal | None] = mapped_column(Numeric(18, 2), nullable=True)
    observaciones: Mapped[str | None] = mapped_column(Text, nullable=True)
    proxima_fecha: Mapped[date | None] = mapped_column(Date, nullable=True)
    proximo_km: Mapped[int | None] = mapped_column(nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=False),
        nullable=False,
        default=datetime.utcnow,
        server_default=func.now(),
    )

    vehiculo: Mapped["VehiculoTransporte"] = relationship(
        "VehiculoTransporte",
        back_populates="mantenciones",
    )
