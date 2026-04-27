# models/finanzas/plan_cuentas.py
# -*- coding: utf-8 -*-
from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from db.base_class import Base


class PlanCuenta(Base):
    __tablename__ = "plan_cuenta"
    __table_args__ = (
        Index("ix_fin_plan_cuenta_codigo", "codigo", unique=True),
        Index("ix_fin_plan_cuenta_padre", "cuenta_padre_id"),
        Index("ix_fin_plan_cuenta_tipo", "tipo"),
        Index("ix_fin_plan_cuenta_clasificacion", "clasificacion"),
        Index("ix_fin_plan_cuenta_estado", "estado"),
        CheckConstraint(
            "tipo IN ('ACTIVO', 'PASIVO', 'PATRIMONIO', 'INGRESO', 'COSTO', 'GASTO', 'ORDEN')",
            name="chk_fin_plan_cuenta_tipo",
        ),
        CheckConstraint(
            "naturaleza IN ('DEUDORA', 'ACREEDORA')",
            name="chk_fin_plan_cuenta_naturaleza",
        ),
        CheckConstraint(
            "estado IN ('ACTIVO', 'INACTIVO')",
            name="chk_fin_plan_cuenta_estado",
        ),
        {"schema": "fin"},
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    codigo: Mapped[str] = mapped_column(String(30), nullable=False, unique=True)
    nombre: Mapped[str] = mapped_column(String(180), nullable=False)
    nivel: Mapped[int] = mapped_column(Integer, nullable=False, default=1)

    cuenta_padre_id: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey("fin.plan_cuenta.id", ondelete="RESTRICT"),
        nullable=True,
    )

    tipo: Mapped[str] = mapped_column(String(30), nullable=False)
    clasificacion: Mapped[str] = mapped_column(String(50), nullable=False)
    naturaleza: Mapped[str] = mapped_column(String(20), nullable=False)

    acepta_movimiento: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    requiere_centro_costo: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    estado: Mapped[str] = mapped_column(String(20), nullable=False, default="ACTIVO")
    descripcion: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    padre: Mapped["PlanCuenta | None"] = relationship(
        "PlanCuenta",
        remote_side=[id],
        back_populates="hijos",
    )

    hijos: Mapped[list["PlanCuenta"]] = relationship(
        "PlanCuenta",
        back_populates="padre",
        cascade="save-update, merge",
    )