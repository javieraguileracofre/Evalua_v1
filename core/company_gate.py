# core/company_gate.py
# -*- coding: utf-8 -*-
"""Exige identidad y membresía. No abre otra compañía si la base falla."""
from __future__ import annotations

import logging
import uuid
from urllib.parse import quote

from sqlalchemy.orm import Session
from starlette.requests import Request
from starlette.responses import HTMLResponse, RedirectResponse, Response

from core.company_context import CompanyContext, set_company_context
from core.config import settings
from db.identity_session import get_identity_sessionmaker
from models.identity.models import Company, IdentityUser
from services.platform.access import active_memberships, authorize_company
from services.platform.messages import MSG_DB_DOWN, MSG_NO_ACCESS, MSG_NO_COMPANY, MSG_SCHEMA_OLD
from services.platform.schema_version import registry_schema_matches, runtime_schema_version

logger = logging.getLogger("evalua.company_gate")

_OPEN_WITHOUT_COMPANY = (
    "/empresa/seleccionar",
    "/empresa/cambiar",
    "/logout",
)


def _codigos(values) -> set[str]:
    if not isinstance(values, list):
        return set()
    return {str(item).strip().upper() for item in values if str(item).strip()}


def _auth_tiene_empresas(auth: dict) -> bool:
    return "ADMIN" in _codigos(auth.get("roles")) or "EMPRESAS" in _codigos(auth.get("visibleModules"))


def _puede_abrir_empresas(identity: Session, user: IdentityUser, auth: dict) -> bool:
    if user.is_platform_admin or _auth_tiene_empresas(auth):
        return True
    for membership in active_memberships(identity, int(user.id)):
        if "ADMIN" in _codigos(list(membership.role_codes or [])) or "EMPRESAS" in _codigos(
            list(membership.module_keys or [])
        ):
            return True
    return False


def _request_id(request: Request) -> str:
    current = getattr(request.state, "request_id", None)
    if isinstance(current, str) and current:
        return current
    generated = uuid.uuid4().hex[:12]
    request.state.request_id = generated
    return generated


def _page(title: str, message: str, status_code: int) -> HTMLResponse:
    body = (
        "<!DOCTYPE html><html lang=\"es\"><head><meta charset=\"utf-8\"/>"
        f"<title>{title}</title></head>"
        "<body style=\"font-family:system-ui,sans-serif;padding:2rem;max-width:40rem;\">"
        f"<h1 style=\"font-size:1.25rem;\">{title}</h1><p>{message}</p>"
        "<p><a href=\"/login\">Volver al acceso</a></p></body></html>"
    )
    return HTMLResponse(content=body, status_code=status_code)


def _choices(db: Session, user_id: int) -> list[dict]:
    rows = []
    for membership in active_memberships(db, user_id):
        company = db.get(Company, membership.company_id)
        if company is None:
            continue
        rows.append(
            {
                "id": int(company.id),
                "legal_name": company.legal_name,
                "trade_name": company.trade_name or "",
                "rut": company.rut,
            }
        )
    return rows


def _bind(company: Company, membership, user: IdentityUser, choices: list[dict]) -> dict:
    record = company.database
    set_company_context(
        CompanyContext(
            company_id=int(company.id),
            company_code=company.code,
            legal_name=company.legal_name,
            trade_name=company.trade_name or "",
            rut=company.rut,
            database_id=int(record.id) if record is not None else 0,
            schema_version=company.schema_version or "",
            authorized=True,
            address=company.address or "",
            region=company.region or "",
            commune=company.commune or "",
            phone=company.phone or "",
            email=company.email or "",
        )
    )
    roles = [str(item) for item in (membership.role_codes or [])]
    modules = [str(item) for item in (membership.module_keys or [])]
    return {
        "uid": int(user.id),
        "identity_user_id": int(user.id),
        "email": user.email,
        "nombre": user.nombre_completo,
        "roles": roles,
        "sv": int(user.session_version or 1),
        "visibleModules": modules,
        "is_platform_admin": bool(user.is_platform_admin),
        "active_company_id": int(company.id),
        "company_code": company.code,
        "company_legal_name": company.legal_name,
        "company_trade_name": company.trade_name or "",
        "company_rut": company.rut,
        "company_choices": choices,
    }


