# erp_platform/events/outbox.py
# -*- coding: utf-8 -*-
"""
Outbox transaccional de eventos de dominio.

Garantía: al menos una vez. Los handlers deben ser idempotentes.
Persistir con `enqueue` dentro de la misma Session/TX de negocio; despachar
con `dispatch_pending` después del commit (o desde un job).

Workers concurrentes: claim atómico con FOR UPDATE SKIP LOCKED.
Filas PROCESSING huérfanas (crash tras claim persistido) se reclaman.
"""
from __future__ import annotations

import json
import logging
from contextvars import ContextVar
from datetime import datetime
from typing import Any

from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from erp_platform.events.bus import DomainEvent, emit

logger = logging.getLogger("evalua.erp_platform.events.outbox")

_MAX_ATTEMPTS = 8
_dispatch_session: ContextVar[Session | None] = ContextVar(
    "evalua_outbox_dispatch_session",
    default=None,
)


def get_dispatch_session() -> Session | None:
    """Sesión que está despachando el outbox. Los handlers no deben hacer commit."""
    return _dispatch_session.get()


def outbox_table_ready(db: Session) -> bool:
    row = db.execute(
        text(
            """
            SELECT 1
            FROM information_schema.tables
            WHERE table_schema = 'public' AND table_name = 'domain_event_outbox'
            LIMIT 1
            """
        )
    ).first()
    return row is not None


def enqueue(
    db: Session,
    *,
    event_name: str,
    payload: dict[str, Any] | None = None,
    company_id: int | None = None,
    actor_id: int | None = None,
    correlation_id: str | None = None,
) -> int | None:
    """
    Inserta un evento PENDING en la misma transacción.
    Si correlation_id ya existe, retorna el id existente (idempotente).
    Si la tabla aún no existe (pre-migración), retorna None.
    """
    if not outbox_table_ready(db):
        logger.warning("outbox no disponible; event=%s omitido de persistencia", event_name)
        return None

    corr = (correlation_id or "").strip()[:64] or None
    if corr:
        existing = db.execute(
            text(
                """
                SELECT id FROM domain_event_outbox
                WHERE correlation_id = :corr
                ORDER BY id ASC
                LIMIT 1
                """
            ),
            {"corr": corr},
        ).first()
        if existing is not None:
            return int(existing[0])

    try:
        nested = db.begin_nested()
        try:
            row = db.execute(
                text(
                    """
                    INSERT INTO domain_event_outbox (
                        event_name, payload_json, company_id, actor_id, correlation_id, status
                    )
                    VALUES (
                        :name,
                        CAST(:payload AS jsonb),
                        :company_id,
                        :actor_id,
                        :correlation_id,
                        'PENDING'
                    )
                    RETURNING id
                    """
                ),
                {
                    "name": (event_name or "").strip(),
                    "payload": json.dumps(payload or {}, ensure_ascii=False, default=str),
                    "company_id": company_id,
                    "actor_id": actor_id,
                    "correlation_id": corr,
                },
            ).first()
            nested.commit()
            return int(row[0]) if row else None
        except IntegrityError:
            nested.rollback()
            if corr:
                existing = db.execute(
                    text(
                        """
                        SELECT id FROM domain_event_outbox
                        WHERE correlation_id = :corr
                        ORDER BY id ASC
                        LIMIT 1
                        """
                    ),
                    {"corr": corr},
                ).first()
                if existing is not None:
                    return int(existing[0])
            raise
    except IntegrityError:
        raise


