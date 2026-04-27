# models/comercial/credito_riesgo.py
# -*- coding: utf-8 -*-
from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING, Any

from sqlalchemy import BigInteger, DateTime, ForeignKey, Integer, Numeric, String, Text, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from db.base_class import Base

if TYPE_CHECKING:
    from models.maestros.cliente import Cliente


class CreditoPolitica(Base):
    """Políticas y parámetros configurables del motor (ponderaciones, macro referencia)."""

    __tablename__ = "credito_politica"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    clave: Mapped[str] = mapped_column(String(80), nullable=False, unique=True, index=True)
    valor_json: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    descripcion: Mapped[str | None] = mapped_column(Text)
    activo: Mapped[bool] = mapped_column(default=True, nullable=False, server_default=text("true"))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("CURRENT_TIMESTAMP")
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("CURRENT_TIMESTAMP")
    )


class CreditoSolicitud(Base):
    __tablename__ = "credito_solicitud"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    cliente_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("clientes.id", ondelete="CASCADE"), nullable=False, index=True)
    comercial_lf_cotizacion_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True, index=True)

    codigo: Mapped[str | None] = mapped_column(String(40), unique=True, nullable=True)
    tipo_persona: Mapped[str] = mapped_column(String(20), nullable=False, default="NATURAL", server_default="NATURAL")
    producto: Mapped[str] = mapped_column(String(40), nullable=False, default="LEASING_FIN", server_default="LEASING_FIN")
    sector_actividad: Mapped[str | None] = mapped_column(String(120))
    moneda: Mapped[str] = mapped_column(String(10), nullable=False, default="CLP", server_default="CLP")

    monto_solicitado: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    plazo_solicitado: Mapped[int] = mapped_column(Integer, nullable=False)

    ingreso_mensual: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False, default=Decimal("0"), server_default="0")
    gastos_mensual: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False, default=Decimal("0"), server_default="0")
    deuda_cuotas_mensual: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False, default=Decimal("0"), server_default="0")
    cuota_propuesta: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False, default=Decimal("0"), server_default="0")

    tipo_contrato: Mapped[str | None] = mapped_column(String(40))
    mora_max_dias_12m: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    protestos: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    castigos: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    reprogramaciones: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")

    ventas_anual: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False, default=Decimal("0"), server_default="0")
    margen_bruto_pct: Mapped[Decimal] = mapped_column(Numeric(9, 4), nullable=False, default=Decimal("0"), server_default="0")
    ebitda_anual: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False, default=Decimal("0"), server_default="0")
    utilidad_neta_anual: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False, default=Decimal("0"), server_default="0")
    flujo_caja_mensual: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False, default=Decimal("0"), server_default="0")
    capital_trabajo: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False, default=Decimal("0"), server_default="0")

    deuda_total: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False, default=Decimal("0"), server_default="0")
    patrimonio: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False, default=Decimal("0"), server_default="0")
    liquidez_corriente: Mapped[Decimal | None] = mapped_column(Numeric(12, 4))

    antiguedad_meses_natural: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    anios_operacion_empresa: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")

    garantia_tipo: Mapped[str | None] = mapped_column(String(80))
    garantia_valor_comercial: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False, default=Decimal("0"), server_default="0")
    garantia_valor_liquidacion: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False, default=Decimal("0"), server_default="0")

    exposicion_usd_pct: Mapped[Decimal] = mapped_column(Numeric(6, 2), nullable=False, default=Decimal("0"), server_default="0")
    concentracion_ingresos_pct: Mapped[Decimal] = mapped_column(
        Numeric(6, 2), nullable=False, default=Decimal("0"), server_default="0"
    )
    historial_tributario: Mapped[str] = mapped_column(
        String(20), nullable=False, default="SIN_INFO", server_default="SIN_INFO"
    )

    estado: Mapped[str] = mapped_column(String(30), nullable=False, default="BORRADOR", server_default="BORRADOR")
    observaciones: Mapped[str] = mapped_column(Text, nullable=False, default="", server_default="")

    creado_en: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("CURRENT_TIMESTAMP")
    )
    actualizado_en: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("CURRENT_TIMESTAMP")
    )

    cliente: Mapped["Cliente"] = relationship("Cliente", lazy="joined")
    evaluaciones: Mapped[list["CreditoEvaluacion"]] = relationship(
        "CreditoEvaluacion", back_populates="solicitud", cascade="all, delete-orphan"
    )
    garantias: Mapped[list["CreditoGarantia"]] = relationship(
        "CreditoGarantia", back_populates="solicitud", cascade="all, delete-orphan"
    )
    documentos: Mapped[list["CreditoDocumento"]] = relationship(
        "CreditoDocumento", back_populates="solicitud", cascade="all, delete-orphan"
    )
    comites: Mapped[list["CreditoComite"]] = relationship(
        "CreditoComite", back_populates="solicitud", cascade="all, delete-orphan"
    )
    historial: Mapped[list["CreditoHistorial"]] = relationship(
        "CreditoHistorial", back_populates="solicitud", cascade="all, delete-orphan"
    )


