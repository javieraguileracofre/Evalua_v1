# models/fondos_rendir/empleado.py
# -*- coding: utf-8 -*-
"""Trabajador (chofer / personal) para fondos por rendir — base mínima; RR.HH. ampliará."""
from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import BigInteger, Boolean, DateTime, Index, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from db.base_class import Base

if TYPE_CHECKING:
    from models.fondos_rendir.fondo_rendir import FondoRendir
    from models.transporte.viaje import TransporteViaje


class Empleado(Base):
    __tablename__ = "empleados"

    __table_args__ = (
        Index("ix_empleados_rut", "rut"),
        Index("ix_empleados_activo", "activo"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    rut: Mapped[str] = mapped_column(String(16), nullable=False, unique=True)
    nombre_completo: Mapped[str] = mapped_column(String(200), nullable=False)
    cargo: Mapped[str | None] = mapped_column(String(120), nullable=True)
    email: Mapped[str | None] = mapped_column(String(120), nullable=True)
    telefono: Mapped[str | None] = mapped_column(String(32), nullable=True)

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
        back_populates="empleado",
    )
    viajes_transporte: Mapped[list["TransporteViaje"]] = relationship(
        "TransporteViaje",
        back_populates="empleado",
    )
