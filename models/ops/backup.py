# models/ops/backup.py
# -*- coding: utf-8 -*-
"""Metadatos de respaldos de base de datos (sin secretos)."""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import BigInteger, DateTime, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from db.base_class import Base

_PK = BigInteger().with_variant(Integer, "sqlite")


class DatabaseBackup(Base):
    __tablename__ = "ops_database_backup"

    id: Mapped[int] = mapped_column(_PK, primary_key=True, autoincrement=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="pending", index=True)
    backup_type: Mapped[str] = mapped_column(String(20), nullable=False, default="manual")
    engine_name: Mapped[str] = mapped_column(String(40), nullable=False, default="postgresql")
    database_name: Mapped[str] = mapped_column(String(120), nullable=False, default="")
    file_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    file_path: Mapped[str | None] = mapped_column(String(500), nullable=True)
    size_bytes: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    checksum_sha256: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_by_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    error_message: Mapped[str | None] = mapped_column(String(500), nullable=True)
    company_code: Mapped[str | None] = mapped_column(String(40), nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=False), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=False), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=False),
        nullable=False,
        default=datetime.utcnow,
        server_default=func.now(),
        index=True,
    )
