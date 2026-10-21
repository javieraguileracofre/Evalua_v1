# models/comunicaciones/mail_account.py
# -*- coding: utf-8 -*-
"""Cuentas SMTP, canales de envío y validaciones."""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import BigInteger, Boolean, DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from db.base_class import Base

_PK = BigInteger().with_variant(Integer, "sqlite")


class MailAccount(Base):
    __tablename__ = "mail_accounts"

    id: Mapped[int] = mapped_column(_PK, primary_key=True, autoincrement=True)
    nombre: Mapped[str] = mapped_column(String(120), nullable=False)
    from_email: Mapped[str] = mapped_column(String(254), nullable=False)
    from_name: Mapped[str] = mapped_column(String(160), nullable=False, default="")
    provider: Mapped[str] = mapped_column(String(32), nullable=False, default="SMTP")
    host: Mapped[str] = mapped_column(String(255), nullable=False)
    port: Mapped[int] = mapped_column(Integer, nullable=False, default=465)
    security: Mapped[str] = mapped_column(String(16), nullable=False, default="SSL")
    username: Mapped[str] = mapped_column(String(254), nullable=False)
    secret_encrypted: Mapped[str] = mapped_column(Text, nullable=False, default="")
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="pendiente_validacion")
    last_ok_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=False), nullable=True)
    last_error: Mapped[str | None] = mapped_column(String(500), nullable=True)
    created_by_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("auth_usuarios.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=False), nullable=False, default=datetime.utcnow, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=False),
        nullable=False,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
        server_default=func.now(),
    )

    validaciones: Mapped[list["MailValidation"]] = relationship(
        back_populates="cuenta",
        cascade="all, delete-orphan",
        order_by="MailValidation.created_at.desc()",
    )

    @property
    def tiene_secreto(self) -> bool:
        return bool((self.secret_encrypted or "").strip())

    @property
    def status_label(self) -> str:
        return {
            "activa": "Activa",
            "inactiva": "Inactiva",
            "error": "Error",
            "pendiente_validacion": "Pendiente de validación",
        }.get(self.status, self.status)


class MailChannel(Base):
    __tablename__ = "mail_channels"

    codigo: Mapped[str] = mapped_column(String(40), primary_key=True)
    nombre: Mapped[str] = mapped_column(String(120), nullable=False)
    descripcion: Mapped[str | None] = mapped_column(Text, nullable=True)
    cuenta_principal_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("mail_accounts.id", ondelete="SET NULL"), nullable=True
    )
    cuenta_fallback_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("mail_accounts.id", ondelete="SET NULL"), nullable=True
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=False), nullable=False, default=datetime.utcnow, server_default=func.now()
    )

    cuenta_principal: Mapped[MailAccount | None] = relationship(
        foreign_keys=[cuenta_principal_id],
    )
    cuenta_fallback: Mapped[MailAccount | None] = relationship(
        foreign_keys=[cuenta_fallback_id],
    )


class MailValidation(Base):
    __tablename__ = "mail_validations"

    id: Mapped[int] = mapped_column(_PK, primary_key=True, autoincrement=True)
    account_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("mail_accounts.id", ondelete="CASCADE"), nullable=False, index=True
    )
    kind: Mapped[str] = mapped_column(String(20), nullable=False, default="CONNECT")
    ok: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    error_code: Mapped[str | None] = mapped_column(String(40), nullable=True)
    error_message: Mapped[str | None] = mapped_column(String(500), nullable=True)
    latency_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    to_email: Mapped[str | None] = mapped_column(String(254), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=False), nullable=False, default=datetime.utcnow, server_default=func.now()
    )

    cuenta: Mapped[MailAccount] = relationship(back_populates="validaciones")
