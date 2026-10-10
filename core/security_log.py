# core/security_log.py
# -*- coding: utf-8 -*-
"""Eventos de seguridad estructurados. No registrar secretos, cookies ni PII innecesaria."""
from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger("evalua.security")


def _uid(auth: dict[str, Any] | None) -> str:
    if not isinstance(auth, dict):
        return "-"
    raw = auth.get("uid")
    if raw is None:
        return "-"
    try:
        return str(int(raw))
    except (TypeError, ValueError):
        return "-"


def security_event(event: str, *, uid: str | int | None = None, auth: dict[str, Any] | None = None, **fields: Any) -> None:
    """Una línea: event=... uid=... k=v (valores sin saltos de línea)."""
    parts = [f"event={event.replace(' ', '_')}"]
    resolved = uid if uid is not None else _uid(auth)
    parts.append(f"uid={resolved}")
    for key, value in fields.items():
        if value is None:
            continue
        raw = str(value).replace("\n", " ").replace("\r", " ").strip()
        if len(raw) > 180:
            raw = raw[:177] + "..."
        parts.append(f"{key}={raw}")
    logger.info(" ".join(parts))
