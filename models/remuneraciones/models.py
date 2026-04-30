# models/remuneraciones/models.py
# -*- coding: utf-8 -*-
"""Nómina / remuneraciones — periodos, contratos laborales, conceptos e ítems."""
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
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from db.base_class import Base

if TYPE_CHECKING:
    from models.fondos_rendir.empleado import Empleado
    from models.fondos_rendir.vehiculo_transporte import VehiculoTransporte
    from models.finanzas.compras_finanzas import CentroCosto

FIN_SCHEMA = "fin"

ESTADOS_PERIODO_REMUNERACION = (
    "BORRADOR",
    "CALCULADO",
    "EN_REVISION",
    "APROBADO_RRHH",
    "APROBADO_FINANZAS",
    "CERRADO",
    "PAGADO",
    "ANULADO",
)

ESTADOS_CONTRATO_LABORAL = ("VIGENTE", "TERMINADO")


class ContratoLaboral(Base):
    """Contrato laboral y remuneración fija base (MVP en ERP, no proveedor externo)."""

    __tablename__ = "contratos_laborales"

    __table_args__ = (
        Index("ix_contratos_laborales_empleado", "empleado_id"),
        Index("ix_contratos_laborales_vigencia", "estado", "fecha_inicio"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    empleado_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("empleados.id", ondelete="RESTRICT"),
        nullable=False,
    )
    fecha_inicio: Mapped[date] = mapped_column(Date, nullable=False)
    fecha_fin: Mapped[date | None] = mapped_column(Date, nullable=True)
    tipo_contrato: Mapped[str | None] = mapped_column(String(40), nullable=True)
    jornada: Mapped[str | None] = mapped_column(String(40), nullable=True)
    sueldo_base: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    centro_costo_id: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey(f"{FIN_SCHEMA}.centro_costo.id", ondelete="SET NULL"),
        nullable=True,
    )
    estado: Mapped[str] = mapped_column(String(20), nullable=False, default="VIGENTE")
    observaciones: Mapped[str | None] = mapped_column(Text, nullable=True)

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

    empleado: Mapped["Empleado"] = relationship("Empleado", back_populates="contratos_laborales")
    centro_costo: Mapped["CentroCosto | None"] = relationship(
        "CentroCosto",
        foreign_keys=[centro_costo_id],
    )
    detalles_remuneracion: Mapped[list["DetalleRemuneracion"]] = relationship(
        "DetalleRemuneracion",
        back_populates="contrato_laboral",
    )


class PeriodoRemuneracion(Base):
    __tablename__ = "periodos_remuneracion"

    __table_args__ = (
        UniqueConstraint("anio", "mes", name="uq_periodos_remuneracion_anio_mes"),
        Index("ix_periodos_remuneracion_estado", "estado"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    anio: Mapped[int] = mapped_column(Integer, nullable=False)
    mes: Mapped[int] = mapped_column(Integer, nullable=False)
    fecha_inicio: Mapped[date] = mapped_column(Date, nullable=False)
    fecha_fin: Mapped[date] = mapped_column(Date, nullable=False)
    estado: Mapped[str] = mapped_column(String(32), nullable=False, default="BORRADOR")

    fecha_calculo: Mapped[datetime | None] = mapped_column(DateTime(timezone=False), nullable=True)
    fecha_cierre: Mapped[datetime | None] = mapped_column(DateTime(timezone=False), nullable=True)
    fecha_pago: Mapped[datetime | None] = mapped_column(DateTime(timezone=False), nullable=True)

    usuario_creador_id: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey("auth_usuarios.id", ondelete="SET NULL"),
        nullable=True,
    )
    usuario_aprobador_rrhh_id: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey("auth_usuarios.id", ondelete="SET NULL"),
        nullable=True,
    )
    usuario_aprobador_finanzas_id: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey("auth_usuarios.id", ondelete="SET NULL"),
        nullable=True,
    )
    observaciones: Mapped[str | None] = mapped_column(Text, nullable=True)

    asiento_pago_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)

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

    detalles: Mapped[list["DetalleRemuneracion"]] = relationship(
        "DetalleRemuneracion",
        back_populates="periodo",
        cascade="all, delete-orphan",
    )


class ConceptoRemuneracion(Base):
    __tablename__ = "conceptos_remuneracion"

    __table_args__ = (
        UniqueConstraint("codigo", name="uq_conceptos_remuneracion_codigo"),
        Index("ix_conceptos_remuneracion_activo", "activo"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    codigo: Mapped[str] = mapped_column(String(40), nullable=False)
    nombre: Mapped[str] = mapped_column(String(160), nullable=False)
    descripcion: Mapped[str | None] = mapped_column(Text, nullable=True)
    tipo: Mapped[str] = mapped_column(String(40), nullable=False)
    imponible: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="false")
    tributable: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="false")
    legal: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="false")
    afecta_liquido: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default="true")
    formula: Mapped[str | None] = mapped_column(String(500), nullable=True)
    regla_calculo: Mapped[str | None] = mapped_column(String(80), nullable=True)
    origen_catalogo: Mapped[str | None] = mapped_column("origen", String(40), nullable=True)
    activo: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default="true")
    orden: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")

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

    items: Mapped[list["ItemRemuneracion"]] = relationship(
        "ItemRemuneracion",
        back_populates="concepto",
    )


