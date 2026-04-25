# models/comercial/leasing_financiero_cotizacion.py
# -*- coding: utf-8 -*-
from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import (
    BigInteger,
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from db.base_class import Base

if TYPE_CHECKING:
    from models.maestros.cliente import Cliente
    from models.comercial.leasing_financiero_credito import LeasingFinancieroAnalisisCredito


class LeasingFinancieroCotizacion(Base):
    """Cotización leasing financiero (tabla comercial_lf_cotizaciones)."""

    __tablename__ = "comercial_lf_cotizaciones"
    __table_args__ = (
        Index("ix_comercial_lf_cot_cliente_fecha", "cliente_id", "fecha_cotizacion"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)

    cliente_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("clientes.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    cliente: Mapped["Cliente"] = relationship(
        "Cliente",
        back_populates="leasing_fin_cotizaciones",
        lazy="selectin",
    )

    monto: Mapped[Decimal | None] = mapped_column(Numeric(18, 2))
    moneda: Mapped[str] = mapped_column(String(10), default="CLP", server_default="CLP")
    dolar_valor: Mapped[Decimal | None] = mapped_column(Numeric(14, 4))

    tasa: Mapped[Decimal | None] = mapped_column(Numeric(9, 6))
    plazo: Mapped[int | None] = mapped_column(Integer)
    opcion_compra: Mapped[Decimal | None] = mapped_column(Numeric(18, 2))

    periodos_gracia: Mapped[int] = mapped_column(Integer, default=0, server_default="0")

    fecha_inicio: Mapped[date | None] = mapped_column(Date)
    valor_neto: Mapped[Decimal | None] = mapped_column(Numeric(18, 2))

    pago_inicial_tipo: Mapped[str | None] = mapped_column(String(20))
    pago_inicial_valor: Mapped[Decimal | None] = mapped_column(Numeric(18, 2))

    financia_seguro: Mapped[bool] = mapped_column(Boolean, default=False, server_default=text("false"))
    seguro_monto_uf: Mapped[Decimal | None] = mapped_column(Numeric(18, 4))
    otros_montos_pesos: Mapped[Decimal | None] = mapped_column(Numeric(18, 2))

    concesionario: Mapped[str | None] = mapped_column(String(255))
    ejecutivo: Mapped[str | None] = mapped_column(String(255))

    fecha_cotizacion: Mapped[date] = mapped_column(
        Date,
        default=date.today,
        server_default=text("CURRENT_DATE"),
        nullable=False,
    )

    uf_valor: Mapped[Decimal | None] = mapped_column(Numeric(14, 4))
    monto_financiado: Mapped[Decimal | None] = mapped_column(Numeric(18, 2))

    estado: Mapped[str] = mapped_column(
        String(40),
        nullable=False,
        default="PENDIENTE",
        server_default=text("'PENDIENTE'"),
    )

    contrato_activo: Mapped[bool] = mapped_column(Boolean, default=False, server_default=text("false"))

    proyeccion_lineas: Mapped[list["LeasingFinancieroProyeccionLinea"]] = relationship(
        "LeasingFinancieroProyeccionLinea",
        back_populates="cotizacion",
        cascade="all, delete-orphan",
        order_by="LeasingFinancieroProyeccionLinea.secuencia",
    )
    analisis_credito: Mapped["LeasingFinancieroAnalisisCredito | None"] = relationship(
        "LeasingFinancieroAnalisisCredito",
        back_populates="cotizacion",
        uselist=False,
        cascade="all, delete-orphan",
        lazy="selectin",
    )

    creado_en: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=datetime.utcnow,
        server_default=text("CURRENT_TIMESTAMP"),
    )
    actualizado_en: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
        server_default=text("CURRENT_TIMESTAMP"),
    )


class LeasingFinancieroProyeccionLinea(Base):
    """Líneas de proyección contable automática por cotización."""

    __tablename__ = "comercial_lf_proyeccion_linea"
    __table_args__ = (UniqueConstraint("cotizacion_id", "secuencia", name="uq_comercial_lf_proy_seq"),)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    cotizacion_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("comercial_lf_cotizaciones.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    cotizacion: Mapped["LeasingFinancieroCotizacion"] = relationship(
        "LeasingFinancieroCotizacion",
        back_populates="proyeccion_lineas",
    )

    secuencia: Mapped[int] = mapped_column(Integer, nullable=False)
    etapa: Mapped[str] = mapped_column(String(40), nullable=False)
    ref_cuota: Mapped[int | None] = mapped_column(Integer)
    glosa: Mapped[str] = mapped_column(String(500), nullable=False)
    cuenta_codigo: Mapped[str] = mapped_column(String(30), nullable=False)
    debe: Mapped[Decimal] = mapped_column(Numeric(18, 2), default=Decimal("0"), server_default="0")
    haber: Mapped[Decimal] = mapped_column(Numeric(18, 2), default=Decimal("0"), server_default="0")

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=datetime.utcnow,
        server_default=text("CURRENT_TIMESTAMP"),
    )
