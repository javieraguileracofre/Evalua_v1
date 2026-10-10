# routes/ui/empresa_contexto.py
# -*- coding: utf-8 -*-
from __future__ import annotations

import secrets

from fastapi import APIRouter, Form, Request, status
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from core.paths import TEMPLATES_DIR
from core.security_log import security_event
from db.identity_session import get_identity_sessionmaker
from services.platform.access import authorize_company
from services.platform.audit import write_audit
from services.platform.messages import MSG_NO_ACCESS

router = APIRouter(tags=["Compañía activa"])
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))


def _auth(request: Request) -> dict | None:
    raw = request.session.get("auth")
    return raw if isinstance(raw, dict) else None


@router.get("/empresa/seleccionar", response_class=HTMLResponse, name="empresa_seleccionar")
def seleccionar_get(request: Request):
    auth = _auth(request)
    if auth is None:
        return RedirectResponse(url="/login", status_code=status.HTTP_303_SEE_OTHER)
    if "csrf_login" not in request.session:
        request.session["csrf_login"] = secrets.token_urlsafe(32)
    return templates.TemplateResponse(
        "auth/seleccionar_empresa.html",
        {
            "request": request,
            "companies": auth.get("company_choices") or [],
            "csrf_token": request.session.get("csrf_global") or request.session.get("csrf_login") or "",
            "error_message": request.session.pop("company_error", None),
        },
    )


@router.post("/empresa/cambiar", name="empresa_cambiar")
@router.post("/empresa/seleccionar", name="empresa_seleccionar_post")
def seleccionar_post(request: Request, company_id: int = Form(...)):
    auth = _auth(request)
    if auth is None or not auth.get("identity_user_id"):
        return RedirectResponse(url="/login", status_code=status.HTTP_303_SEE_OTHER)
    identity = get_identity_sessionmaker()()
    try:
        membership = authorize_company(identity, int(auth["identity_user_id"]), int(company_id))
        if membership is None:
            write_audit(
                identity,
                actor_id=int(auth["identity_user_id"]),
                company_id=int(company_id),
                action="COMPANY_SWITCH",
                result="denied",
            )
            identity.commit()
            request.session["company_error"] = MSG_NO_ACCESS
            security_event("company_switch_denied", uid=auth.get("identity_user_id"), company_id=company_id)
            return RedirectResponse(url="/empresa/seleccionar", status_code=status.HTTP_303_SEE_OTHER)
        company = membership.company
        auth = {
            **auth,
            "active_company_id": int(company.id),
            "company_code": company.code,
            "company_legal_name": company.legal_name,
            "company_trade_name": company.trade_name or "",
            "company_rut": company.rut,
            "roles": list(membership.role_codes or []),
            "visibleModules": list(membership.module_keys or []),
        }
        request.session["auth"] = auth
        write_audit(
            identity,
            actor_id=int(auth["identity_user_id"]),
            company_id=int(company.id),
            action="COMPANY_SWITCH",
            result="ok",
            resource=company.code,
        )
        identity.commit()
    finally:
        identity.close()
    return RedirectResponse(url="/", status_code=status.HTTP_303_SEE_OTHER)
