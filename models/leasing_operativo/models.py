# models/leasing_operativo/models.py
# -*- coding: utf-8 -*-
from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import TYPE_CHECKING, Any

from sqlalchemy import BigInteger, Boolean, Date, DateTime, ForeignKey, Integer, Numeric, String, Text, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from db.base_class import Base

if TYPE_CHECKING:
    from models.maestros.cliente import Cliente


class LeasingOpTipoActivo(Base):
    __tablename__ = "leasing_op_tipo_activo"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    codigo: Mapped[str] = mapped_column(String(40), nullable=False, unique=True)
    nombre: Mapped[str] = mapped_column(String(160), nullable=False)
    residual_base_pct: Mapped[Decimal] = mapped_column(Numeric(7, 4), nullable=False, default=Decimal("15"))
    residual_max_pct: Mapped[Decimal] = mapped_column(Numeric(7, 4), nullable=False, default=Decimal("45"))
    sector: Mapped[str | None] = mapped_column(String(120))
    liquidez_factor: Mapped[Decimal] = mapped_column(Numeric(9, 6), nullable=False, default=Decimal("1"))
    obsolescencia_factor: Mapped[Decimal] = mapped_column(Numeric(9, 6), nullable=False, default=Decimal("1"))
    desgaste_km_factor: Mapped[Decimal] = mapped_column(Numeric(12, 8), nullable=False, default=Decimal("0.0001"))
    desgaste_hora_factor: Mapped[Decimal] = mapped_column(Numeric(12, 8), nullable=False, default=Decimal("0.0005"))
    haircut_residual_pct: Mapped[Decimal] = mapped_column(Numeric(7, 4), nullable=False, default=Decimal("5"))
    activo: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default=text("true"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("CURRENT_TIMESTAMP"))

    plantillas: Mapped[list["LeasingOpCostoPlantilla"]] = relationship(
        "LeasingOpCostoPlantilla", back_populates="tipo", cascade="all, delete-orphan"
    )
    simulaciones: Mapped[list["LeasingOpSimulacion"]] = relationship("LeasingOpSimulacion", back_populates="tipo")


class LeasingOpPolitica(Base):
    __tablename__ = "leasing_op_politica"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    clave: Mapped[str] = mapped_column(String(100), nullable=False, unique=True)
    valor_json: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    descripcion: Mapped[str | None] = mapped_column(Text)
    activo: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default=text("true"))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("CURRENT_TIMESTAMP"))


class LeasingOpCostoPlantilla(Base):
    __tablename__ = "leasing_op_costo_plantilla"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    tipo_activo_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("leasing_op_tipo_activo.id", ondelete="CASCADE"), nullable=False)
    codigo: Mapped[str] = mapped_column(String(60), nullable=False)
    descripcion: Mapped[str] = mapped_column(String(200), nullable=False)
    periodicidad: Mapped[str] = mapped_column(String(20), nullable=False, default="MENSUAL", server_default="MENSUAL")
    monto_mensual_equiv: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False, default=Decimal("0"))
    orden: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")

    tipo: Mapped["LeasingOpTipoActivo"] = relationship("LeasingOpTipoActivo", back_populates="plantillas")