async def dispatch_company_mode(request: Request, call_next) -> Response:
    path = request.url.path
    sess = getattr(request, "session", None)
    auth = sess.get("auth") if isinstance(sess, dict) else None
    if not isinstance(auth, dict):
        auth = None
    request.state.auth_user = auth

    from core.auth_paths import is_public_path

    if is_public_path(path, settings) and not (path == "/" and auth):
        return await call_next(request)
    if auth is None or not auth.get("identity_user_id"):
        loc = "/login"
        if path != "/":
            loc = f"/login?next={quote(path, safe='')}"
        return RedirectResponse(url=loc, status_code=302)

    identity = get_identity_sessionmaker()()
    try:
        try:
            user = identity.get(IdentityUser, int(auth.get("identity_user_id")))
        except (TypeError, ValueError):
            user = None
        if user is None or not user.activo:
            if sess is not None:
                sess.pop("auth", None)
            return RedirectResponse(url="/login?msg=Sesion+expirada&sev=warning", status_code=302)
        try:
            cookie_sv = int(auth.get("sv") or 0)
        except (TypeError, ValueError):
            cookie_sv = 0
        if cookie_sv != int(user.session_version or 1):
            if sess is not None:
                sess.pop("auth", None)
            return RedirectResponse(url="/login?msg=Sesion+expirada&sev=warning", status_code=302)

        choices = _choices(identity, int(user.id))
        if path in _OPEN_WITHOUT_COMPANY or path.startswith("/plataforma"):
            auth = {
                **auth,
                "is_platform_admin": bool(user.is_platform_admin),
                "company_choices": choices,
                "identity_user_id": int(user.id),
                "email": user.email,
                "nombre": user.nombre_completo,
                "sv": int(user.session_version or 1),
            }
            request.state.auth_user = auth
            if sess is not None:
                sess["auth"] = auth
            if path.startswith("/plataforma") and not _puede_abrir_empresas(identity, user, auth):
                return _page("Sin acceso", MSG_NO_ACCESS, 403)
            if path.startswith("/plataforma") and not _auth_tiene_empresas(auth):
                modulos = list(auth.get("visibleModules") or [])
                auth = {**auth, "visibleModules": [*modulos, "EMPRESAS"]}
                request.state.auth_user = auth
            return await call_next(request)

        company_id = auth.get("active_company_id")
        membership = authorize_company(identity, int(user.id), company_id) if company_id else None
        if membership is None:
            if user.is_platform_admin and not choices:
                return RedirectResponse(url="/plataforma/empresas", status_code=302)
            if not choices:
                return _page("Sin compañía", MSG_NO_COMPANY, 403)
            return RedirectResponse(url="/empresa/seleccionar", status_code=302)
        company = identity.get(Company, membership.company_id)
        if company is None or company.status != "ACTIVE":
            logger.info(
                "access denied company_id=%s identity_user_id=%s request_id=%s",
                company_id,
                user.id,
                _request_id(request),
            )
            return _page("Sin acceso", MSG_NO_ACCESS, 403)
        record = company.database
        if record is None or record.status != "ACTIVE":
            logger.info(
                "database registry denied company_id=%s identity_user_id=%s request_id=%s",
                company.id,
                user.id,
                _request_id(request),
            )
            return _page("Sin acceso", MSG_NO_ACCESS, 403)
        if not registry_schema_matches(company.schema_version, record.schema_version):
            logger.info(
                "schema mismatch company_id=%s identity_user_id=%s request_id=%s",
                company.id,
                user.id,
                _request_id(request),
            )
            return _page("Esquema", MSG_SCHEMA_OLD, 409)
        refreshed = _bind(company, membership, user, choices)
        request.state.auth_user = refreshed
        if sess is not None:
            sess["auth"] = refreshed
        try:
            from services.platform.projection import project_membership
            from db.company_engine import get_company_sessionmaker

            company_db = get_company_sessionmaker(int(company.id))()
            try:
                runtime = runtime_schema_version(company_db.get_bind())
                if runtime != (company.schema_version or "").strip():
                    logger.info(
                        "schema mismatch company_id=%s identity_user_id=%s request_id=%s",
                        company.id,
                        user.id,
                        _request_id(request),
                    )
                    return _page("Esquema", MSG_SCHEMA_OLD, 409)
                local = project_membership(company_db, user, membership)
                company_db.commit()
                refreshed["uid"] = int(local.id)
                request.state.auth_user = refreshed
                if sess is not None:
                    sess["auth"] = refreshed
            finally:
                company_db.close()
        except Exception:
            logger.error(
                "company database unavailable company_id=%s identity_user_id=%s request_id=%s",
                company.id,
                user.id,
                _request_id(request),
            )
            return _page("Conexión", MSG_DB_DOWN, 503)
        return await call_next(request)
    finally:
        identity.close()
