# core/client_ip.py
# -*- coding: utf-8 -*-
from __future__ import annotations

from fastapi import Request

from core.config import settings


def _proxy_ip(request: Request) -> str | None:
    """IP que escribe el proxy. CF-Connecting-IP gana sobre el primer salto de X-Forwarded-For."""
    cloudflare = (request.headers.get("cf-connecting-ip") or "").strip()
    if cloudflare:
        return cloudflare[:45]
    forwarded = (request.headers.get("x-forwarded-for") or "").split(",")[0].strip()
    if forwarded:
        return forwarded[:45]
    return None


def client_ip(request: Request) -> str | None:
    """IP del socket. Solo se lee el proxy si TRUST_X_FORWARDED_FOR está activo."""
    if settings.trust_x_forwarded_for:
        proxied = _proxy_ip(request)
        if proxied:
            return proxied
    if request.client and request.client.host:
        return str(request.client.host)[:45]
    return None
