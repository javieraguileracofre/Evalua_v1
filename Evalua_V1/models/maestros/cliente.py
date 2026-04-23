# models/maestros/cliente.py
# -*- coding: utf-8 -*-
from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import BigInteger, Boolean, DateTime, Index, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from db.base_class import Base

if TYPE_CHECKING:
    from models.cobranza.cuentas_por_cobrar import CuentaPorCobrar
    from models.comercial.nota_venta import NotaVenta
    from models.comercial.orden_servicio import OrdenServicio
    from models.comercial.vehiculo import Vehiculo
    from models.postventa.postventa import PostventaInteraccion, PostventaSolicitud


class Cliente(Base):
    __tablename__ = "clientes"

    __table_args__ = (
        Index("ix_clientes_rut", "rut"),
        Index("ix_clientes_activo", "activo"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    rut: Mapped[str] = mapped_column(String(20), nullable=False, unique=True)
    razon_social: Mapped[str] = mapped_column(String(200), nullable=False)
    nombre_fantasia: Mapped[str | None] = mapped_column(String(200), nullable=True)
    giro: Mapped[str | None] = mapped_column(String(200), nullable=True)
    direccion: Mapped[str | None] = mapped_column(String(250), nullable=True)
    comuna: Mapped[str | None] = mapped_column(String(100), nullable=True)
    ciudad: Mapped[str | None] = mapped_column(String(100), nullable=True)
    telefono: Mapped[str | None] = mapped_column(String(50), nullable=True)
    email: Mapped[str | None] = mapped_column(String(150), nullable=True)

    activo: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
        server_default="true",
    )

    fecha_creacion: Mapped[datetime] = mapped_column(
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

    notas_venta: Mapped[list["NotaVenta"]] = relationship(
        "NotaVenta",
        back_populates="cliente",
    )

    cuentas_por_cobrar: Mapped[list["CuentaPorCobrar"]] = relationship(
        "CuentaPorCobrar",
        back_populates="cliente",
    )

    postventa_interacciones: Mapped[list["PostventaInteraccion"]] = relationship(
        "PostventaInteraccion",
        back_populates="cliente",
    )

    postventa_solicitudes: Mapped[list["PostventaSolicitud"]] = relationship(
        "PostventaSolicitud",
        back_populates="cliente",
    )

    vehiculos: Mapped[list["Vehiculo"]] = relationship(
        "Vehiculo",
        back_populates="cliente",
    )
    ordenes_servicio: Mapped[list["OrdenServicio"]] = relationship(
        "OrdenServicio",
        back_populates="cliente",
    )