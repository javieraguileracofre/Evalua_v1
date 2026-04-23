# routes/ui/finanzas.py
# -*- coding: utf-8 -*-
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Query, Request, status
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from core.paths import TEMPLATES_DIR
from core.rbac import guard_finanzas_consulta
from crud.finanzas import dashboard as crud_dashboard
from db.session import get_db

router = APIRouter(tags=["Finanzas"])
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))


@router.get("/finanzas/hub", response_class=HTMLResponse, name="finanzas_hub")
def finanzas_hub(
    request: Request,
    msg: str | None = Query(None),
    sev: str = Query("info"),
):
    if (redir := guard_finanzas_consulta(request)) is not None:
        return redir
    return templates.TemplateResponse(
        "finanzas/hub.html",
        {
            "request": request,
            "msg": msg,
            "sev": sev,
            "active_menu": "finanzas_hub",
        },
        status_code=status.HTTP_200_OK,
    )


@router.get("/finanzas/dashboard", response_class=HTMLResponse, name="fin_dashboard")
def fin_dashboard(
    request: Request,
    msg: str | None = Query(None),
    sev: str = Query("info"),
    db: Session = Depends(get_db),
):
    if (redir := guard_finanzas_consulta(request)) is not None:
        return redir
    kpis = crud_dashboard.get_kpis(db)
    aging = crud_dashboard.get_aging(db, limit=80)
    docs_recientes = crud_dashboard.get_docs_recientes(db, limit=20)
    resumen_estado = crud_dashboard.get_resumen_por_estado(db)
    top_proveedores = crud_dashboard.get_top_proveedores_saldo(db, limit=10)
    flujo_caja = crud_dashboard.get_flujo_caja_efectivo(db)
    movimientos_caja = crud_dashboard.get_movimientos_caja_recientes(db, limit=18)
    tesoreria_cajas = crud_dashboard.get_tesoreria_cajas(db)
    tesoreria_contable = crud_dashboard.get_tesoreria_efectivo_bancos_contable(db)
    tesoreria_banco = crud_dashboard.get_tesoreria_banco_cartola(db, limite_movs=10)
    ratios_financieros = crud_dashboard.get_ratios_financieros(db)

    return templates.TemplateResponse(
        "dashboard/fin_dashboard.html",
        {
            "request": request,
            "kpis": kpis,
            "aging": aging,
            "docs_recientes": docs_recientes,
            "resumen_estado": resumen_estado,
            "top_proveedores": top_proveedores,
            "flujo_caja": flujo_caja,
            "movimientos_caja": movimientos_caja,
            "tesoreria_cajas": tesoreria_cajas,
            "tesoreria_contable": tesoreria_contable,
            "tesoreria_banco": tesoreria_banco,
            "ratios_financieros": ratios_financieros,
            "msg": msg,
            "sev": sev,
            "active_menu": "fin_dashboard",
        },
        status_code=status.HTTP_200_OK,
    )