# services/platform/audit.py
# -*- coding: utf-8 -*-
from __future__ import annotations

import hashlib
import hmac

from sqlalchemy.orm import Session

from models.identity.models import PlatformAuditLog


def ip_hmac(ip: str | None, secret: str) -> str | None:
    raw = (ip or "").strip()
    if not raw or not secret:
        return None
    return hmac.new(secret.encode("utf-8"), raw.encode("utf-8"), hashlib.sha256).hexdigest()[:32]


def write_audit(
    db: Session,
    *,
    actor_id: int | None,
    action: str,
    result: str,
    company_id: int | None = None,
    module: str = "platform",
    resource: str | None = None,
    request_id: str | None = None,
    ip_hmac_value: str | None = None,
) -> None:
    db.add(
        PlatformAuditLog(
            actor_id=actor_id,
            company_id=company_id,
            action=action[:64],
            module=module[:64],
            resource=(resource or None),
            result=result[:20],
            request_id=request_id,
            ip_hmac=ip_hmac_value,
        )
    )
