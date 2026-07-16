# models/comercial/leasing_financiero_credito.py
# -*- coding: utf-8 -*-
from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import TYPE_CHECKING, Any

from sqlalchemy import BigInteger, Date, DateTime, ForeignKey, Integer, JSON, Numeric, String, Text, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from db.base_class import Base

if TYPE_CHECKING:
    from models.comercial.leasing_financiero_cotizacion import LeasingFinancieroCotizacion
    from models.maestros.cliente import Cliente


class LeasingFinancieroAnalisisCredito(Base):
    __tablename__ = "comercial_lf_analisis_credito"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    cotizacion_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("comercial_lf_cotizaciones.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
        index=True,
    )
    cliente_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("clientes.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    tipo_persona: Mapped[str] = mapped_column(String(20), nullable=False, default="NATURAL", server_default="NATURAL")
    tipo_producto: Mapped[str] = mapped_column(
        String(30), nullable=False, default="leasing_financiero", server_default="leasing_financiero"
    )
    moneda_referencia: Mapped[str] = mapped_column(String(10), nullable=False, default="CLP", server_default="CLP")

    ingreso_neto_mensual: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False, default=Decimal("0"), server_default="0")
    carga_financiera_mensual: Mapped[Decimal] = mapped_column(
        Numeric(18, 2), nullable=False, default=Decimal("0"), server_default="0"
    )
    antiguedad_laboral_meses: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")

    ventas_anuales: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False, default=Decimal("0"), server_default="0")
    ebitda_anual: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False, default=Decimal("0"), server_default="0")
    deuda_financiera_total: Mapped[Decimal] = mapped_column(
        Numeric(18, 2), nullable=False, default=Decimal("0"), server_default="0"
    )
    patrimonio: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False, default=Decimal("0"), server_default="0")
    anios_operacion: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")

    activo_corriente: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False, default=Decimal("0"), server_default="0")
    pasivo_corriente: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False, default=Decimal("0"), server_default="0")
    activo_total: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False, default=Decimal("0"), server_default="0")
    pasivo_total: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False, default=Decimal("0"), server_default="0")
    utilidad_neta_anual: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False, default=Decimal("0"), server_default="0")
    gastos_financieros_anual: Mapped[Decimal] = mapped_column(
        Numeric(18, 2), nullable=False, default=Decimal("0"), server_default="0"
    )
    ventas_12m_iva: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False, default=Decimal("0"), server_default="0")
    iva_debito_12m: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False, default=Decimal("0"), server_default="0")
    iva_credito_12m: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False, default=Decimal("0"), server_default="0")

    score_buro: Mapped[int | None] = mapped_column(Integer)
    comportamiento_pago: Mapped[str] = mapped_column(
        String(20), nullable=False, default="SIN_HISTORIAL", server_default="SIN_HISTORIAL"
    )
    ltv_pct: Mapped[Decimal] = mapped_column(Numeric(7, 2), nullable=False, default=Decimal("0"), server_default="0")
    dscr: Mapped[Decimal | None] = mapped_column(Numeric(9, 4))
    leverage_ratio: Mapped[Decimal | None] = mapped_column(Numeric(9, 4))
    liquidez_corriente: Mapped[Decimal | None] = mapped_column(Numeric(9, 4))
    margen_ebitda_pct: Mapped[Decimal | None] = mapped_column(Numeric(9, 4))
    endeudamiento_pct: Mapped[Decimal | None] = mapped_column(Numeric(9, 4))
    capital_trabajo: Mapped[Decimal | None] = mapped_column(Numeric(18, 2))
    cobertura_gastos_fin: Mapped[Decimal | None] = mapped_column(Numeric(9, 4))
    rentabilidad_neta_pct: Mapped[Decimal | None] = mapped_column(Numeric(9, 4))
    ratios_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict, server_default=text("'{}'::jsonb"))
    documentos_resumen_json: Mapped[dict[str, Any]] = mapped_column(
        JSON, nullable=False, default=dict, server_default=text("'{}'::jsonb")
    )

    score_total: Mapped[Decimal] = mapped_column(Numeric(6, 2), nullable=False, default=Decimal("0"), server_default="0")
    rating: Mapped[str] = mapped_column(String(4), nullable=False, default="E", server_default="E")
    recomendacion: Mapped[str] = mapped_column(String(20), nullable=False, default="RECHAZADO", server_default="RECHAZADO")
    nivel_riesgo: Mapped[str] = mapped_column(String(20), nullable=False, default="ALTO", server_default="ALTO")
    motivo_resumen: Mapped[str] = mapped_column(Text, nullable=False, default="", server_default="")
    supuestos: Mapped[str] = mapped_column(Text, nullable=False, default="", server_default="")
    analista: Mapped[str] = mapped_column(String(200), nullable=False, default="sistema", server_default="sistema")

    creado_en: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=datetime.utcnow, server_default=text("CURRENT_TIMESTAMP")
    )
    actualizado_en: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
        server_default=text("CURRENT_TIMESTAMP"),
    )

    cotizacion: Mapped["LeasingFinancieroCotizacion"] = relationship(
        "LeasingFinancieroCotizacion",
        back_populates="analisis_credito",
        lazy="selectin",
    )
    cliente: Mapped["Cliente"] = relationship(
        "Cliente",
        back_populates="leasing_fin_analisis_credito",
        lazy="selectin",
    )


class LeasingFinancieroCreditoDocumento(Base):
    __tablename__ = "comercial_lf_credito_documento"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    cotizacion_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("comercial_lf_cotizaciones.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    cliente_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("clientes.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    tipo_documento: Mapped[str] = mapped_column(String(40), nullable=False)
    nombre_archivo: Mapped[str] = mapped_column(String(255), nullable=False)
    mime_type: Mapped[str] = mapped_column(String(120), nullable=False, default="application/octet-stream")
    storage_path: Mapped[str] = mapped_column(String(500), nullable=False)
    hash_sha256: Mapped[str | None] = mapped_column(String(64))
    tamano_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0, server_default="0")
    estado: Mapped[str] = mapped_column(String(20), nullable=False, default="RECIBIDO", server_default="RECIBIDO")
    periodo_desde: Mapped[date | None] = mapped_column(Date)
    periodo_hasta: Mapped[date | None] = mapped_column(Date)
    datos_extraidos: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict, server_default=text("'{}'::jsonb"))
    observaciones: Mapped[str] = mapped_column(Text, nullable=False, default="", server_default="")
    cargado_por: Mapped[str] = mapped_column(String(200), nullable=False, default="sistema", server_default="sistema")
    creado_en: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=datetime.utcnow, server_default=text("CURRENT_TIMESTAMP")
    )
    actualizado_en: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
        server_default=text("CURRENT_TIMESTAMP"),
    )
