# routes/ui/fin_periodos.py
# -*- coding: utf-8 -*-
from __future__ import annotations

from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, Form, Query, Request, status
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from core.paths import TEMPLATES_DIR
from core.rbac import guard_finanzas_consulta, guard_finanzas_mutacion
from crud.finanzas import periodos as crud_periodos
from db.session import get_db

router = APIRouter(tags=["Finanzas - Períodos"])
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))


def _redirect(
    request: Request,
    route_name: str,
    *,
    msg: str | None = None,
    sev: str = "info",
    status_code: int = status.HTTP_303_SEE_OTHER,
    **path_params: Any,
) -> RedirectResponse:
    url = str(request.url_for(route_name, **path_params))
    if msg:
        sep = "&" if "?" in url else "?"
        url = f"{url}{sep}msg={msg}&sev={sev}"
    return RedirectResponse(url=url, status_code=status_code)


@router.get("/finanzas/periodos", response_class=HTMLResponse, name="fin_periodos")
def fin_periodos(
    request: Request,
    msg: str | None = Query(None),
    sev: str = Query("info"),
    db: Session = Depends(get_db),
):
    if (redir := guard_finanzas_consulta(request)) is not None:
        return redir
    hoy = datetime.now()
    crud_periodos.ensure_periodos_rango(
        db=db,
        anio_ini=hoy.year - 1,
        mes_ini=1,
        anio_fin=hoy.year + 1,
        mes_fin=12,
    )

    periodos = crud_periodos.list_periodos(db, limit=60)

    return templates.TemplateResponse(
        "finanzas/fin_periodos.html",
        {
            "request": request,
            "periodos": periodos,
            "anio_actual": hoy.year,
            "mes_actual": hoy.month,
            "msg": msg,
            "sev": sev,
            "active_menu": "fin_periodos",
        },
    )


@router.post("/finanzas/periodos/generar", name="fin_periodos_generar")
def fin_periodos_generar(
    request: Request,
    anio_ini: int = Form(...),
    mes_ini: int = Form(...),
    anio_fin: int = Form(...),
    mes_fin: int = Form(...),
    db: Session = Depends(get_db),
):
    if (redir := guard_finanzas_mutacion(request)) is not None:
        return redir
    try:
        crud_periodos.ensure_periodos_rango(
            db=db,
            anio_ini=anio_ini,
            mes_ini=mes_ini,
            anio_fin=anio_fin,
            mes_fin=mes_fin,
        )
    except Exception:
        return _redirect(
            request,
            "fin_periodos",
            msg="No fue posible generar el rango de períodos.",
            sev="danger",
        )

    return _redirect(
        request,
        "fin_periodos",
        msg="Períodos generados correctamente.",
        sev="success",
    )


@router.post("/finanzas/periodos/cerrar", name="fin_periodos_cerrar")
def fin_periodos_cerrar(
    request: Request,
    anio: int = Form(...),
    mes: int = Form(...),
    notas: str | None = Form(None),
    db: Session = Depends(get_db),
):
    if (redir := guard_finanzas_mutacion(request)) is not None:
        return redir
    try:
        crud_periodos.cerrar_periodo(
            db=db,
            anio=anio,
            mes=mes,
            user_email="sistema@evalua.local",
            notas=notas,
        )
    except Exception:
        return _redirect(
            request,
            "fin_periodos",
            msg=f"No fue posible cerrar el período {anio}-{mes:02d}.",
            sev="danger",
        )

    return _redirect(
        request,
        "fin_periodos",
        msg=f"Período {anio}-{mes:02d} cerrado correctamente.",
        sev="success",
    )


@router.post("/finanzas/periodos/abrir", name="fin_periodos_abrir")
def fin_periodos_abrir(
    request: Request,
    anio: int = Form(...),
    mes: int = Form(...),
    notas: str | None = Form(None),
    db: Session = Depends(get_db),
):
    if (redir := guard_finanzas_mutacion(request)) is not None:
        return redir
    try:
        crud_periodos.abrir_periodo(
            db=db,
            anio=anio,
            mes=mes,
            user_email="sistema@evalua.local",
            notas=notas,
        )
    except Exception:
        return _redirect(
            request,
            "fin_periodos",
            msg=f"No fue posible reabrir el período {anio}-{mes:02d}.",
            sev="danger",
        )

    return _redirect(
        request,
        "fin_periodos",
        msg=f"Período {anio}-{mes:02d} reabierto correctamente.",
        sev="success",
    )