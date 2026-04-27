# models/transporte/viaje.py
# -*- coding: utf-8 -*-
"""Hoja de ruta / viaje de transporte — control operativo (no contable)."""
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
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from db.base_class import Base

if TYPE_CHECKING:
    from models.fondos_rendir.empleado import Empleado
    from models.fondos_rendir.fondo_rendir import FondoRendir
    from models.fondos_rendir.vehiculo_transporte import VehiculoTransporte
    from models.maestros.cliente import Cliente


ESTADOS_VIAJE = ("BORRADOR", "EN_CURSO", "CERRADO", "ANULADO")


class TransporteViaje(Base):
    """
    Registro de viaje (hoja de ruta): tiempos, odómetro, combustible y vínculo opcional a anticipo.
    """

    __tablename__ = "transporte_viajes"

    __table_args__ = (
        Index("ix_transporte_viajes_folio", "folio"),
        Index("ix_transporte_viajes_empleado", "empleado_id"),
        Index("ix_transporte_viajes_vehiculo", "vehiculo_transporte_id"),
        Index("ix_transporte_viajes_estado", "estado"),
        Index("ix_transporte_viajes_real_salida", "real_salida"),
        Index("ix_transporte_viajes_fondo", "fondo_rendir_id"),
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
    cliente_id: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey("clientes.id", ondelete="SET NULL"),
        nullable=True,
    )
    fondo_rendir_id: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey("fondos_rendir.id", ondelete="SET NULL"),
        nullable=True,
    )

    estado: Mapped[str] = mapped_column(String(24), nullable=False, default="BORRADOR")

    origen: Mapped[str] = mapped_column(String(240), nullable=False, default="")
    destino: Mapped[str] = mapped_column(String(240), nullable=False, default="")
    referencia_carga: Mapped[str | None] = mapped_column(String(200), nullable=True)
    tipo_carga: Mapped[str | None] = mapped_column(String(80), nullable=True)
    peso_carga: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)
    valor_flete: Mapped[Decimal | None] = mapped_column(Numeric(18, 2), nullable=True)
    costo_estimado: Mapped[Decimal | None] = mapped_column(Numeric(18, 2), nullable=True)
    costo_real: Mapped[Decimal | None] = mapped_column(Numeric(18, 2), nullable=True)
    km_vacio: Mapped[int | None] = mapped_column(Integer, nullable=True)
    km_cargado: Mapped[int | None] = mapped_column(Integer, nullable=True)

    programado_salida: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=False),
        nullable=True,
    )
    programado_llegada: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=False),
        nullable=True,
    )
    real_salida: Mapped[datetime | None] = mapped_column(DateTime(timezone=False), nullable=True)
    real_llegada: Mapped[datetime | None] = mapped_column(DateTime(timezone=False), nullable=True)

    odometro_inicio: Mapped[int | None] = mapped_column(Integer, nullable=True)
    odometro_fin: Mapped[int | None] = mapped_column(Integer, nullable=True)
    litros_combustible: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)

    notas: Mapped[str | None] = mapped_column(Text, nullable=True)
    motivo_desvio: Mapped[str | None] = mapped_column(Text, nullable=True)
    observaciones_cierre: Mapped[str | None] = mapped_column(Text, nullable=True)
    alerta_consumo: Mapped[bool] = mapped_column(nullable=False, default=False, server_default="false")
    motivo_anulacion: Mapped[str | None] = mapped_column(Text, nullable=True)
    usuario_creacion: Mapped[str | None] = mapped_column(String(120), nullable=True)
    usuario_modificacion: Mapped[str | None] = mapped_column(String(120), nullable=True)

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

    empleado: Mapped["Empleado"] = relationship("Empleado", back_populates="viajes_transporte")
    vehiculo: Mapped["VehiculoTransporte | None"] = relationship(
        "VehiculoTransporte",
        back_populates="viajes",
    )
    cliente: Mapped["Cliente | None"] = relationship("Cliente")
    fondo: Mapped["FondoRendir | None"] = relationship("FondoRendir", back_populates="viajes_transporte")
