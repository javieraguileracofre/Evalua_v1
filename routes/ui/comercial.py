# routes/ui/comercial.py
# -*- coding: utf-8 -*-
"""Hub del área comercial: nota de venta, leasing y scoring."""
from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from core.paths import TEMPLATES_DIR
from core.rbac import guard_operacion_consulta
from crud.comercial import leasing_fin as crud_lf
from db.session import get_db

router = APIRouter(tags=["Comercial"])
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))


@router.get("/comercial", response_class=HTMLResponse, name="comercial_hub")
def comercial_hub(request: Request):
    if (redir := guard_operacion_consulta(request)) is not None:
        return redir
    return templates.TemplateResponse(
        "comercial/hub.html",
        {
            "request": request,
            "active_menu": "comercial",
        },
    )


@router.get("/comercial/leasing-financiero", response_class=HTMLResponse, name="leasing_financiero_hub")
def leasing_financiero_hub(request: Request, db: Session = Depends(get_db)):
    if (redir := guard_operacion_consulta(request)) is not None:
        return redir
    resumen = crud_lf.get_hub_resumen(db)
    return templates.TemplateResponse(
        "comercial/leasing_financiero/hub.html",
        {
            "request": request,
            **resumen,
            "active_menu": "leasing_financiero",
        },
    )


@router.get("/comercial/leasing-financiero/cotizaciones", include_in_schema=False)
def leasing_financiero_hub_redirect(request: Request):
    return RedirectResponse(url=str(request.url_for("lf_cotizaciones_list")), status_code=302)
