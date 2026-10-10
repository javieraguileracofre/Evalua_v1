# core/tenant.py
# -*- coding: utf-8 -*-
"""Aísla el contexto de la petición. No elige una compañía por defecto."""
from __future__ import annotations

from contextvars import ContextVar, Token

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from core.company_context import reset_company_context, set_company_context
from core.config import settings

_current_tenant_code: ContextVar[str | None] = ContextVar("current_tenant_code", default=None)


def set_current_tenant_code(tenant_code: str | None) -> Token[str | None]:
    return _current_tenant_code.set(tenant_code)


def get_current_tenant_code() -> str | None:
    return _current_tenant_code.get()


class TenantResolutionMiddleware(BaseHTTPMiddleware):
    """No lee header, query ni cookie para elegir una base. Limpia el contexto al salir."""

    async def dispatch(self, request: Request, call_next) -> Response:
        token = set_current_tenant_code(None)
        company_token = set_company_context(None)
        try:
            return await call_next(request)
        finally:
            reset_company_context(company_token)
            _current_tenant_code.reset(token)


def tenancy_is_company_mode() -> bool:
    return bool(getattr(settings, "database_per_company", False))
