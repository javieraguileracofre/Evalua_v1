# services/audit/enterprise.py
# -*- coding: utf-8 -*-
"""Auditoría empresarial unificada. Nunca registra secretos ni contraseñas."""
from __future__ import annotations

import logging
from typing import Any

from sqlalchemy.orm import Session

from core.client_ip import client_ip
from core.security_log import security_event
from services.platform.audit import ip_hmac, write_audit

logger = logging.getLogger("evalua.audit")

_SECRET_KEYS = frozenset(
    {
        "password",
        "password_hash",
        "token",
        "secret",
        "credential",
        "refresh_token",
        "access_token",
        "private_key",
        "database_url",
        "db_password",
        "smtp_password",
        "secret_encrypted",
    }
)


def _scrub(detail: dict[str, Any] | None) -> dict[str, Any] | None:
    if not detail:
        return None
    out: dict[str, Any] = {}
    for key, value in detail.items():
        lk = str(key).strip().lower()
        if lk in _SECRET_KEYS or any(s in lk for s in ("password", "token", "secret", "credential")):
            continue
        raw = str(value)
        if len(raw) > 240:
            raw = raw[:237] + "..."
        out[str(key)[:64]] = raw
    return out or None


def audit_event(
    *,
    action: str,
    result: str = "ok",
    actor_id: int | None = None,
    auth: dict[str, Any] | None = None,
    company_id: int | None = None,
    company_code: str | None = None,
    module: str = "security",
    entity: str | None = None,
    entity_id: str | int | None = None,
    request: Any | None = None,
    db: Session | None = None,
    identity_db: Session | None = None,
    detail: dict[str, Any] | None = None,
    persist_operational: bool = True,
) -> None:
    """
    Registra en security_log siempre; opcionalmente en PlatformAuditLog (identity)
    y en auth_audit_event (BD operacional de la empresa).
    """
    uid = actor_id
    if uid is None and isinstance(auth, dict):
        try:
            uid = int(auth.get("uid")) if auth.get("uid") is not None else None
        except (TypeError, ValueError):
            uid = None

    if company_id is None and isinstance(auth, dict) and auth.get("active_company_id") is not None:
        try:
            company_id = int(auth["active_company_id"])
        except (TypeError, ValueError):
            company_id = None
    if not company_code and isinstance(auth, dict):
        company_code = str(auth.get("company_code") or "") or None

    ip_raw = None
    ua = None
    if request is not None:
        try:
            ip_raw = client_ip(request)
        except Exception:
            ip_raw = None
        try:
            ua = (request.headers.get("user-agent") or "")[:240]
        except Exception:
            ua = None

    scrubbed = _scrub(detail)
    security_event(
        action,
        uid=uid if uid is not None else "-",
        auth=auth,
        result=result,
        module=module,
        entity=entity,
        entity_id=entity_id,
        company=company_code or company_id,
    )

    hmac_val = None
    try:
        from core.config import settings

        hmac_val = ip_hmac(ip_raw, settings.secret_key)
    except Exception:
        hmac_val = None

    if identity_db is not None:
        try:
            write_audit(
                identity_db,
                actor_id=uid,
                action=action,
                result=result,
                company_id=company_id,
                module=module,
                resource=f"{entity}:{entity_id}" if entity and entity_id is not None else entity,
                ip_hmac_value=hmac_val,
            )
        except Exception:
            logger.exception("No se pudo escribir PlatformAuditLog action=%s", action)

    if persist_operational and db is not None:
        try:
            from models.auth.audit_event import AuthAuditEvent
            import json

            db.add(
                AuthAuditEvent(
                    actor_id=uid,
                    company_code=(company_code or "")[:40] or None,
                    action=str(action)[:64],
                    module=str(module)[:64],
                    entity=(str(entity)[:64] if entity else None),
                    entity_id=(str(entity_id)[:64] if entity_id is not None else None),
                    result=str(result)[:20],
                    ip_hmac=hmac_val,
                    user_agent=ua,
                    detail_json=json.dumps(scrubbed, ensure_ascii=False) if scrubbed else None,
                )
            )
            db.flush()
        except Exception:
            logger.exception("No se pudo persistir auth_audit_event action=%s", action)
