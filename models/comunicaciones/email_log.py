# models/comunicaciones/email_log.py
# -*- coding: utf-8 -*-
from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, String, Text

from db.base_class import Base


class EmailLog(Base):
    __tablename__ = "email_log"

    id = Column(Integer, primary_key=True, index=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)

    modulo = Column(String(50), nullable=False, default="COBRANZA")
    evento = Column(String(50), nullable=False, default="RECORDATORIO")

    cliente_id = Column(Integer, ForeignKey("clientes.id"), nullable=True)
    cxc_id = Column(Integer, ForeignKey("cuentas_por_cobrar.id"), nullable=True)
    caso_id = Column(Integer, ForeignKey("postventa_solicitudes.id"), nullable=True)

    to_email = Column(String(255), nullable=False)
    subject = Column(String(255), nullable=False)
    include_detalle = Column(Boolean, nullable=False, default=True)

    status = Column(String(20), nullable=False, default="PENDIENTE")  # PENDIENTE / ENVIADO / ERROR
    sent_at = Column(DateTime, nullable=True)
    error_message = Column(Text, nullable=True)

    meta_json = Column(Text, nullable=True)