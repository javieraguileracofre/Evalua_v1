# models/auth/login_attempt.py
# -*- coding: utf-8 -*-
"""Intentos de login fallidos. Se guarda HMAC del correo y de la IP, nunca el valor en claro."""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import BigInteger, DateTime, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from db.base_class import Base


class LoginAttempt(Base):
    __tablename__ = "auth_login_attempts"

    id: Mapped[int] = mapped_column(
        BigInteger().with_variant(Integer, "sqlite"),
        primary_key=True,
        autoincrement=True,
    )
    email_hmac: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    ip_hmac: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=False),
        nullable=False,
        default=datetime.utcnow,
        server_default=func.now(),
    )
