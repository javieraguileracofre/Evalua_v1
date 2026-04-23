# models/auth/usuario.py
# -*- coding: utf-8 -*-
"""Usuarios del portal corporativo y roles (RBAC base)."""
from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import BigInteger, Boolean, Column, DateTime, ForeignKey, String, Table, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from db.base_class import Base

if TYPE_CHECKING:
    pass

usuario_rol = Table(
    "auth_usuario_rol",
    Base.metadata,
    Column(
        "usuario_id",
        BigInteger,
        ForeignKey("auth_usuarios.id", ondelete="CASCADE"),
        primary_key=True,
    ),
    Column(
        "rol_id",
        BigInteger,
        ForeignKey("auth_roles.id", ondelete="CASCADE"),
        primary_key=True,
    ),
)


class Rol(Base):
    __tablename__ = "auth_roles"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    codigo: Mapped[str] = mapped_column(String(32), unique=True, nullable=False, index=True)
    nombre: Mapped[str] = mapped_column(String(120), nullable=False)
    descripcion: Mapped[str | None] = mapped_column(Text, nullable=True)

    usuarios: Mapped[list["Usuario"]] = relationship(
        secondary=usuario_rol,
        back_populates="roles",
    )


class Usuario(Base):
    __tablename__ = "auth_usuarios"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    email: Mapped[str] = mapped_column(String(254), unique=True, nullable=False, index=True)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    nombre_completo: Mapped[str] = mapped_column(String(200), nullable=False)
    activo: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default="true")

    ultimo_acceso: Mapped[datetime | None] = mapped_column(DateTime(timezone=False), nullable=True)
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

    roles: Mapped[list[Rol]] = relationship(
        secondary=usuario_rol,
        back_populates="usuarios",
    )
