# core/client_ip.py
# -*- coding: utf-8 -*-
from __future__ import annotations

from fastapi import Request

from core.config import settings


def client_ip(request: Request) -> str | None:
    """IP del socket, salvo que TRUST_X_FORWARDED_FOR esté activo (proxy de confianza)."""
    if settings.trust_x_forwarded_for:
        forwarded = (request.headers.get("x-forwarded-for") or "").split(",")[0].strip()
        if forwarded:
            return forwarded[:45]
    if request.client and request.client.host:
        return str(request.client.host)[:45]
    return None
