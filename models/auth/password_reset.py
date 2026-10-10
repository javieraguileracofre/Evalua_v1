# models/auth/password_reset.py
# -*- coding: utf-8 -*-
"""Códigos de recuperación de contraseña (solo hash, un solo uso, expiración corta)."""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import BigInteger, DateTime, ForeignKey, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from db.base_class import Base


class PasswordResetCode(Base):
    __tablename__ = "auth_password_reset_codes"

    id: Mapped[int] = mapped_column(
        BigInteger().with_variant(Integer, "sqlite"),
        primary_key=True,
        autoincrement=True,
    )
    user_id: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey("auth_usuarios.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    email_hmac: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    code_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=False), nullable=False, index=True)
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=False), nullable=True)
    invalidated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=False), nullable=True)
    failed_attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    request_ip_hmac: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=False),
        nullable=False,
        default=datetime.utcnow,
        server_default=func.now(),
    )

    usuario: Mapped["Usuario | None"] = relationship(  # noqa: F821
        "Usuario",
        foreign_keys=[user_id],
    )
