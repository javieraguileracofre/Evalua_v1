# core/auth_middleware.py
# -*- coding: utf-8 -*-
from __future__ import annotations

from urllib.parse import quote

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from core.auth_paths import is_public_path
from core.config import settings


class AuthMiddleware(BaseHTTPMiddleware):
    """
    Exige sesión con payload `auth` (dict) para todas las rutas no públicas.
    Debe ejecutarse DESPUÉS de SessionMiddleware (más interno en la pila).
    """

    async def dispatch(self, request: Request, call_next) -> Response:
        if request.method == "OPTIONS":
            return await call_next(request)

        path = request.url.path
        sess = getattr(request, "session", None)

        auth: dict | None = None
        if sess is not None:
            raw = sess.get("auth")
            if isinstance(raw, dict) and raw.get("uid"):
                auth = raw
        request.state.auth_user = auth

        if is_public_path(path, settings):
            return await call_next(request)

        if auth is None:
            nxt = path
            if request.url.query:
                nxt = f"{path}?{request.url.query}"
            loc = f"/login?next={quote(nxt, safe='')}"
            from starlette.responses import RedirectResponse

            return RedirectResponse(url=loc, status_code=302)

        return await call_next(request)
