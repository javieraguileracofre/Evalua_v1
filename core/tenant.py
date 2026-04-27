# core/tenant.py
# -*- coding: utf-8 -*-
from __future__ import annotations

from contextvars import ContextVar, Token
import re

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from core.config import settings


_current_tenant_code: ContextVar[str | None] = ContextVar(
    "current_tenant_code",
    default=None,
)


def set_current_tenant_code(tenant_code: str | None) -> Token[str | None]:
    return _current_tenant_code.set(tenant_code)


def get_current_tenant_code() -> str | None:
    return _current_tenant_code.get()


_TENANT_CODE_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{0,63}$")


def _normalize_tenant_code(value: str | None) -> str:
    code = (value or "").strip().lower()
    if not code:
        return settings.default_tenant_code
    if not _TENANT_CODE_RE.match(code):
        return settings.default_tenant_code
    return code


class TenantResolutionMiddleware(BaseHTTPMiddleware):
    """
    Resuelve tenant de forma segura (server-side):
    1) tenant de sesión autenticada (`session.auth.tenant_code`)
    2) tenant por defecto de la aplicación

    No confía en header/query/cookie del cliente para evitar
    cambio de tenant no autorizado (tenant hopping).
    """

    async def dispatch(self, request: Request, call_next) -> Response:
        tenant_code = settings.default_tenant_code
        sess = getattr(request, "session", None)
        if isinstance(sess, dict):
            auth = sess.get("auth")
            if isinstance(auth, dict):
                tenant_code = auth.get("tenant_code") or settings.default_tenant_code

        tenant_code = _normalize_tenant_code(tenant_code)
        token = set_current_tenant_code(tenant_code)
        try:
            response = await call_next(request)
            if settings.app_debug:
                response.headers["X-Resolved-Tenant"] = tenant_code
            return response
        finally:
            _current_tenant_code.reset(token)