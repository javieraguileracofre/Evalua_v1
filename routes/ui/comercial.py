# routes/ui/comercial.py
# -*- coding: utf-8 -*-
"""Hub del área comercial: enlaces a postventa y leasing financiero."""
from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from core.paths import TEMPLATES_DIR

router = APIRouter(tags=["Comercial"])
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))


@router.get("/comercial", response_class=HTMLResponse, name="comercial_hub")
def comercial_hub(request: Request):
    return templates.TemplateResponse(
        "comercial/hub.html",
        {
            "request": request,
            "active_menu": "comercial",
        },
    )
