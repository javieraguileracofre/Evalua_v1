# routes/ui/comercial.py
# -*- coding: utf-8 -*-
"""Hub del área comercial: nota de venta, leasing y scoring."""
from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from core.paths import TEMPLATES_DIR
from core.rbac import guard_operacion_consulta

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