class CreditoEvaluacion(Base):
    """Resultado de una corrida del motor (ScoreRiesgo + variables agregadas en JSON)."""

    __tablename__ = "credito_evaluacion"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    solicitud_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("credito_solicitud.id", ondelete="CASCADE"), nullable=False, index=True)

    score_total: Mapped[Decimal] = mapped_column(Numeric(7, 2), nullable=False)
    categoria: Mapped[str] = mapped_column(String(1), nullable=False)
    clasificacion_riesgo: Mapped[str] = mapped_column(String(20), nullable=False)

    monto_maximo_sugerido: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    plazo_maximo_sugerido: Mapped[int] = mapped_column(Integer, nullable=False)
    tasa_sugerida_anual: Mapped[Decimal] = mapped_column(Numeric(9, 6), nullable=False)

    recomendacion: Mapped[str] = mapped_column(String(30), nullable=False)
    flujo_evaluacion: Mapped[str] = mapped_column(
        String(20), nullable=False, default="PROFUNDO", server_default="PROFUNDO"
    )
    decision_motor: Mapped[str] = mapped_column(
        String(20), nullable=False, default="PENDIENTE", server_default="PENDIENTE"
    )
    explicacion: Mapped[str] = mapped_column(Text, nullable=False, default="", server_default="")
    desglose_json: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, server_default=text("'{}'::jsonb"))
    macro_json: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, server_default=text("'{}'::jsonb"))
    stress_cuotas_json: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, server_default=text("'{}'::jsonb"))
    log_reglas_json: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, server_default=text("'{}'::jsonb")
    )
    motor_version: Mapped[str] = mapped_column(String(20), nullable=False, default="v1", server_default="v1")

    creado_en: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("CURRENT_TIMESTAMP")
    )

    solicitud: Mapped["CreditoSolicitud"] = relationship("CreditoSolicitud", back_populates="evaluaciones")


class CreditoGarantia(Base):
    __tablename__ = "credito_garantia"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    solicitud_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("credito_solicitud.id", ondelete="CASCADE"), nullable=False, index=True)
    tipo: Mapped[str] = mapped_column(String(80), nullable=False)
    descripcion: Mapped[str | None] = mapped_column(Text)
    valor_comercial: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False, default=Decimal("0"), server_default="0")
    valor_liquidacion: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False, default=Decimal("0"), server_default="0")
    cobertura_pct: Mapped[Decimal | None] = mapped_column(Numeric(9, 4))
    creado_en: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("CURRENT_TIMESTAMP")
    )

    solicitud: Mapped["CreditoSolicitud"] = relationship("CreditoSolicitud", back_populates="garantias")


class CreditoDocumento(Base):
    __tablename__ = "credito_documento"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    solicitud_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("credito_solicitud.id", ondelete="CASCADE"), nullable=False, index=True)
    tipo_documento: Mapped[str] = mapped_column(String(80), nullable=False)
    referencia: Mapped[str] = mapped_column(String(255), nullable=False, default="", server_default="")
    creado_en: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("CURRENT_TIMESTAMP")
    )

    solicitud: Mapped["CreditoSolicitud"] = relationship("CreditoSolicitud", back_populates="documentos")


class CreditoComite(Base):
    __tablename__ = "credito_comite"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    solicitud_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("credito_solicitud.id", ondelete="CASCADE"), nullable=False, index=True)
    estado: Mapped[str] = mapped_column(String(20), nullable=False, default="PENDIENTE", server_default="PENDIENTE")
    resumen: Mapped[str] = mapped_column(Text, nullable=False, default="", server_default="")
    decision: Mapped[str | None] = mapped_column(String(30))
    comentario: Mapped[str] = mapped_column(Text, nullable=False, default="", server_default="")
    analista: Mapped[str] = mapped_column(String(200), nullable=False, default="sistema", server_default="sistema")
    fecha_apertura: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("CURRENT_TIMESTAMP")
    )
    fecha_cierre: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    solicitud: Mapped["CreditoSolicitud"] = relationship("CreditoSolicitud", back_populates="comites")


class CreditoHistorial(Base):
    __tablename__ = "credito_historial"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    solicitud_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("credito_solicitud.id", ondelete="CASCADE"), nullable=False, index=True)
    evento: Mapped[str] = mapped_column(String(80), nullable=False)
    detalle_json: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    usuario: Mapped[str] = mapped_column(String(200), nullable=False, default="sistema", server_default="sistema")
    creado_en: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("CURRENT_TIMESTAMP")
    )

    solicitud: Mapped["CreditoSolicitud"] = relationship("CreditoSolicitud", back_populates="historial")
