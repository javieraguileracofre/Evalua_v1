# routes/ui/leasing_credito.py
# -*- coding: utf-8 -*-
from __future__ import annotations

from decimal import Decimal

from fastapi import APIRouter, Depends, Form, HTTPException, Request, status
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from core.rbac import guard_operacion_consulta, guard_operacion_mutacion
from core.paths import TEMPLATES_DIR
from crud.comercial import leasing_credito as crud_credito
from db.session import get_db
from schemas.comercial.leasing_credito import LeasingCreditoInput
from services.leasing_credito_scoring import evaluar_credito

router = APIRouter(prefix="/comercial/leasing/credito", tags=["Comercial · Crédito leasing"])
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))


def _parse_decimal(raw: str | None, default: str = "0") -> Decimal:
    v = str(raw or "").strip()
    if not v:
        return Decimal(default)
    if "," in v:
        v = v.replace(".", "").replace(",", ".")
    try:
        return Decimal(v)
    except Exception:
        return Decimal(default)


def _parse_int(raw: str | None, default: int = 0) -> int:
    try:
        return int(str(raw or "").strip())
    except Exception:
        return default


@router.get("/", response_class=HTMLResponse, name="lf_credito_home")
def lf_credito_home(request: Request, db: Session = Depends(get_db)):
    if (redir := guard_operacion_consulta(request)) is not None:
        return redir
    estado = (request.query_params.get("estado") or "EN_ANALISIS_CREDITO").strip().upper()
    recomendacion = (request.query_params.get("recomendacion") or "").strip().upper() or None
    cotizaciones = crud_credito.listar_cotizaciones_para_credito(
        db,
        limit=250,
        estado=estado if estado != "TODOS" else None,
        recomendacion=recomendacion,
    )
    return templates.TemplateResponse(
        "comercial/leasing_financiero/credito_home.html",
        {
            "request": request,
            "cotizaciones": cotizaciones,
            "filtros": {"estado": estado, "recomendacion": recomendacion or ""},
            "active_menu": "leasing_financiero",
        },
    )


@router.get("/{cotizacion_id}", response_class=HTMLResponse, name="lf_credito_form")
def lf_credito_form(
    request: Request,
    cotizacion_id: int,
    db: Session = Depends(get_db),
):
    if (redir := guard_operacion_consulta(request)) is not None:
        return redir
    cotizacion = crud_credito.get_cotizacion(db, cotizacion_id)
    if not cotizacion:
        raise HTTPException(status_code=404, detail="Cotización no encontrada")
    return templates.TemplateResponse(
        "comercial/leasing_financiero/credito_form.html",
        {
            "request": request,
            "cotizacion": cotizacion,
            "analisis": cotizacion.analisis_credito,
            "active_menu": "leasing_financiero",
        },
    )


@router.post("/{cotizacion_id}/calcular", name="lf_credito_calcular")
def lf_credito_calcular(
    request: Request,
    cotizacion_id: int,
    tipo_persona: str = Form("NATURAL"),
    moneda_referencia: str = Form("CLP"),
    ingreso_neto_mensual: str = Form("0"),
    carga_financiera_mensual: str = Form("0"),
    antiguedad_laboral_meses: str = Form("0"),
    ventas_anuales: str = Form("0"),
    ebitda_anual: str = Form("0"),
    deuda_financiera_total: str = Form("0"),
    patrimonio: str = Form("0"),
    anios_operacion: str = Form("0"),
    score_buro: str = Form(""),
    comportamiento_pago: str = Form("SIN_HISTORIAL"),
    ltv_pct: str = Form("0"),
    supuestos: str = Form(""),
    db: Session = Depends(get_db),
):
    if (redir := guard_operacion_mutacion(request)) is not None:
        return redir
    cotizacion = crud_credito.get_cotizacion(db, cotizacion_id)
    if not cotizacion:
        raise HTTPException(status_code=404, detail="Cotización no encontrada")

    score_buro_val = _parse_int(score_buro, 0) if str(score_buro or "").strip() else None
    payload = LeasingCreditoInput(
        tipo_persona="JURIDICA" if str(tipo_persona).strip().upper() == "JURIDICA" else "NATURAL",
        tipo_producto="leasing_financiero",
        moneda_referencia=(moneda_referencia or "CLP").strip().upper() or "CLP",
        ingreso_neto_mensual=_parse_decimal(ingreso_neto_mensual),
        carga_financiera_mensual=_parse_decimal(carga_financiera_mensual),
        antiguedad_laboral_meses=max(0, _parse_int(antiguedad_laboral_meses, 0)),
        ventas_anuales=_parse_decimal(ventas_anuales),
        ebitda_anual=_parse_decimal(ebitda_anual),
        deuda_financiera_total=_parse_decimal(deuda_financiera_total),
        patrimonio=_parse_decimal(patrimonio),
        anios_operacion=max(0, _parse_int(anios_operacion, 0)),
        score_buro=score_buro_val,
        comportamiento_pago=str(comportamiento_pago or "SIN_HISTORIAL").strip().upper(),
        ltv_pct=_parse_decimal(ltv_pct),
        supuestos=(supuestos or "").strip(),
    )
    resultado = evaluar_credito(payload)

    crud_credito.upsert_analisis(
        db,
        cotizacion=cotizacion,
        data=payload,
        resultado=resultado,
        analista="sistema",
    )
    return RedirectResponse(
        url=str(request.url_for("lf_credito_form", cotizacion_id=cotizacion_id)),
        status_code=status.HTTP_303_SEE_OTHER,
    )
