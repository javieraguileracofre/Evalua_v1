# models/comercial/orden_servicio.py
# -*- coding: utf-8 -*-
"""Orden de servicio / recepción de vehículo (taller automotriz)."""
from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Numeric,
    String,
    Text,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from db.base_class import Base

if TYPE_CHECKING:
    from models.comercial.orden_servicio_linea import OrdenServicioCotizacionLinea
    from models.comercial.vehiculo import Vehiculo
    from models.maestros.cliente import Cliente


class OrdenServicio(Base):
    __tablename__ = "ordenes_servicio"

    __table_args__ = (
        Index("ix_orden_servicio_folio", "folio"),
        Index("ix_orden_servicio_cliente", "cliente_id"),
        Index("ix_orden_servicio_estado", "estado"),
        Index("ix_orden_servicio_fecha", "fecha_recepcion"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    folio: Mapped[str | None] = mapped_column(String(32), nullable=True, unique=True)

    cliente_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("clientes.id", ondelete="RESTRICT"),
        nullable=False,
    )
    vehiculo_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("vehiculos.id", ondelete="RESTRICT"),
        nullable=False,
    )

    estado: Mapped[str] = mapped_column(
        String(24),
        nullable=False,
        default="RECIBIDA",
        server_default="RECIBIDA",
    )

    fecha_recepcion: Mapped[datetime] = mapped_column(
        DateTime(timezone=False),
        nullable=False,
        default=datetime.utcnow,
        server_default=func.now(),
    )
    fecha_entrega_estimada: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=False),
        nullable=True,
    )

    contacto_nombre: Mapped[str | None] = mapped_column(String(200), nullable=True)
    contacto_telefono: Mapped[str | None] = mapped_column(String(50), nullable=True)

    trabajo_solicitado: Mapped[str | None] = mapped_column(Text, nullable=True)
    observaciones: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Testigos tablero (marcado = encendido / reportado)
    testigo_airbag: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    testigo_check_engine: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    testigo_abs: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    testigo_aceite: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    testigo_bateria: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    testigo_cinturon: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    testigo_freno_mano: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    testigo_luces_altas: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    testigo_traccion: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    testigo_temperatura: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")

    # Inventario al ingreso (marcado = verificado presente)
    inv_gato: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    inv_herramientas: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    inv_triangulos: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    inv_tapetes: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    inv_llanta_repuesto: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    inv_extintor: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    inv_antena: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    inv_emblemas: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    inv_tapones_rueda: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    inv_cables: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    inv_estereo: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    inv_encendedor: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")

    # E, 1/4, 1/2, 3/4, F
    nivel_combustible: Mapped[str | None] = mapped_column(String(8), nullable=True)

    dano_vista_frente: Mapped[str | None] = mapped_column(Text, nullable=True)
    dano_vista_atras: Mapped[str | None] = mapped_column(Text, nullable=True)
    dano_vista_izquierda: Mapped[str | None] = mapped_column(Text, nullable=True)
    dano_vista_derecha: Mapped[str | None] = mapped_column(Text, nullable=True)

    pagare_monto: Mapped[Decimal | None] = mapped_column(Numeric(18, 2), nullable=True)
    pagare_ciudad: Mapped[str | None] = mapped_column(String(120), nullable=True)
    pagare_tasa_interes_mensual: Mapped[Decimal | None] = mapped_column(
        Numeric(8, 4),
        nullable=True,
    )

    # Cotización / administrativo
    ingreso_grua: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    ote_num: Mapped[str | None] = mapped_column(String(60), nullable=True)
    email_contacto: Mapped[str | None] = mapped_column(String(150), nullable=True)
    cotizacion_afecta_iva: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
        server_default="true",
    )

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

    cliente: Mapped["Cliente"] = relationship("Cliente", back_populates="ordenes_servicio")
    vehiculo: Mapped["Vehiculo"] = relationship("Vehiculo", back_populates="ordenes_servicio")
    lineas_cotizacion: Mapped[list["OrdenServicioCotizacionLinea"]] = relationship(
        "OrdenServicioCotizacionLinea",
        back_populates="orden",
        cascade="all, delete-orphan",
        order_by="OrdenServicioCotizacionLinea.linea",
    )
