# core/security_headers.py
# -*- coding: utf-8 -*-
from __future__ import annotations

from starlette.datastructures import MutableHeaders
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from core.config import settings

# CSP pragmática: la UI usa scripts inline y CDN Bootstrap/Google Fonts.
# Paso siguiente (documentado): nonce + vendor local y quitar 'unsafe-inline'.
# img-src incluye CDN de comparables LOP (Chileautos / Autocosmos / Mercado Libre).
_CSP = (
    "default-src 'self'; "
    "base-uri 'self'; "
    "form-action 'self'; "
    "frame-ancestors 'none'; "
    "object-src 'none'; "
    "img-src 'self' data: blob: "
    "https://chileautos.pxcrush.net "
    "https://*.pxcrush.net "
    "https://acroadtrip.blob.core.windows.net "
    "https://http2.mlstatic.com "
    "https://*.mlstatic.com; "
    "font-src 'self' https://fonts.gstatic.com https://cdn.jsdelivr.net data:; "
    "style-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net https://fonts.googleapis.com; "
    "script-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net; "
    "connect-src 'self' https://cdn.jsdelivr.net"
)


class SecurityHeadersMiddleware:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        async def send_wrapper(message: Message) -> None:
            if message["type"] == "http.response.start":
                headers = MutableHeaders(scope=message)
                headers.setdefault("X-Frame-Options", "DENY")
                headers.setdefault("X-Content-Type-Options", "nosniff")
                headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
                headers.setdefault(
                    "Permissions-Policy",
                    "camera=(), microphone=(), geolocation=(), payment=()",
                )
                # Forzar CSP vigente (no setdefault): evita quedar con una política vieja en caché de proceso.
                headers["Content-Security-Policy"] = _CSP
                if settings.auth_cookie_secure and not settings.is_dev:
                    headers.setdefault(
                        "Strict-Transport-Security",
                        "max-age=31536000; includeSubDomains",
                    )
            await send(message)

        await self.app(scope, receive, send_wrapper)
