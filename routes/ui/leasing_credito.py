# routes/ui/leasing_credito.py
# -*- coding: utf-8 -*-
from __future__ import annotations

from decimal import Decimal

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile, status
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from core.rbac import guard_leasing_fin_consulta, guard_leasing_fin_mutacion
from core.paths import TEMPLATES_DIR
from crud.comercial import leasing_credito as crud_credito
from db.session import get_db
from schemas.comercial.leasing_credito import LeasingCreditoInput
from services.leasing_credito_documentos import (
    ETIQUETAS_DOCUMENTO,
    TIPOS_DOCUMENTO,
    merge_extracciones,
    parse_documento,
    save_upload_bytes,
)
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


def _usuario_request(request: Request) -> str:
    user = getattr(request.state, "user", None)
    if user is None:
        return "sistema"
    return str(getattr(user, "email", None) or getattr(user, "nombre", None) or "sistema")


@router.get("/", response_class=HTMLResponse, name="lf_credito_home")
def lf_credito_home(request: Request, db: Session = Depends(get_db)):
    if (redir := guard_leasing_fin_consulta(request)) is not None:
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
    if (redir := guard_leasing_fin_consulta(request)) is not None:
        return redir
    cotizacion = crud_credito.get_cotizacion(db, cotizacion_id)
    if not cotizacion:
        raise HTTPException(status_code=404, detail="Cotización no encontrada")
    documentos = crud_credito.listar_documentos(db, cotizacion_id)
    msg = (request.query_params.get("msg") or "").strip()
    err = (request.query_params.get("err") or "").strip()
    return templates.TemplateResponse(
        "comercial/leasing_financiero/credito_form.html",
        {
            "request": request,
            "cotizacion": cotizacion,
            "analisis": cotizacion.analisis_credito,
            "documentos": documentos,
            "tipos_documento": TIPOS_DOCUMENTO,
            "etiquetas_documento": ETIQUETAS_DOCUMENTO,
            "msg": msg,
            "err": err,
            "active_menu": "leasing_financiero",
        },
    )


@router.post("/{cotizacion_id}/documentos", name="lf_credito_documento_upload")
async def lf_credito_documento_upload(
    request: Request,
    cotizacion_id: int,
    tipo_documento: str = Form("CARPETA_TRIBUTARIA"),
    archivo: UploadFile = File(...),
    observaciones: str = Form(""),
    aplicar_extraccion: str = Form("1"),
    db: Session = Depends(get_db),
):
    if (redir := guard_leasing_fin_mutacion(request)) is not None:
        return redir
    cotizacion = crud_credito.get_cotizacion(db, cotizacion_id)
    if not cotizacion:
        raise HTTPException(status_code=404, detail="Cotización no encontrada")

    tipo = (tipo_documento or "OTRO").strip().upper()
    if tipo not in TIPOS_DOCUMENTO:
        tipo = "OTRO"
    filename = archivo.filename or "documento.bin"
    content = await archivo.read()
    if not content:
        return RedirectResponse(
            url=str(request.url_for("lf_credito_form", cotizacion_id=cotizacion_id)) + "?err=archivo_vacio",
            status_code=status.HTTP_303_SEE_OTHER,
        )

    try:
        _path, rel, digest = save_upload_bytes(
            cotizacion_id=cotizacion_id,
            tipo_documento=tipo,
            filename=filename,
            content=content,
        )
    except ValueError as exc:
        return RedirectResponse(
            url=str(request.url_for("lf_credito_form", cotizacion_id=cotizacion_id))
            + f"?err={str(exc)[:120]}",
            status_code=status.HTTP_303_SEE_OTHER,
        )

    extraccion = parse_documento(content, filename, tipo)
    usuario = _usuario_request(request)
    crud_credito.crear_documento(
        db,
        cotizacion=cotizacion,
        tipo_documento=tipo,
        nombre_archivo=filename,
        mime_type=archivo.content_type or "application/octet-stream",
        storage_path=rel,
        hash_sha256=digest,
        tamano_bytes=len(content),
        datos_extraidos=extraccion.to_dict(),
        observaciones=(observaciones or "").strip(),
        cargado_por=usuario,
    )

    if (aplicar_extraccion or "1").strip() in {"1", "true", "on", "yes"} and extraccion.campos:
        crud_credito.aplicar_datos_extraidos_a_analisis(
            db,
            cotizacion=cotizacion,
            campos=extraccion.campos,
            analista=usuario,
        )

    msg = "documento_cargado"
    if extraccion.campos:
        msg = "documento_cargado_con_datos"
    return RedirectResponse(
        url=str(request.url_for("lf_credito_form", cotizacion_id=cotizacion_id)) + f"?msg={msg}",
        status_code=status.HTTP_303_SEE_OTHER,
    )


