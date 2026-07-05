# models/auth/modulo_visible.py
# -*- coding: utf-8 -*-
"""Módulos visibles en el menú por usuario."""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import BigInteger, DateTime, ForeignKey, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from db.base_class import Base


class UsuarioModuloVisible(Base):
    __tablename__ = "auth_usuario_modulo_visible"

    usuario_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("auth_usuarios.id", ondelete="CASCADE"),
        primary_key=True,
    )
    module_key: Mapped[str] = mapped_column(String(32), primary_key=True)
    assigned_by_id: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey("auth_usuarios.id", ondelete="SET NULL"),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=False),
        nullable=False,
        default=datetime.utcnow,
        server_default=func.now(),
    )

    usuario: Mapped["Usuario"] = relationship(  # noqa: F821
        "Usuario",
        back_populates="modulos_visibles",
        foreign_keys=[usuario_id],
    )
