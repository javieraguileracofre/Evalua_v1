# services/audit/financial.py
# -*- coding: utf-8 -*-
"""Auditoría de mutaciones de dinero, dentro de un SAVEPOINT.

Si la tabla de auditoría falla, se revierte solo el savepoint y la
transacción de negocio sigue vigente.
"""
from __future__ import annotations

import logging
from typing import Any

from sqlalchemy.orm import Session

logger = logging.getLogger("evalua.audit.financial")


def audit_financial_fact(
    db: Session,
    *,
    action: str,
    module: str,
    entity: str | None = None,
    entity_id: str | int | None = None,
    actor_id: int | None = None,
    company_id: int | None = None,
    detail: dict[str, Any] | None = None,
    result: str = "ok",
) -> None:
    nested = None
    try:
        from core.request_context import get_request_context
        from services.audit.enterprise import audit_event

        ctx = get_request_context()
        if actor_id is None:
            actor_id = ctx.get("actor_id")
        if company_id is None:
            company_id = ctx.get("company_id")
        payload = dict(detail or {})
        request_id = ctx.get("request_id")
        if request_id and "request_id" not in payload:
            payload["request_id"] = request_id

        nested = db.begin_nested()
        audit_event(
            action=action,
            result=result,
            actor_id=actor_id,
            company_id=company_id,
            module=module,
            entity=entity,
            entity_id=entity_id,
            db=db,
            detail=payload or None,
            persist_operational=True,
        )
        nested.commit()
    except Exception:
        logger.exception("auditoría financiera omitida action=%s", action)
        if nested is not None:
            try:
                nested.rollback()
            except Exception:
                logger.debug("rollback de savepoint de auditoría no aplicado", exc_info=True)