class LeasingOpSimulacion(Base):
    __tablename__ = "leasing_op_simulacion"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    codigo: Mapped[str | None] = mapped_column(String(48), unique=True, nullable=True)
    cliente_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("clientes.id", ondelete="SET NULL"), nullable=True, index=True)
    tipo_activo_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("leasing_op_tipo_activo.id"), nullable=False, index=True)
    nombre: Mapped[str] = mapped_column(String(200), nullable=False, default="", server_default="")
    plazo_meses: Mapped[int] = mapped_column(Integer, nullable=False)
    escenario: Mapped[str] = mapped_column(String(24), nullable=False, default="BASE", server_default="BASE")
    metodo_pricing: Mapped[str] = mapped_column(String(24), nullable=False, default="COSTO_SPREAD", server_default="COSTO_SPREAD")
    margen_pct: Mapped[Decimal | None] = mapped_column(Numeric(9, 6))
    spread_pct: Mapped[Decimal | None] = mapped_column(Numeric(9, 6))
    tir_objetivo_anual: Mapped[Decimal | None] = mapped_column(Numeric(9, 6))
    inputs_json: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, server_default=text("'{}'::jsonb"))
    result_json: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, server_default=text("'{}'::jsonb"))
    decision_codigo: Mapped[str] = mapped_column(String(20), nullable=False, default="PENDIENTE", server_default="PENDIENTE")
    decision_detalle: Mapped[str] = mapped_column(Text, nullable=False, default="", server_default="")
    estado: Mapped[str] = mapped_column(String(24), nullable=False, default="BORRADOR", server_default="BORRADOR")
    creado_en: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("CURRENT_TIMESTAMP"))
    actualizado_en: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("CURRENT_TIMESTAMP"))

    tipo: Mapped["LeasingOpTipoActivo"] = relationship("LeasingOpTipoActivo", back_populates="simulaciones")
    cliente: Mapped["Cliente | None"] = relationship("Cliente", lazy="joined")
    comites: Mapped[list["LeasingOpComite"]] = relationship(
        "LeasingOpComite", back_populates="simulacion", cascade="all, delete-orphan"
    )
    historial: Mapped[list["LeasingOpHistorial"]] = relationship(
        "LeasingOpHistorial", back_populates="simulacion", cascade="all, delete-orphan"
    )
    contrato: Mapped["LeasingOpContrato | None"] = relationship(
        "LeasingOpContrato", back_populates="simulacion", uselist=False
    )


class LeasingOpContrato(Base):
    __tablename__ = "leasing_op_contrato"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    simulacion_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("leasing_op_simulacion.id", ondelete="RESTRICT"), nullable=False, unique=True, index=True
    )
    codigo: Mapped[str] = mapped_column(String(48), nullable=False, unique=True)
    plazo_meses: Mapped[int] = mapped_column(Integer, nullable=False)
    renta_mensual: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False)
    fecha_inicio: Mapped[date] = mapped_column(Date, nullable=False, server_default=text("CURRENT_DATE"))
    estado: Mapped[str] = mapped_column(String(24), nullable=False, default="VIGENTE", server_default="VIGENTE")
    creado_en: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("CURRENT_TIMESTAMP"))

    simulacion: Mapped["LeasingOpSimulacion"] = relationship("LeasingOpSimulacion", back_populates="contrato")
    cuotas: Mapped[list["LeasingOpCuota"]] = relationship(
        "LeasingOpCuota", back_populates="contrato", cascade="all, delete-orphan", order_by="LeasingOpCuota.nro"
    )


class LeasingOpCuota(Base):
    __tablename__ = "leasing_op_cuota"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    contrato_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("leasing_op_contrato.id", ondelete="CASCADE"), nullable=False, index=True)
    nro: Mapped[int] = mapped_column(Integer, nullable=False)
    fecha_vencimiento: Mapped[date] = mapped_column(Date, nullable=False)
    monto_renta: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False)
    estado: Mapped[str] = mapped_column(String(20), nullable=False, default="PENDIENTE", server_default="PENDIENTE")

    contrato: Mapped["LeasingOpContrato"] = relationship("LeasingOpContrato", back_populates="cuotas")


class LeasingOpActivoFijo(Base):
    __tablename__ = "leasing_op_activo_fijo"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    codigo: Mapped[str] = mapped_column(String(48), nullable=False, unique=True)
    tipo_activo_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("leasing_op_tipo_activo.id", ondelete="SET NULL"), nullable=True, index=True)
    marca: Mapped[str] = mapped_column(String(120), nullable=False, default="", server_default="")
    modelo: Mapped[str] = mapped_column(String(120), nullable=False, default="", server_default="")
    anio: Mapped[int] = mapped_column(Integer, nullable=False)
    vin_serie: Mapped[str | None] = mapped_column(String(120))
    fecha_compra: Mapped[date] = mapped_column(Date, nullable=False, server_default=text("CURRENT_DATE"))
    costo_compra: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False)
    valor_residual_esperado: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False, default=Decimal("0"), server_default="0")
    vida_util_meses_sii: Mapped[int] = mapped_column(Integer, nullable=False, default=60, server_default="60")
    depreciacion_mensual_sii: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False, default=Decimal("0"), server_default="0")
    valor_libro: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False)
    estado: Mapped[str] = mapped_column(String(24), nullable=False, default="DISPONIBLE", server_default="DISPONIBLE")
    creado_en: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("CURRENT_TIMESTAMP"))

    tipo: Mapped["LeasingOpTipoActivo | None"] = relationship("LeasingOpTipoActivo")
    depreciaciones: Mapped[list["LeasingOpActivoDepreciacion"]] = relationship(
        "LeasingOpActivoDepreciacion", back_populates="activo", cascade="all, delete-orphan"
    )


