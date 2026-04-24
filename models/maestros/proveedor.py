# models/maestros/proveedor.py
# -*- coding: utf-8 -*-
from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import (
    BigInteger,
    Boolean,
    Computed,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from db.base_class import Base

if TYPE_CHECKING:
    from models.finanzas.compras_finanzas import APPago, APDocumento, ProveedorFin


class Proveedor(Base):
    __tablename__ = "proveedor"
    __table_args__ = (
        Index("ix_proveedor_razon_social", "razon_social"),
        UniqueConstraint("rut_normalizado", name="ux_proveedor_rut_normalizado"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    rut: Mapped[str] = mapped_column(String(20), nullable=False)

    # IMPORTANTE:
    # En tu BD esta columna es GENERATED ALWAYS, por lo tanto
    # no debe enviarse en INSERT/UPDATE.
    rut_normalizado: Mapped[str | None] = mapped_column(
        String(20),
        Computed("public.fn_normalizar_rut(rut)", persisted=True),
        nullable=True,
    )

    razon_social: Mapped[str] = mapped_column(String(180), nullable=False)
    nombre_fantasia: Mapped[str | None] = mapped_column(String(180), nullable=True)
    giro: Mapped[str | None] = mapped_column(String(180), nullable=True)
    email: Mapped[str | None] = mapped_column(String(180), nullable=True)
    telefono: Mapped[str | None] = mapped_column(String(50), nullable=True)
    sitio_web: Mapped[str | None] = mapped_column(String(180), nullable=True)
    condicion_pago_dias: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=30,
        server_default=text("30"),
    )
    limite_credito: Mapped[Decimal] = mapped_column(
        Numeric(18, 2),
        nullable=False,
        default=Decimal("0.00"),
        server_default=text("0"),
    )
    activo: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
        server_default=text("true"),
    )
    notas: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    bancos: Mapped[list["ProveedorBanco"]] = relationship(
        "ProveedorBanco",
        back_populates="proveedor",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )

    contactos: Mapped[list["ProveedorContacto"]] = relationship(
        "ProveedorContacto",
        back_populates="proveedor",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )

    direcciones: Mapped[list["ProveedorDireccion"]] = relationship(
        "ProveedorDireccion",
        back_populates="proveedor",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )

    finanzas: Mapped["ProveedorFin | None"] = relationship(
        "ProveedorFin",
        back_populates="proveedor",
        uselist=False,
        passive_deletes=True,
    )

    documentos_ap: Mapped[list["APDocumento"]] = relationship(
        "APDocumento",
        back_populates="proveedor",
    )

    pagos_ap: Mapped[list["APPago"]] = relationship(
        "APPago",
        back_populates="proveedor",
    )


class ProveedorBanco(Base):
    __tablename__ = "proveedor_banco"
    __table_args__ = (
        Index("ix_prov_banco_proveedor", "proveedor_id"),
        UniqueConstraint(
            "proveedor_id",
            "banco",
            "tipo_cuenta",
            "numero_cuenta",
            name="ux_prov_banco_unique",
        ),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    proveedor_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("proveedor.id", ondelete="CASCADE"),
        nullable=False,
    )
    banco: Mapped[str] = mapped_column(String(120), nullable=False)
    tipo_cuenta: Mapped[str] = mapped_column(String(60), nullable=False)
    numero_cuenta: Mapped[str] = mapped_column(String(60), nullable=False)
    titular: Mapped[str | None] = mapped_column(String(180), nullable=True)
    rut_titular: Mapped[str | None] = mapped_column(String(20), nullable=True)
    email_pago: Mapped[str | None] = mapped_column(String(180), nullable=True)
    es_principal: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        server_default=text("false"),
    )
    activo: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
        server_default=text("true"),
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    proveedor: Mapped["Proveedor"] = relationship(
        "Proveedor",
        back_populates="bancos",
    )

    pagos_ap: Mapped[list["APPago"]] = relationship(
        "APPago",
        back_populates="banco_proveedor",
    )


class ProveedorContacto(Base):
    __tablename__ = "proveedor_contacto"
    __table_args__ = (
        Index("ix_prov_contacto_proveedor", "proveedor_id"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    proveedor_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("proveedor.id", ondelete="CASCADE"),
        nullable=False,
    )
    nombre: Mapped[str] = mapped_column(String(120), nullable=False)
    cargo: Mapped[str | None] = mapped_column(String(120), nullable=True)
    email: Mapped[str | None] = mapped_column(String(180), nullable=True)
    telefono: Mapped[str | None] = mapped_column(String(50), nullable=True)
    es_principal: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        server_default=text("false"),
    )
    activo: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
        server_default=text("true"),
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    proveedor: Mapped["Proveedor"] = relationship(
        "Proveedor",
        back_populates="contactos",
    )


class ProveedorDireccion(Base):
    __tablename__ = "proveedor_direccion"
    __table_args__ = (
        Index("ix_prov_direccion_proveedor", "proveedor_id"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    proveedor_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("proveedor.id", ondelete="CASCADE"),
        nullable=False,
    )
    linea1: Mapped[str] = mapped_column(String(180), nullable=False)
    linea2: Mapped[str | None] = mapped_column(String(180), nullable=True)
    comuna: Mapped[str | None] = mapped_column(String(120), nullable=True)
    ciudad: Mapped[str | None] = mapped_column(String(120), nullable=True)
    region: Mapped[str | None] = mapped_column(String(120), nullable=True)
    pais: Mapped[str] = mapped_column(
        String(120),
        nullable=False,
        default="Chile",
        server_default=text("'Chile'"),
    )
    codigo_postal: Mapped[str | None] = mapped_column(String(20), nullable=True)
    es_principal: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        server_default=text("false"),
    )
    activo: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
        server_default=text("true"),
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    proveedor: Mapped["Proveedor"] = relationship(
        "Proveedor",
        back_populates="direcciones",
    )