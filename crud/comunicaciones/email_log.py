# crud/comunicaciones/email_log.py
# -*- coding: utf-8 -*-
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from models.comunicaciones.email_log import EmailLog

try:
    from zoneinfo import ZoneInfo
except Exception:  # pragma: no cover
    ZoneInfo = None


TZ_CL = "America/Santiago"


def _now_cl() -> datetime:
    if ZoneInfo is None:
        return datetime.utcnow()
    return datetime.now(ZoneInfo(TZ_CL))


def _cl_day_bounds_utc_naive(ref_cl: Optional[datetime] = None) -> tuple[datetime, datetime]:
    """
    Retorna el inicio y fin del día Chile, convertidos a UTC naive,
    para comparar con timestamps UTC naive guardados en la BD.
    """
    if ZoneInfo is None:
        ref = datetime.utcnow()
        start = ref.replace(hour=0, minute=0, second=0, microsecond=0)
        end = start + timedelta(days=1)
        return start, end

    ref = ref_cl or _now_cl()
    start_local = ref.replace(hour=0, minute=0, second=0, microsecond=0)
    end_local = start_local + timedelta(days=1)

    start_utc = start_local.astimezone(timezone.utc).replace(tzinfo=None)
    end_utc = end_local.astimezone(timezone.utc).replace(tzinfo=None)
    return start_utc, end_utc


def crear_email_log(
    db: Session,
    *,
    modulo: str,
    evento: str,
    cliente_id: int | None,
    cxc_id: int | None,
    caso_id: int | None = None,
    to_email: str,
    subject: str,
    include_detalle: bool = True,
    status: str = "PENDIENTE",
    meta_json: str | None = None,
) -> EmailLog:
    item = EmailLog(
        modulo=modulo,
        evento=evento,
        cliente_id=cliente_id,
        cxc_id=cxc_id,
        caso_id=caso_id,
        to_email=to_email,
        subject=subject,
        include_detalle=bool(include_detalle),
        status=status,
        meta_json=meta_json or json.dumps({}, ensure_ascii=False),
    )
    db.add(item)
    db.commit()
    db.refresh(item)
    return item


def marcar_enviado(db: Session, *, email_log_id: int) -> EmailLog:
    item = db.get(EmailLog, email_log_id)
    if not item:
        raise ValueError("EmailLog no encontrado.")

    item.status = "ENVIADO"
    item.sent_at = datetime.utcnow()
    item.error_message = None
    db.commit()
    db.refresh(item)
    return item


def marcar_error(db: Session, *, email_log_id: int, error_message: str) -> EmailLog:
    item = db.get(EmailLog, email_log_id)
    if not item:
        raise ValueError("EmailLog no encontrado.")

    item.status = "ERROR"
    item.error_message = (error_message or "")[:5000]
    db.commit()
    db.refresh(item)
    return item


def listar_logs_cliente(db: Session, *, cliente_id: int, limit: int = 15) -> list[EmailLog]:
    stmt = (
        select(EmailLog)
        .where(EmailLog.cliente_id == cliente_id)
        .order_by(EmailLog.created_at.desc())
        .limit(limit)
    )
    return list(db.scalars(stmt))


def ya_enviado_hoy_cliente(
    db: Session,
    *,
    cliente_id: int,
    modulo: str = "COBRANZA",
    evento: str = "RECORDATORIO",
) -> bool:
    start_utc, end_utc = _cl_day_bounds_utc_naive()

    stmt = (
        select(EmailLog.id)
        .where(EmailLog.cliente_id == cliente_id)
        .where(EmailLog.modulo == modulo)
        .where(EmailLog.evento == evento)
        .where(EmailLog.status == "ENVIADO")
        .where(
            or_(
                (
                    EmailLog.sent_at.is_not(None)
                    & (EmailLog.sent_at >= start_utc)
                    & (EmailLog.sent_at < end_utc)
                ),
                (
                    EmailLog.sent_at.is_(None)
                    & (EmailLog.created_at >= start_utc)
                    & (EmailLog.created_at < end_utc)
                ),
            )
        )
        .limit(1)
    )
    return db.execute(stmt).first() is not None


def contar_logs_periodo(
    db: Session,
    *,
    horas: int | None = None,
    dias: int | None = None,
    status: str | None = None,
    modulo: str | None = None,
    evento: str | None = None,
) -> int:
    stmt = select(EmailLog.id)

    if horas is not None:
        desde = datetime.utcnow() - timedelta(hours=horas)
        stmt = stmt.where(EmailLog.created_at >= desde)

    if dias is not None:
        desde = datetime.utcnow() - timedelta(days=dias)
        stmt = stmt.where(EmailLog.created_at >= desde)

    if status:
        stmt = stmt.where(EmailLog.status == status)

    if modulo:
        stmt = stmt.where(EmailLog.modulo == modulo)

    if evento:
        stmt = stmt.where(EmailLog.evento == evento)

    return len(list(db.scalars(stmt)))