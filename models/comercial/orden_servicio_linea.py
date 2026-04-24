# models/comercial/orden_servicio_linea.py
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
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from db.base_class import Base

if TYPE_CHECKING:
    from models.comercial.orden_servicio import OrdenServicio


class OrdenServicioCotizacionLinea(Base):
    """Líneas de cotización / presupuesto de mano de obra y repuestos (orden de servicio taller)."""

    __tablename__ = "ordenes_servicio_cotizacion_lineas"

    __table_args__ = (
        UniqueConstraint("orden_servicio_id", "linea", name="uq_os_cotiz_orden_linea"),
        Index("ix_os_cotiz_linea_orden", "orden_servicio_id"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    orden_servicio_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("ordenes_servicio.id", ondelete="CASCADE"),
        nullable=False,
    )
    linea: Mapped[int] = mapped_column(Integer, nullable=False)
    descripcion: Mapped[str] = mapped_column(Text, nullable=False)
    cantidad: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False, default=Decimal("1"))
    precio_unitario: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    valor_neto: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=False),
        nullable=False,
        default=datetime.utcnow,
        server_default=func.now(),
    )

    orden: Mapped["OrdenServicio"] = relationship("OrdenServicio", back_populates="lineas_cotizacion")
