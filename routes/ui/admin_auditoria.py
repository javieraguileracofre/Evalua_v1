# routes/ui/admin_auditoria.py
# -*- coding: utf-8 -*-
"""Consulta de auditoría operacional (solo ADMIN)."""
from __future__ import annotations

from urllib.parse import urlencode

from fastapi import APIRouter, Depends, Query, Request, status
from fastapi.responses import HTMLResponse, RedirectResponse
from core.ui_templates import EvaluaTemplates as Jinja2Templates
from sqlalchemy import select
from sqlalchemy.orm import Session

from core.paths import TEMPLATES_DIR
from core.rbac import usuario_es_admin
from db.session import get_db
from models.auth.audit_event import AuthAuditEvent

router = APIRouter(prefix="/seguridad/auditoria", tags=["Auditoría"])
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))


def _guard(request: Request) -> RedirectResponse | None:
    if usuario_es_admin(getattr(request.state, "auth_user", None)):
        return None
    q = urlencode({"msg": "No tiene permiso para ver la auditoría (se requiere Administrador).", "sev": "danger"})
    return RedirectResponse(url=f"/?{q}", status_code=status.HTTP_303_SEE_OTHER)


@router.get("", response_class=HTMLResponse, name="seguridad_auditoria")
def auditoria_lista(
    request: Request,
    db: Session = Depends(get_db),
    page: int = Query(1, ge=1),
    q: str = Query(""),
):
    if (redir := _guard(request)) is not None:
        return redir
    page_size = 40
    stmt = select(AuthAuditEvent).order_by(AuthAuditEvent.created_at.desc(), AuthAuditEvent.id.desc())
    term = (q or "").strip()
    if term:
        like = f"%{term}%"
        stmt = stmt.where(
            (AuthAuditEvent.action.ilike(like))
            | (AuthAuditEvent.entity.ilike(like))
            | (AuthAuditEvent.module.ilike(like))
        )
    rows = list(db.scalars(stmt.offset((page - 1) * page_size).limit(page_size + 1)))
    has_more = len(rows) > page_size
    rows = rows[:page_size]
    return templates.TemplateResponse(
        "seguridad/auditoria_lista.html",
        {
            "request": request,
            "active_menu": "seguridad_auditoria",
            "events": rows,
            "page": page,
            "has_more": has_more,
            "q": term,
        },
    )