def reclaim_stale_processing(db: Session) -> int:
    """
    Devuelve a PENDING/FAILED filas PROCESSING no bloqueadas por otro worker.

    Defensa ante crash tras un claim ya persistido. Filas en TX abiertas de
    otros workers se omiten vía SKIP LOCKED.
    """
    rows = db.execute(
        text(
            """
            UPDATE domain_event_outbox AS o
            SET status = CASE
                    WHEN o.attempts >= :max_attempts THEN 'FAILED'
                    ELSE 'PENDING'
                END,
                last_error = LEFT(
                    CONCAT(
                        COALESCE(o.last_error, ''),
                        CASE WHEN o.last_error IS NULL OR o.last_error = '' THEN '' ELSE ' | ' END,
                        'reclaimed from stale PROCESSING'
                    ),
                    2000
                )
            FROM (
                SELECT id
                FROM domain_event_outbox
                WHERE status = 'PROCESSING'
                FOR UPDATE SKIP LOCKED
            ) AS pick
            WHERE o.id = pick.id
            RETURNING o.id
            """
        ),
        {"max_attempts": _MAX_ATTEMPTS},
    ).fetchall()
    n = len(rows)
    if n:
        logger.warning("outbox reclaim: %s evento(s) PROCESSING huérfanos", n)
    return n


def dispatch_pending(db: Session, *, limit: int = 50) -> dict[str, int]:
    """Procesa eventos PENDING/FAILED con reintentos. Seguro ante workers concurrentes."""
    stats = {"processed": 0, "failed": 0, "skipped": 0, "reclaimed": 0}
    if not outbox_table_ready(db):
        return stats

    stats["reclaimed"] = reclaim_stale_processing(db)

    # Claim atómico: SKIP LOCKED evita que dos workers tomen el mismo evento.
    claimed = db.execute(
        text(
            """
            UPDATE domain_event_outbox AS o
            SET status = 'PROCESSING',
                attempts = o.attempts + 1
            FROM (
                SELECT id
                FROM domain_event_outbox
                WHERE status IN ('PENDING', 'FAILED')
                  AND attempts < :max_attempts
                ORDER BY created_at ASC
                LIMIT :lim
                FOR UPDATE SKIP LOCKED
            ) AS pick
            WHERE o.id = pick.id
            RETURNING o.id, o.event_name, o.payload_json, o.company_id, o.actor_id, o.attempts
            """
        ),
        {"max_attempts": _MAX_ATTEMPTS, "lim": int(limit)},
    ).mappings().all()

    if not claimed:
        if stats["reclaimed"]:
            db.commit()
        return stats

    for row in claimed:
        eid = int(row["id"])
        try:
            payload = row["payload_json"] or {}
            if isinstance(payload, str):
                payload = json.loads(payload)
            token = _dispatch_session.set(db)
            try:
                emit(
                    DomainEvent(
                        name=str(row["event_name"]),
                        payload=dict(payload),
                        company_id=row["company_id"],
                        actor_id=row["actor_id"],
                    )
                )
            finally:
                _dispatch_session.reset(token)
            db.execute(
                text(
                    """
                    UPDATE domain_event_outbox
                    SET status = 'DONE', processed_at = :ts, last_error = NULL
                    WHERE id = :id
                    """
                ),
                {"id": eid, "ts": datetime.utcnow()},
            )
            stats["processed"] += 1
        except Exception as exc:
            db.execute(
                text(
                    """
                    UPDATE domain_event_outbox
                    SET status = 'FAILED', last_error = :err
                    WHERE id = :id
                    """
                ),
                {"id": eid, "err": f"{type(exc).__name__}: {exc}"[:2000]},
            )
            stats["failed"] += 1
            logger.exception("outbox handler failed id=%s event=%s", eid, row["event_name"])
    db.commit()
    return stats


def enqueue_and_emit_best_effort(
    db: Session,
    *,
    event_name: str,
    payload: dict[str, Any] | None = None,
    company_id: int | None = None,
    actor_id: int | None = None,
    correlation_id: str | None = None,
    after_commit: bool = True,
) -> None:
    """
    Persiste en outbox (misma TX). Si after_commit=False, emite síncrono inmediatamente
    (solo para tests / efectos no críticos). En producción preferir dispatch_pending.
    """
    enqueue(
        db,
        event_name=event_name,
        payload=payload,
        company_id=company_id,
        actor_id=actor_id,
        correlation_id=correlation_id,
    )
    if not after_commit:
        emit(
            DomainEvent(
                name=event_name,
                payload=payload or {},
                company_id=company_id,
                actor_id=actor_id,
            )
        )
