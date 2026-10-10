# models/auth/audit_event.py
# -*- coding: utf-8 -*-
"""Eventos de auditoría operacional (BD de compañía / legacy)."""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import BigInteger, DateTime, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from db.base_class import Base

_PK = BigInteger().with_variant(Integer, "sqlite")


class AuthAuditEvent(Base):
    __tablename__ = "auth_audit_event"

    id: Mapped[int] = mapped_column(_PK, primary_key=True, autoincrement=True)
    actor_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True, index=True)
    company_code: Mapped[str | None] = mapped_column(String(40), nullable=True)
    action: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    module: Mapped[str] = mapped_column(String(64), nullable=False, default="security")
    entity: Mapped[str | None] = mapped_column(String(64), nullable=True)
    entity_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    result: Mapped[str] = mapped_column(String(20), nullable=False, default="ok")
    ip_hmac: Mapped[str | None] = mapped_column(String(64), nullable=True)
    user_agent: Mapped[str | None] = mapped_column(String(240), nullable=True)
    detail_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=False),
        nullable=False,
        default=datetime.utcnow,
        server_default=func.now(),
        index=True,
    )