@router.post("/{cotizacion_id}/aplicar-documentos", name="lf_credito_aplicar_documentos")
def lf_credito_aplicar_documentos(
    request: Request,
    cotizacion_id: int,
    db: Session = Depends(get_db),
):
    if (redir := guard_leasing_fin_mutacion(request)) is not None:
        return redir
    cotizacion = crud_credito.get_cotizacion(db, cotizacion_id)
    if not cotizacion:
        raise HTTPException(status_code=404, detail="Cotización no encontrada")
    docs = crud_credito.listar_documentos(db, cotizacion_id)
    # más antiguo primero → el reciente sobrescribe
    datos = list(reversed([d.datos_extraidos or {} for d in docs]))
    campos = merge_extracciones(datos)
    if not campos:
        return RedirectResponse(
            url=str(request.url_for("lf_credito_form", cotizacion_id=cotizacion_id)) + "?err=sin_datos_extraidos",
            status_code=status.HTTP_303_SEE_OTHER,
        )
    crud_credito.aplicar_datos_extraidos_a_analisis(
        db,
        cotizacion=cotizacion,
        campos=campos,
        analista=_usuario_request(request),
    )
    return RedirectResponse(
        url=str(request.url_for("lf_credito_form", cotizacion_id=cotizacion_id)) + "?msg=datos_aplicados",
        status_code=status.HTTP_303_SEE_OTHER,
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
    activo_corriente: str = Form("0"),
    pasivo_corriente: str = Form("0"),
    activo_total: str = Form("0"),
    pasivo_total: str = Form("0"),
    utilidad_neta_anual: str = Form("0"),
    gastos_financieros_anual: str = Form("0"),
    ventas_12m_iva: str = Form("0"),
    iva_debito_12m: str = Form("0"),
    iva_credito_12m: str = Form("0"),
    score_buro: str = Form(""),
    comportamiento_pago: str = Form("SIN_HISTORIAL"),
    ltv_pct: str = Form("0"),
    supuestos: str = Form(""),
    db: Session = Depends(get_db),
):
    if (redir := guard_leasing_fin_mutacion(request)) is not None:
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
        activo_corriente=_parse_decimal(activo_corriente),
        pasivo_corriente=_parse_decimal(pasivo_corriente),
        activo_total=_parse_decimal(activo_total),
        pasivo_total=_parse_decimal(pasivo_total),
        utilidad_neta_anual=_parse_decimal(utilidad_neta_anual),
        gastos_financieros_anual=_parse_decimal(gastos_financieros_anual),
        ventas_12m_iva=_parse_decimal(ventas_12m_iva),
        iva_debito_12m=_parse_decimal(iva_debito_12m),
        iva_credito_12m=_parse_decimal(iva_credito_12m),
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
        analista=_usuario_request(request),
    )
    return RedirectResponse(
        url=str(request.url_for("lf_credito_form", cotizacion_id=cotizacion_id)) + "?msg=scoring_ok",
        status_code=status.HTTP_303_SEE_OTHER,
    )