class LeasingOpActivoDepreciacion(Base):
    __tablename__ = "leasing_op_activo_depreciacion"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    activo_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("leasing_op_activo_fijo.id", ondelete="CASCADE"), nullable=False, index=True)
    periodo_yyyymm: Mapped[str] = mapped_column(String(6), nullable=False)
    depreciacion_mes: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False)
    valor_libro_cierre: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False)
    asiento_ref: Mapped[str | None] = mapped_column(String(80))
    creado_en: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("CURRENT_TIMESTAMP"))

    activo: Mapped["LeasingOpActivoFijo"] = relationship("LeasingOpActivoFijo", back_populates="depreciaciones")


class LeasingOpParametroTipo(Base):
    __tablename__ = "leasing_op_param_tipo"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    tipo_activo_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("leasing_op_tipo_activo.id", ondelete="CASCADE"), nullable=False, unique=True, index=True
    )
    moneda: Mapped[str] = mapped_column(String(8), nullable=False, default="CLP", server_default="CLP")
    iva_pct: Mapped[Decimal] = mapped_column(Numeric(7, 4), nullable=False, default=Decimal("19"), server_default="19")
    plazo_default: Mapped[int] = mapped_column(Integer, nullable=False, default=36, server_default="36")
    spread_default_pct: Mapped[Decimal] = mapped_column(Numeric(9, 6), nullable=False, default=Decimal("8"), server_default="8")
    margen_default_pct: Mapped[Decimal] = mapped_column(Numeric(9, 6), nullable=False, default=Decimal("12"), server_default="12")
    tir_default_pct: Mapped[Decimal] = mapped_column(Numeric(9, 6), nullable=False, default=Decimal("14"), server_default="14")
    perfil_json: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, server_default=text("'{}'::jsonb"))
    actualizado_en: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("CURRENT_TIMESTAMP"))

    tipo: Mapped["LeasingOpTipoActivo"] = relationship("LeasingOpTipoActivo")


class LeasingOpComite(Base):
    __tablename__ = "leasing_op_comite"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    simulacion_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("leasing_op_simulacion.id", ondelete="CASCADE"), nullable=False, index=True)
    estado: Mapped[str] = mapped_column(String(20), nullable=False, default="PENDIENTE", server_default="PENDIENTE")
    resumen: Mapped[str] = mapped_column(Text, nullable=False, default="", server_default="")
    decision: Mapped[str | None] = mapped_column(String(30))
    comentario: Mapped[str] = mapped_column(Text, nullable=False, default="", server_default="")
    analista: Mapped[str] = mapped_column(String(200), nullable=False, default="sistema", server_default="sistema")
    fecha_apertura: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("CURRENT_TIMESTAMP"))
    fecha_cierre: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    simulacion: Mapped["LeasingOpSimulacion"] = relationship("LeasingOpSimulacion", back_populates="comites")


class LeasingOpHistorial(Base):
    __tablename__ = "leasing_op_historial"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    simulacion_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("leasing_op_simulacion.id", ondelete="CASCADE"), nullable=False, index=True)
    evento: Mapped[str] = mapped_column(String(80), nullable=False)
    detalle_json: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    usuario: Mapped[str] = mapped_column(String(200), nullable=False, default="sistema", server_default="sistema")
    creado_en: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("CURRENT_TIMESTAMP"))

    simulacion: Mapped["LeasingOpSimulacion"] = relationship("LeasingOpSimulacion", back_populates="historial")
