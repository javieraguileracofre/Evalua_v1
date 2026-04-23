# models/postventa/postventa.py
# -*- coding: utf-8 -*-
from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import BigInteger, DateTime, ForeignKey, Index, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from db.base_class import Base

if TYPE_CHECKING:
    from models.maestros.cliente import Cliente


class PostventaInteraccion(Base):
    """Registro de contacto con el cliente (llamada, visita, etc.)."""

    __tablename__ = "postventa_interacciones"

    __table_args__ = (
        Index("ix_pv_int_cliente_fecha", "cliente_id", "fecha_evento"),
        Index("ix_pv_int_tipo", "tipo"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)

    cliente_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("clientes.id", ondelete="RESTRICT"),
        nullable=False,
    )

    tipo: Mapped[str] = mapped_column(String(30), nullable=False, default="LLAMADA")
    asunto: Mapped[str | None] = mapped_column(String(200), nullable=True)
    detalle: Mapped[str] = mapped_column(Text, nullable=False, default="")

    duracion_minutos: Mapped[int | None] = mapped_column(Integer, nullable=True)
    resultado: Mapped[str | None] = mapped_column(String(40), nullable=True)
    registrado_por: Mapped[str | None] = mapped_column(String(120), nullable=True)

    fecha_evento: Mapped[datetime] = mapped_column(
        DateTime(timezone=False),
        nullable=False,
        default=datetime.utcnow,
        server_default=func.now(),
    )

    fecha_creacion: Mapped[datetime] = mapped_column(
        DateTime(timezone=False),
        nullable=False,
        default=datetime.utcnow,
        server_default=func.now(),
    )

    cliente: Mapped["Cliente"] = relationship("Cliente", back_populates="postventa_interacciones")


class PostventaSolicitud(Base):
    """Solicitud o caso de postventa vinculado al cliente."""

    __tablename__ = "postventa_solicitudes"

    __table_args__ = (
        Index("ix_pv_sol_cliente_estado", "cliente_id", "estado"),
        Index("ix_pv_sol_fecha", "fecha_apertura"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)

    cliente_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("clientes.id", ondelete="RESTRICT"),
        nullable=False,
    )

    titulo: Mapped[str] = mapped_column(String(250), nullable=False)
    descripcion: Mapped[str] = mapped_column(Text, nullable=False, default="")
    categoria: Mapped[str] = mapped_column(String(50), nullable=False, default="CONSULTA")
    estado: Mapped[str] = mapped_column(String(30), nullable=False, default="ABIERTA")
    prioridad: Mapped[str] = mapped_column(String(20), nullable=False, default="MEDIA")

    fecha_apertura: Mapped[datetime] = mapped_column(
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

    fecha_cierre: Mapped[datetime | None] = mapped_column(DateTime(timezone=False), nullable=True)

    cliente: Mapped["Cliente"] = relationship("Cliente", back_populates="postventa_solicitudes")
