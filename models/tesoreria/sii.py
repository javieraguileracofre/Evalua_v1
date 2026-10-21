# models/tesoreria/sii.py
# -*- coding: utf-8 -*-
"""Credencial, ejecución y evidencia de archivos del Registro de Compras y Ventas."""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    SmallInteger,
    String,
    Text,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from db.base_class import Base

_SCHEMA = "fin"


class SiiCredencial(Base):
    __tablename__ = "sii_credencial"
    __table_args__ = (
        CheckConstraint("id = 1", name="ck_sii_credencial_singleton"),
        CheckConstraint("estado IN ('INCOMPLETA', 'CONFIGURADA')", name="ck_sii_credencial_estado"),
        {"schema": _SCHEMA},
    )

    id: Mapped[int] = mapped_column(SmallInteger, primary_key=True, default=1)
    rut: Mapped[str] = mapped_column(String(20), nullable=False)
    usuario: Mapped[str] = mapped_column(String(32), nullable=False)
    secreto_cifrado: Mapped[str] = mapped_column(Text, nullable=False, default="")
    estado: Mapped[str] = mapped_column(String(32), nullable=False, default="INCOMPLETA")
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )
    updated_by: Mapped[int | None] = mapped_column(BigInteger, nullable=True)


class SiiEjecucion(Base):
    __tablename__ = "sii_ejecucion"
    __table_args__ = (
        CheckConstraint("tipo_integracion = 'SII'", name="ck_sii_ejecucion_tipo"),
        CheckConstraint("periodo_mes BETWEEN 1 AND 12", name="ck_sii_ejecucion_mes"),
        CheckConstraint(
            "estado IN ("
            "'PENDIENTE','EN_PROCESO','DESCARGANDO_COMPRAS','DESCARGANDO_VENTAS',"
            "'PROCESANDO_COMPRAS','PROCESANDO_VENTAS','IMPORTANDO','COMPLETADO',"
            "'COMPLETADO_CON_OBSERVACIONES','REQUIERE_INTERVENCION_USUARIO','ERROR'"
            ")",
            name="ck_sii_ejecucion_estado",
        ),
        Index(
            "ux_sii_ejecucion_activa",
            "company_id",
            unique=True,
            postgresql_where=text(
                "estado IN ("
                "'PENDIENTE','EN_PROCESO','DESCARGANDO_COMPRAS','DESCARGANDO_VENTAS',"
                "'PROCESANDO_COMPRAS','PROCESANDO_VENTAS','IMPORTANDO'"
                ")"
            ),
        ),
        {"schema": _SCHEMA},
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    company_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    actor_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    actor_email: Mapped[str] = mapped_column(
        String(254), nullable=False, default="", server_default=text("''")
    )
    periodo_anio: Mapped[int] = mapped_column(Integer, nullable=False)
    periodo_mes: Mapped[int] = mapped_column(Integer, nullable=False)
    tipo_integracion: Mapped[str] = mapped_column(
        String(16), nullable=False, default="SII", server_default=text("'SII'")
    )
    estado: Mapped[str] = mapped_column(String(40), nullable=False)
    pasos: Mapped[str] = mapped_column(Text, nullable=False, default="[]", server_default=text("'[]'"))
    inicio_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )
    fin_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    compras_encontrados: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default=text("0"))
    compras_importados: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default=text("0"))
    compras_omitidos: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default=text("0"))
    compras_errores: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default=text("0"))
    ventas_encontrados: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default=text("0"))
    ventas_importados: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default=text("0"))
    ventas_omitidos: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default=text("0"))
    ventas_errores: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default=text("0"))
    error_publico: Mapped[str | None] = mapped_column(Text, nullable=True)
    error_tecnico: Mapped[str | None] = mapped_column(Text, nullable=True)


class SiiArchivo(Base):
    __tablename__ = "sii_archivo"
    __table_args__ = (
        CheckConstraint("tipo IN ('COMPRAS', 'VENTAS')", name="ck_sii_archivo_tipo"),
        Index("ix_sii_archivo_hash", "company_id", "sha256"),
        {"schema": _SCHEMA},
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    ejecucion_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey(f"{_SCHEMA}.sii_ejecucion.id", ondelete="CASCADE"), nullable=False
    )
    tipo: Mapped[str] = mapped_column(String(16), nullable=False)
    nombre_archivo: Mapped[str] = mapped_column(String(255), nullable=False)
    periodo_anio: Mapped[int] = mapped_column(Integer, nullable=False)
    periodo_mes: Mapped[int] = mapped_column(Integer, nullable=False)
    company_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    descargado_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )
    sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    tamano_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False)
    ruta: Mapped[str] = mapped_column(String(500), nullable=False)
