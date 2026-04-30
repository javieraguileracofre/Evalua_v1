# models/fondos_rendir/empleado.py
# -*- coding: utf-8 -*-
"""Trabajador (chofer / personal) para fondos por rendir — base mínima; RR.HH. ampliará."""
from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import BigInteger, Boolean, DateTime, ForeignKey, Index, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from db.base_class import Base

if TYPE_CHECKING:
    from models.auth.usuario import Usuario
    from models.fondos_rendir.fondo_rendir import FondoRendir
    from models.remuneraciones.models import ContratoLaboral, DetalleRemuneracion
    from models.transporte.viaje import TransporteViaje


class Empleado(Base):
    __tablename__ = "empleados"

    __table_args__ = (
        Index("ix_empleados_rut", "rut"),
        Index("ix_empleados_activo", "activo"),
        Index("ix_empleados_auth_usuario_id", "auth_usuario_id"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    rut: Mapped[str] = mapped_column(String(16), nullable=False, unique=True)
    nombre_completo: Mapped[str] = mapped_column(String(200), nullable=False)
    cargo: Mapped[str | None] = mapped_column(String(120), nullable=True)
    email: Mapped[str | None] = mapped_column(String(120), nullable=True)
    telefono: Mapped[str | None] = mapped_column(String(32), nullable=True)

    auth_usuario_id: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey("auth_usuarios.id", ondelete="SET NULL"),
        nullable=True,
    )

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
    contratos_laborales: Mapped[list["ContratoLaboral"]] = relationship(
        "ContratoLaboral",
        back_populates="empleado",
    )
    detalles_remuneracion: Mapped[list["DetalleRemuneracion"]] = relationship(
        "DetalleRemuneracion",
        back_populates="empleado",
    )
    usuario_portal: Mapped["Usuario | None"] = relationship(
        "Usuario",
        foreign_keys=[auth_usuario_id],
    )
