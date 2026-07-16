# models/maestros/cliente_extendido.py
# -*- coding: utf-8 -*-
from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import BigInteger, Boolean, DateTime, ForeignKey, String, Text, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from db.base_class import Base

if TYPE_CHECKING:
    from models.maestros.cliente import Cliente


class ClienteDireccion(Base):
    __tablename__ = "cliente_direccion"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    cliente_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("clientes.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    tipo: Mapped[str] = mapped_column(String(30), nullable=False, default="COMERCIAL", server_default="COMERCIAL")
    direccion: Mapped[str] = mapped_column(String(250), nullable=False)
    comuna: Mapped[str | None] = mapped_column(String(100))
    ciudad: Mapped[str | None] = mapped_column(String(100))
    region: Mapped[str | None] = mapped_column(String(100))
    pais: Mapped[str] = mapped_column(String(80), nullable=False, default="Chile", server_default="Chile")
    es_principal: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default=text("false"))
    activo: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default=text("true"))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=datetime.utcnow, server_default=text("CURRENT_TIMESTAMP")
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
        server_default=text("CURRENT_TIMESTAMP"),
    )

    cliente: Mapped["Cliente"] = relationship("Cliente", back_populates="direcciones", lazy="selectin")


class ClienteAuditoria(Base):
    __tablename__ = "cliente_auditoria"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    cliente_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("clientes.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    campo: Mapped[str] = mapped_column(String(80), nullable=False)
    valor_anterior: Mapped[str | None] = mapped_column(Text)
    valor_nuevo: Mapped[str | None] = mapped_column(Text)
    usuario: Mapped[str] = mapped_column(String(200), nullable=False, default="sistema", server_default="sistema")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=datetime.utcnow, server_default=text("CURRENT_TIMESTAMP")
    )

    cliente: Mapped["Cliente"] = relationship("Cliente", back_populates="auditoria", lazy="selectin")