class DetalleRemuneracion(Base):
    __tablename__ = "detalle_remuneraciones"

    __table_args__ = (
        UniqueConstraint("periodo_remuneracion_id", "empleado_id", name="uq_detalle_periodo_empleado"),
        Index("ix_detalle_remuneraciones_periodo", "periodo_remuneracion_id"),
        Index("ix_detalle_remuneraciones_empleado", "empleado_id"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    periodo_remuneracion_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("periodos_remuneracion.id", ondelete="CASCADE"),
        nullable=False,
    )
    empleado_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("empleados.id", ondelete="RESTRICT"),
        nullable=False,
    )
    contrato_laboral_id: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey("contratos_laborales.id", ondelete="SET NULL"),
        nullable=True,
    )
    cargo_snapshot: Mapped[str | None] = mapped_column(String(120), nullable=True)
    centro_costo_id: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey(f"{FIN_SCHEMA}.centro_costo.id", ondelete="SET NULL"),
        nullable=True,
    )
    camion_id: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey("vehiculos_transporte.id", ondelete="SET NULL"),
        nullable=True,
    )

    dias_trabajados: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    dias_ausencia: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    horas_ordinarias: Mapped[Decimal] = mapped_column(
        Numeric(12, 2), nullable=False, default=Decimal("0"), server_default="0"
    )
    horas_extras: Mapped[Decimal] = mapped_column(
        Numeric(12, 2), nullable=False, default=Decimal("0"), server_default="0"
    )
    horas_nocturnas: Mapped[Decimal] = mapped_column(
        Numeric(12, 2), nullable=False, default=Decimal("0"), server_default="0"
    )

    total_haberes_imponibles: Mapped[Decimal] = mapped_column(
        Numeric(18, 2), nullable=False, default=Decimal("0"), server_default="0"
    )
    total_haberes_no_imponibles: Mapped[Decimal] = mapped_column(
        Numeric(18, 2), nullable=False, default=Decimal("0"), server_default="0"
    )
    total_descuentos_legales: Mapped[Decimal] = mapped_column(
        Numeric(18, 2), nullable=False, default=Decimal("0"), server_default="0"
    )
    total_otros_descuentos: Mapped[Decimal] = mapped_column(
        Numeric(18, 2), nullable=False, default=Decimal("0"), server_default="0"
    )
    total_aportes_empresa: Mapped[Decimal] = mapped_column(
        Numeric(18, 2), nullable=False, default=Decimal("0"), server_default="0"
    )
    liquido_a_pagar: Mapped[Decimal] = mapped_column(
        Numeric(18, 2), nullable=False, default=Decimal("0"), server_default="0"
    )
    estado: Mapped[str] = mapped_column(String(24), nullable=False, default="CALCULADO")
    observaciones: Mapped[str | None] = mapped_column(Text, nullable=True)

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

    periodo: Mapped["PeriodoRemuneracion"] = relationship("PeriodoRemuneracion", back_populates="detalles")
    empleado: Mapped["Empleado"] = relationship("Empleado", back_populates="detalles_remuneracion")
    contrato_laboral: Mapped["ContratoLaboral | None"] = relationship(
        "ContratoLaboral",
        back_populates="detalles_remuneracion",
    )
    centro_costo: Mapped["CentroCosto | None"] = relationship(
        "CentroCosto",
        foreign_keys=[centro_costo_id],
    )
    camion: Mapped["VehiculoTransporte | None"] = relationship("VehiculoTransporte")
    items: Mapped[list["ItemRemuneracion"]] = relationship(
        "ItemRemuneracion",
        back_populates="detalle",
        cascade="all, delete-orphan",
    )


class ItemRemuneracion(Base):
    __tablename__ = "items_remuneracion"

    __table_args__ = (
        Index("ix_items_remuneracion_detalle", "detalle_remuneracion_id"),
        Index("ix_items_remuneracion_concepto", "concepto_remuneracion_id"),
        Index("ix_items_remuneracion_ref", "referencia_tipo", "referencia_id"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    detalle_remuneracion_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("detalle_remuneraciones.id", ondelete="CASCADE"),
        nullable=False,
    )
    concepto_remuneracion_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("conceptos_remuneracion.id", ondelete="RESTRICT"),
        nullable=False,
    )
    cantidad: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False, default=Decimal("1"))
    valor_unitario: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False, default=Decimal("0"))
    monto_total: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)

    origen: Mapped[str | None] = mapped_column(String(40), nullable=True)
    referencia_tipo: Mapped[str | None] = mapped_column(String(40), nullable=True)
    referencia_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)

    es_ajuste_manual: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="false")
    usuario_ajuste_id: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey("auth_usuarios.id", ondelete="SET NULL"),
        nullable=True,
    )
    motivo_ajuste: Mapped[str | None] = mapped_column(Text, nullable=True)
    observaciones: Mapped[str | None] = mapped_column(Text, nullable=True)

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

    detalle: Mapped["DetalleRemuneracion"] = relationship("DetalleRemuneracion", back_populates="items")
    concepto: Mapped["ConceptoRemuneracion"] = relationship("ConceptoRemuneracion", back_populates="items")


class RemuneracionParametro(Base):
    """Parámetros globales de cálculo (ej. % bono sobre valor_flete de viajes cerrados)."""

    __tablename__ = "remuneracion_parametros"

    __table_args__ = (UniqueConstraint("clave", name="uq_remuneracion_parametros_clave"),)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    clave: Mapped[str] = mapped_column(String(80), nullable=False)
    valor_numerico: Mapped[Decimal | None] = mapped_column(Numeric(18, 6), nullable=True)
    valor_texto: Mapped[str | None] = mapped_column(String(500), nullable=True)
    descripcion: Mapped[str | None] = mapped_column(String(255), nullable=True)

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=False),
        nullable=False,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
        server_default=func.now(),
    )
