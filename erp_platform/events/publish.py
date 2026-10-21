# erp_platform/events/publish.py
# -*- coding: utf-8 -*-
"""Publicación de eventos de dominio con outbox preferente."""
from __future__ import annotations

import logging
from typing import Any

from sqlalchemy.orm import Session

from erp_platform.events.bus import DomainEvent, emit
from erp_platform.events.outbox import dispatch_pending, enqueue

logger = logging.getLogger("evalua.erp_platform.events.publish")


def _context_ids(
    company_id: int | None,
    actor_id: int | None,
) -> tuple[int | None, int | None]:
    """Completa company/actor desde el contexto HTTP cuando el caller no los pasa."""
    if company_id is not None and actor_id is not None:
        return company_id, actor_id
    try:
        from core.request_context import get_request_context

        ctx = get_request_context()
    except Exception:
        return company_id, actor_id
    if company_id is None:
        company_id = ctx.get("company_id")
    if actor_id is None:
        actor_id = ctx.get("actor_id")
    return company_id, actor_id


def publish_in_transaction(
    db: Session,
    *,
    event_name: str,
    payload: dict[str, Any] | None = None,
    company_id: int | None = None,
    actor_id: int | None = None,
    correlation_id: str | None = None,
) -> None:
    """
    Registra el evento en outbox dentro de la TX actual.
    Si la outbox aún no existe (pre-migración), emite en memoria como fallback.
    """
    company_id, actor_id = _context_ids(company_id, actor_id)
    outbox_id = enqueue(
        db,
        event_name=event_name,
        payload=payload,
        company_id=company_id,
        actor_id=actor_id,
        correlation_id=correlation_id,
    )
    if outbox_id is None:
        try:
            emit(
                DomainEvent(
                    name=event_name,
                    payload=payload or {},
                    company_id=company_id,
                    actor_id=actor_id,
                )
            )
        except Exception:
            logger.exception("fallback emit falló event=%s", event_name)


def flush_outbox_after_commit(db: Session, *, limit: int = 50) -> dict[str, int]:
    """Despacha PENDING tras commit. Errores no revierten la TX de negocio ya confirmada."""
    try:
        return dispatch_pending(db, limit=limit)
    except Exception:
        logger.exception("flush outbox falló")
        return {"processed": 0, "failed": 0, "skipped": 0, "reclaimed": 0}
