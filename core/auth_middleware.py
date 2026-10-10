# core/auth_middleware.py
# -*- coding: utf-8 -*-
from __future__ import annotations

import logging
from urllib.parse import quote

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from core.auth_paths import is_public_path
from core.config import settings

logger = logging.getLogger("evalua.auth.mw")


class AuthMiddleware(BaseHTTPMiddleware):
    """
    Exige sesión con payload `auth` (dict) para todas las rutas no públicas.
    Debe ejecutarse DESPUÉS de SessionMiddleware (más interno en la pila).
    Revalida usuario activo y session_version contra la base en cada request.
    """

    async def dispatch(self, request: Request, call_next) -> Response:
        if request.method == "OPTIONS":
            return await call_next(request)

        path = request.url.path
        if getattr(settings, "database_per_company", False):
            from core.company_gate import dispatch_company_mode

            return await dispatch_company_mode(request, call_next)

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

        refreshed = None
        try:
            from core.session_revalidate import revalidar_auth_payload
            from db.session import get_session_local

            SessionLocal = get_session_local()
            db = SessionLocal()
            try:
                refreshed = revalidar_auth_payload(db, auth)
            finally:
                db.close()
        except Exception:
            logger.exception("No se pudo revalidar la sesión uid=%s", auth.get("uid"))
            refreshed = None

        if refreshed is None:
            if sess is not None:
                sess.pop("auth", None)
            request.state.auth_user = None
            from starlette.responses import RedirectResponse

            return RedirectResponse(url="/login?msg=Sesion+expirada&sev=warning", status_code=302)

        auth = refreshed
        request.state.auth_user = auth
        if sess is not None:
            sess["auth"] = auth

        # Fail-closed: sin lista (o vacía) se rehidrata desde roles; ADMIN recibe catálogo completo.
        raw_mods = auth.get("visibleModules")
        needs_modules = "visibleModules" not in auth or not isinstance(raw_mods, list) or not raw_mods
        if needs_modules:
            from core.module_catalog import ALL_ASSIGNABLE_KEYS, default_visible_modules_for_roles
            from core.rbac import auth_roles, usuario_es_admin

            if usuario_es_admin(auth):
                enriched = {**auth, "visibleModules": list(ALL_ASSIGNABLE_KEYS)}
            else:
                enriched = {
                    **auth,
                    "visibleModules": sorted(default_visible_modules_for_roles(auth_roles(auth))),
                }
            auth = enriched
            request.state.auth_user = auth
            if sess is not None:
                sess["auth"] = auth

        return await call_next(request)
