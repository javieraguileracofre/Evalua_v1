# routes/ui/admin_system_status.py
# -*- coding: utf-8 -*-
"""Estado del sistema (solo lectura). No inicia/detiene servicios."""
from __future__ import annotations

from urllib.parse import urlencode

from fastapi import APIRouter, Depends, Request, status
from fastapi.responses import HTMLResponse, RedirectResponse
from core.ui_templates import EvaluaTemplates as Jinja2Templates
from sqlalchemy.orm import Session

from core.paths import TEMPLATES_DIR
from core.rbac import usuario_es_admin
from db.session import get_db
from services.operacion.system_status_service import collect_system_status

router = APIRouter(prefix="/seguridad/estado-sistema", tags=["Estado del sistema"])
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))


def _guard(request: Request) -> RedirectResponse | None:
    if usuario_es_admin(getattr(request.state, "auth_user", None)):
        return None
    q = urlencode(
        {"msg": "No tiene permiso para ver el estado del sistema (se requiere Administrador).", "sev": "danger"}
    )
    return RedirectResponse(url=f"/?{q}", status_code=status.HTTP_303_SEE_OTHER)


@router.get("", response_class=HTMLResponse, name="admin_system_status")
def system_status_page(request: Request, db: Session = Depends(get_db)):
    if (redir := _guard(request)) is not None:
        return redir
    payload = collect_system_status(db)
    return templates.TemplateResponse(
        "seguridad/system_status.html",
        {
            "request": request,
            "active_menu": "admin_system_status",
            "status": payload,
        },
    )
