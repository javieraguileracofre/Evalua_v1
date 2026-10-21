# core/observability_middleware.py
# -*- coding: utf-8 -*-
from __future__ import annotations

import logging
import time

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from core.request_context import (
    clear_request_context,
    get_request_context,
    new_request_id,
    set_request_context,
)

logger = logging.getLogger("evalua.http")


def _extract_identity(request: Request) -> tuple[int | None, int | None]:
    company = getattr(request.state, "company", None) or getattr(
        request.state, "company_context", None
    )
    auth = getattr(request.state, "auth_user", None) or {}
    company_id = None
    if company is not None:
        company_id = getattr(company, "company_id", None) or getattr(company, "id", None)
    actor_id = None
    if isinstance(auth, dict):
        actor_id = auth.get("id") or auth.get("user_id")
    else:
        actor_id = getattr(auth, "id", None)
    try:
        company_id_i = int(company_id) if company_id is not None else None
    except (TypeError, ValueError):
        company_id_i = None
    try:
        actor_id_i = int(actor_id) if actor_id is not None else None
    except (TypeError, ValueError):
        actor_id_i = None
    return company_id_i, actor_id_i


class ObservabilityMiddleware(BaseHTTPMiddleware):
    """Asigna request_id, correlaciona company/actor autorizados y registra latencia."""

    async def dispatch(self, request: Request, call_next) -> Response:
        rid = (request.headers.get("X-Request-ID") or "").strip() or new_request_id()
        request.state.request_id = rid
        set_request_context(request_id=rid)
        started = time.perf_counter()
        status_code = 500
        response: Response | None = None
        try:
            response = await call_next(request)
            status_code = int(response.status_code)
            company_id, actor_id = _extract_identity(request)
            set_request_context(company_id=company_id, actor_id=actor_id)
            response.headers["X-Request-ID"] = rid
            return response
        except Exception:
            company_id, actor_id = _extract_identity(request)
            set_request_context(company_id=company_id, actor_id=actor_id)
            raise
        finally:
            elapsed_ms = (time.perf_counter() - started) * 1000.0
            ctx = get_request_context()
            logger.info(
                "http method=%s path=%s status=%s duration_ms=%.1f request_id=%s company_id=%s actor_id=%s",
                request.method,
                request.url.path,
                status_code,
                elapsed_ms,
                ctx.get("request_id"),
                ctx.get("company_id"),
                ctx.get("actor_id"),
            )
            clear_request_context()
