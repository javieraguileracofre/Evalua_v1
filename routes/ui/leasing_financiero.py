# routes/ui/leasing_financiero.py
# -*- coding: utf-8 -*-
from __future__ import annotations

import logging
from datetime import date
from decimal import Decimal
from typing import List, Optional

from fastapi import APIRouter, Depends, Form, HTTPException, Request, status
from fastapi.responses import HTMLResponse, RedirectResponse, StreamingResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from core.rbac import guard_operacion_consulta, guard_operacion_mutacion
from core.paths import TEMPLATES_DIR
from crud.comercial import leasing_fin as crud_lf
from crud.maestros import cliente as crud_cliente
from db.session import get_db
from schemas.comercial.leasing_amortizacion import AmortizacionCuota
from schemas.comercial.leasing_cotizacion import (
    LeasingCotizacionCreate,
    LeasingCotizacionRead,
    LeasingCotizacionUpdate,
)
from services import leasing_financiero
from services.indicadores_mercado import obtener_uf_dolar_hoy
from services.leasing_financiero_export import build_amortizacion_excel, build_amortizacion_pdf

router = APIRouter(prefix="/comercial/leasing/cotizaciones", tags=["Comercial · Leasing financiero"])
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))
logger = logging.getLogger("evalua.leasing_financiero.ui")


def _parse_decimal(value: str) -> Optional[Decimal]:
    value = (value or "").strip()
    if not value:
        return None
    # Soporta formatos: 1234.56, 1,234.56, 1.234,56, 1234,56
    if "," in value and "." in value:
        if value.rfind(",") > value.rfind("."):
            # 1.234,56 -> 1234.56
            value = value.replace(".", "").replace(",", ".")
        else:
            # 1,234.56 -> 1234.56
            value = value.replace(",", "")
    elif "," in value:
        value = value.replace(".", "").replace(",", ".")
    try:
        return Decimal(value)
    except Exception:
        return None


def _parse_int(value: str) -> Optional[int]:
    value = (value or "").strip()
    if not value:
        return None
    try:
        return int(value)
    except Exception:
        return None


def _parse_date(value: str) -> Optional[date]:
    value = (value or "").strip()
    if not value:
        return None
    try:
        return date.fromisoformat(value)
    except Exception:
        return None


def _parse_bool(value: object) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return False
    s = str(value).strip().lower()
    return s in ("1", "true", "t", "yes", "y", "si", "sí", "on")


def _normalizar_estado(value: str | None) -> str:
    if not value:
        return "BORRADOR"
    v = str(value).strip().upper()
    validos = {
        "BORRADOR",
        "COTIZADA",
        "EN_ANALISIS_COMERCIAL",
        "EN_ANALISIS_CREDITO",
        "APROBADA_CONDICIONES",
        "APROBADA",
        "EN_FORMALIZACION",
        "DOCUMENTACION_COMPLETA",
        "ACTIVADA",
        "VIGENTE",
        "RECHAZADA",
        "PERDIDA_CLIENTE",
        "ANULADA",
    }
    return v if v in validos else "BORRADOR"


def _normalizar_moneda(value: str | None) -> str:
    v = str(value or "CLP").strip().upper()
    return v if v in {"CLP", "USD", "UF"} else "CLP"


def _validar_fx_moneda(moneda: str, uf_valor: Optional[Decimal], dolar_valor: Optional[Decimal]) -> None:
    if moneda == "USD" and (dolar_valor is None or dolar_valor <= 0):
        raise ValueError("Para cotizar en USD debe informar Valor dólar mayor a 0.")
    if moneda == "UF" and (uf_valor is None or uf_valor <= 0):
        raise ValueError("Para cotizar en UF debe informar Valor UF mayor a 0.")


@router.get("/hub", response_class=HTMLResponse, name="leasing_financiero_hub_internal", include_in_schema=False)
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


@router.get("/api/rates/today")
def api_lf_rates_today():
    try:
        return obtener_uf_dolar_hoy()
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"No fue posible obtener UF/USD: {exc}") from exc


@router.get("/", response_class=HTMLResponse, name="lf_cotizaciones_list")
def lf_cotizaciones_list(request: Request, db: Session = Depends(get_db)):
    if (redir := guard_operacion_consulta(request)) is not None:
        return redir
    estado = _normalizar_estado(request.query_params.get("estado")) if request.query_params.get("estado") else None
    moneda = _normalizar_moneda(request.query_params.get("moneda")) if request.query_params.get("moneda") else None
    ejecutivo = (request.query_params.get("ejecutivo") or "").strip() or None
    fecha_desde = _parse_date(request.query_params.get("fecha_desde") or "")
    fecha_hasta = _parse_date(request.query_params.get("fecha_hasta") or "")
    cotizaciones = crud_lf.get_cotizaciones(
        db,
        estado=estado,
        moneda=moneda,
        ejecutivo=ejecutivo,
        fecha_desde=fecha_desde,
        fecha_hasta=fecha_hasta,
        limit=500,
    )
    return templates.TemplateResponse(
        "comercial/leasing_financiero/cotizaciones_list.html",
        {
            "request": request,
            "cotizaciones": cotizaciones,
            "filtros": {
                "estado": estado or "",
                "moneda": moneda or "",
                "ejecutivo": ejecutivo or "",
                "fecha_desde": request.query_params.get("fecha_desde") or "",
                "fecha_hasta": request.query_params.get("fecha_hasta") or "",
            },
            "active_menu": "leasing_financiero",
        },
    )


@router.get("/nueva", response_class=HTMLResponse, name="lf_cotizacion_nueva_form")
def lf_cotizacion_nueva_form(
    request: Request,
    cliente_id: int | None = None,
    db: Session = Depends(get_db),
):
    if (redir := guard_operacion_mutacion(request)) is not None:
        return redir
    clientes, _hay_mas = crud_cliente.listar_clientes(db, activos_solo=False, busqueda=None, skip=0, limit=500)
    has_clientes = bool(clientes)

    cliente = None
    if cliente_id:
        cliente = crud_cliente.get_cliente(db, cliente_id)
        if not cliente:
            raise HTTPException(status_code=404, detail="Cliente no encontrado")

    return templates.TemplateResponse(
        "comercial/leasing_financiero/form_cotizacion.html",
        {
            "request": request,
            "cliente": cliente,
            "clientes": clientes,
            "cliente_id": cliente_id,
            "has_clientes": has_clientes,
            "moneda_default": "CLP",
            "active_menu": "leasing_financiero",
        },
    )


@router.post("/nueva", name="lf_cotizacion_nueva_post")
def lf_cotizacion_nueva_post(
    request: Request,
    db: Session = Depends(get_db),
    cliente_id: int = Form(...),
    monto: str = Form(""),
    moneda: str = Form("CLP"),
    tasa: str = Form(""),
    plazo: str = Form(""),
    opcion_compra: str = Form(""),
    periodos_gracia: str = Form(""),
    fecha_inicio: str = Form(""),
    valor_neto: str = Form(""),
    pago_inicial_tipo: str = Form(""),
    pago_inicial_valor: str = Form(""),
    financia_seguro: object = Form(False),
    seguro_monto_uf: str = Form(""),
    otros_montos_pesos: str = Form(""),
    concesionario: str = Form(""),
    ejecutivo: str = Form(""),
    fecha_cotizacion: str = Form(""),
    uf_valor: str = Form(""),
    monto_financiado: str = Form(""),
    dolar_valor: str = Form(""),
):
    if (redir := guard_operacion_mutacion(request)) is not None:
        return redir
    cliente = crud_cliente.get_cliente(db, cliente_id)
    if not cliente:
        raise HTTPException(status_code=404, detail="Cliente no encontrado")

    moneda_norm = _normalizar_moneda(moneda)
    uf_val = _parse_decimal(uf_valor)
    usd_val = _parse_decimal(dolar_valor)
    _validar_fx_moneda(moneda_norm, uf_val, usd_val)

    obj_in = LeasingCotizacionCreate(
        cliente_id=int(cliente.id),
        monto=_parse_decimal(monto),
        moneda=moneda_norm,
        tasa=_parse_decimal(tasa),
        plazo=_parse_int(plazo),
        opcion_compra=_parse_decimal(opcion_compra),
        periodos_gracia=_parse_int(periodos_gracia) or 0,
        fecha_inicio=_parse_date(fecha_inicio),
        valor_neto=_parse_decimal(valor_neto),
        pago_inicial_tipo=(pago_inicial_tipo or None),
        pago_inicial_valor=_parse_decimal(pago_inicial_valor),
        financia_seguro=_parse_bool(financia_seguro),
        seguro_monto_uf=_parse_decimal(seguro_monto_uf),
        otros_montos_pesos=_parse_decimal(otros_montos_pesos),
        concesionario=(concesionario or None),
        ejecutivo=(ejecutivo or None),
        fecha_cotizacion=_parse_date(fecha_cotizacion),
        uf_valor=uf_val,
        monto_financiado=_parse_decimal(monto_financiado),
        dolar_valor=usd_val,
        estado=_normalizar_estado("BORRADOR"),
        contrato_activo=False,
    )

    try:
        cotizacion = crud_lf.crear_cotizacion(db, obj_in=obj_in)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except SQLAlchemyError as exc:
        logger.exception("Error SQL al crear cotización LF (cliente_id=%s)", cliente_id)
        raise HTTPException(
            status_code=503,
            detail="No fue posible crear la cotización por un problema de base de datos. Verifique migraciones de leasing financiero.",
        ) from exc
    except Exception as exc:
        logger.exception("Error inesperado al crear cotización LF (cliente_id=%s)", cliente_id)
        raise HTTPException(
            status_code=500,
            detail="No fue posible crear la cotización en este momento. Intente nuevamente.",
        ) from exc

    return RedirectResponse(
        url=str(request.url_for("lf_cotizacion_detalle", cotizacion_id=cotizacion.id)),
        status_code=status.HTTP_303_SEE_OTHER,
    )


@router.get(
    "/nuevo/{cliente_id}",
    response_class=HTMLResponse,
    name="lf_cotizacion_nueva_form_cliente",
    include_in_schema=False,
)
def lf_cotizacion_nueva_form_cliente(
    request: Request,
    cliente_id: int,
    db: Session = Depends(get_db),
):
    return lf_cotizacion_nueva_form(request=request, cliente_id=cliente_id, db=db)


@router.post(
    "/nuevo/{cliente_id}",
    name="lf_cotizacion_nueva_post_cliente",
    include_in_schema=False,
)
def lf_cotizacion_nueva_post_cliente(
    request: Request,
    cliente_id: int,
    db: Session = Depends(get_db),
    monto: str = Form(""),
    moneda: str = Form("CLP"),
    tasa: str = Form(""),
    plazo: str = Form(""),
    opcion_compra: str = Form(""),
    periodos_gracia: str = Form(""),
    fecha_inicio: str = Form(""),
    valor_neto: str = Form(""),
    pago_inicial_tipo: str = Form(""),
    pago_inicial_valor: str = Form(""),
    financia_seguro: object = Form(False),
    seguro_monto_uf: str = Form(""),
    otros_montos_pesos: str = Form(""),
    concesionario: str = Form(""),
    ejecutivo: str = Form(""),
    fecha_cotizacion: str = Form(""),
    uf_valor: str = Form(""),
    monto_financiado: str = Form(""),
    dolar_valor: str = Form(""),
):
    if (redir := guard_operacion_mutacion(request)) is not None:
        return redir
    return lf_cotizacion_nueva_post(
        request=request,
        db=db,
        cliente_id=cliente_id,
        monto=monto,
        moneda=moneda,
        tasa=tasa,
        plazo=plazo,
        opcion_compra=opcion_compra,
        periodos_gracia=periodos_gracia,
        fecha_inicio=fecha_inicio,
        valor_neto=valor_neto,
        pago_inicial_tipo=pago_inicial_tipo,
        pago_inicial_valor=pago_inicial_valor,
        financia_seguro=financia_seguro,
        seguro_monto_uf=seguro_monto_uf,
        otros_montos_pesos=otros_montos_pesos,
        concesionario=concesionario,
        ejecutivo=ejecutivo,
        fecha_cotizacion=fecha_cotizacion,
        uf_valor=uf_valor,
        monto_financiado=monto_financiado,
        dolar_valor=dolar_valor,
    )


@router.get("/api", response_model=List[LeasingCotizacionRead])
def api_lf_cotizaciones_list(
    db: Session = Depends(get_db),
    cliente_id: int | None = None,
    estado: str | None = None,
):
    items = crud_lf.get_cotizaciones(db, cliente_id=cliente_id, estado=estado)
    return [LeasingCotizacionRead.model_validate(c) for c in items]


@router.get("/api/{cotizacion_id}", response_model=LeasingCotizacionRead)
def api_lf_cotizacion_detalle(
    cotizacion_id: int,
    db: Session = Depends(get_db),
):
    cotizacion = crud_lf.get_cotizacion(db, cotizacion_id)
    if not cotizacion:
        raise HTTPException(status_code=404, detail="Cotización no encontrada")
    return LeasingCotizacionRead.model_validate(cotizacion)


@router.post("/api", response_model=LeasingCotizacionRead, status_code=status.HTTP_201_CREATED)
def api_lf_cotizacion_crear(
    obj_in: LeasingCotizacionCreate,
    db: Session = Depends(get_db),
):
    try:
        cotizacion = crud_lf.crear_cotizacion(db, obj_in=obj_in)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return LeasingCotizacionRead.model_validate(cotizacion)


@router.patch("/api/{cotizacion_id}", response_model=LeasingCotizacionRead)
def api_lf_cotizacion_actualizar(
    cotizacion_id: int,
    obj_in: LeasingCotizacionUpdate,
    db: Session = Depends(get_db),
):
    cotizacion = crud_lf.get_cotizacion(db, cotizacion_id)
    if not cotizacion:
        raise HTTPException(status_code=404, detail="Cotización no encontrada")

    try:
        cotizacion = crud_lf.actualizar_cotizacion(db, cotizacion=cotizacion, obj_in=obj_in)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return LeasingCotizacionRead.model_validate(cotizacion)


@router.get("/api/{cotizacion_id}/amortizacion", response_model=List[AmortizacionCuota])
def api_lf_cotizacion_amortizacion(
    cotizacion_id: int,
    db: Session = Depends(get_db),
):
    cotizacion = crud_lf.get_cotizacion(db, cotizacion_id)
    if not cotizacion:
        raise HTTPException(status_code=404, detail="Cotización no encontrada")

    return leasing_financiero.calcular_tabla_amortizacion(cotizacion)


@router.get("/{cotizacion_id}", response_class=HTMLResponse, name="lf_cotizacion_detalle")
def lf_cotizacion_detalle(
    request: Request,
    cotizacion_id: int,
    db: Session = Depends(get_db),
):
    if (redir := guard_operacion_consulta(request)) is not None:
        return redir
    cotizacion = crud_lf.get_cotizacion(db, cotizacion_id)
    if not cotizacion:
        raise HTTPException(status_code=404, detail="Cotización no encontrada")

    cotizaciones_cliente = crud_lf.listar_cotizaciones_por_cliente(db, cotizacion.cliente_id)
    workflow = crud_lf.obtener_workflow(cotizacion)
    documentos = crud_lf.listar_documentos_proceso(db, int(cotizacion.id))
    historial = crud_lf.listar_historial(db, int(cotizacion.id))

    return templates.TemplateResponse(
        "comercial/leasing_financiero/cotizacion_detalle.html",
        {
            "request": request,
            "cotizacion": cotizacion,
            "cotizaciones_cliente": cotizaciones_cliente,
            "workflow": workflow,
            "documentos_proceso": documentos,
            "historial": historial,
            "active_menu": "leasing_financiero",
        },
    )


@router.post("/{cotizacion_id}/workflow/sync-credito", name="lf_cotizacion_workflow_sync_credito")
def lf_cotizacion_workflow_sync_credito(
    request: Request,
    cotizacion_id: int,
    db: Session = Depends(get_db),
):
    if (redir := guard_operacion_mutacion(request)) is not None:
        return redir
    cotizacion = crud_lf.get_cotizacion(db, cotizacion_id)
    if not cotizacion:
        raise HTTPException(status_code=404, detail="Cotización no encontrada")
    try:
        crud_lf.sincronizar_hito_credito(db, cotizacion=cotizacion)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return RedirectResponse(
        url=str(request.url_for("lf_cotizacion_detalle", cotizacion_id=cotizacion_id)),
        status_code=status.HTTP_303_SEE_OTHER,
    )


@router.post("/{cotizacion_id}/workflow/documento/{modulo}", name="lf_cotizacion_workflow_documento")
def lf_cotizacion_workflow_documento(
    request: Request,
    cotizacion_id: int,
    modulo: str,
    tipo_documento: str = Form(""),
    numero_documento: str = Form(""),
    fecha_documento: str = Form(""),
    archivo_nombre: str = Form(""),
    storage_key: str = Form(""),
    estado_documento: str = Form("RECIBIDO"),
    observacion: str = Form(""),
    db: Session = Depends(get_db),
):
    if (redir := guard_operacion_mutacion(request)) is not None:
        return redir
    cotizacion = crud_lf.get_cotizacion(db, cotizacion_id)
    if not cotizacion:
        raise HTTPException(status_code=404, detail="Cotización no encontrada")
    payload = {
        "tipo_documento": (tipo_documento or "").strip().upper(),
        "numero_documento": (numero_documento or "").strip(),
        "fecha_documento": (fecha_documento or "").strip(),
        "archivo_nombre": (archivo_nombre or "").strip(),
        "storage_key": (storage_key or "").strip(),
        "estado": (estado_documento or "RECIBIDO").strip().upper(),
        "observacion": (observacion or "").strip(),
    }
    try:
        crud_lf.guardar_documento_proceso(
            db,
            cotizacion=cotizacion,
            modulo=modulo,
            payload=payload,
            usuario="ui",
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return RedirectResponse(
        url=str(request.url_for("lf_cotizacion_detalle", cotizacion_id=cotizacion_id)),
        status_code=status.HTTP_303_SEE_OTHER,
    )


@router.post("/{cotizacion_id}/workflow/activar", name="lf_cotizacion_workflow_activar")
def lf_cotizacion_workflow_activar(
    request: Request,
    cotizacion_id: int,
    db: Session = Depends(get_db),
):
    if (redir := guard_operacion_mutacion(request)) is not None:
        return redir
    cotizacion = crud_lf.get_cotizacion(db, cotizacion_id)
    if not cotizacion:
        raise HTTPException(status_code=404, detail="Cotización no encontrada")
    try:
        crud_lf.activar_flujo_contable(db, cotizacion=cotizacion, usuario="ui")
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return RedirectResponse(
        url=str(request.url_for("lf_cotizacion_detalle", cotizacion_id=cotizacion_id)),
        status_code=status.HTTP_303_SEE_OTHER,
    )


@router.get(
    "/{cotizacion_id}/amortizacion",
    response_class=HTMLResponse,
    name="lf_cotizacion_amortizacion",
)
def lf_cotizacion_amortizacion_view(
    request: Request,
    cotizacion_id: int,
    db: Session = Depends(get_db),
):
    if (redir := guard_operacion_consulta(request)) is not None:
        return redir
    cotizacion = crud_lf.get_cotizacion(db, cotizacion_id)
    if not cotizacion:
        raise HTTPException(status_code=404, detail="Cotización no encontrada")

    try:
        tabla = leasing_financiero.calcular_tabla_amortizacion(cotizacion)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    total_interes = sum((c.interes for c in tabla), Decimal("0.00"))
    total_cuotas = sum((c.cuota for c in tabla), Decimal("0.00"))

    return templates.TemplateResponse(
        "comercial/leasing_financiero/cotizacion_amortizacion.html",
        {
            "request": request,
            "cotizacion": cotizacion,
            "tabla": tabla,
            "total_interes": total_interes,
            "total_cuotas": total_cuotas,
            "active_menu": "leasing_financiero",
        },
    )


@router.get("/{cotizacion_id}/editar", response_class=HTMLResponse, name="lf_cotizacion_editar_form")
def lf_cotizacion_editar_form(
    request: Request,
    cotizacion_id: int,
    db: Session = Depends(get_db),
):
    if (redir := guard_operacion_mutacion(request)) is not None:
        return redir
    cotizacion = crud_lf.get_cotizacion(db, cotizacion_id)
    if not cotizacion:
        raise HTTPException(status_code=404, detail="Cotización no encontrada")
    return templates.TemplateResponse(
        "comercial/leasing_financiero/form_cotizacion_edit.html",
        {
            "request": request,
            "cotizacion": cotizacion,
            "active_menu": "leasing_financiero",
        },
    )


@router.post("/{cotizacion_id}/editar", name="lf_cotizacion_editar_post")
def lf_cotizacion_editar_post(
    request: Request,
    cotizacion_id: int,
    monto: str = Form(""),
    moneda: str = Form("CLP"),
    tasa: str = Form(""),
    plazo: str = Form(""),
    opcion_compra: str = Form(""),
    periodos_gracia: str = Form(""),
    fecha_inicio: str = Form(""),
    valor_neto: str = Form(""),
    monto_financiado: str = Form(""),
    estado: str = Form("BORRADOR"),
    uf_valor: str = Form(""),
    dolar_valor: str = Form(""),
    db: Session = Depends(get_db),
):
    if (redir := guard_operacion_mutacion(request)) is not None:
        return redir
    cotizacion = crud_lf.get_cotizacion(db, cotizacion_id)
    if not cotizacion:
        raise HTTPException(status_code=404, detail="Cotización no encontrada")
    obj = LeasingCotizacionUpdate(
        monto=_parse_decimal(monto),
        moneda=_normalizar_moneda(moneda),
        tasa=_parse_decimal(tasa),
        plazo=_parse_int(plazo),
        opcion_compra=_parse_decimal(opcion_compra),
        periodos_gracia=_parse_int(periodos_gracia),
        fecha_inicio=_parse_date(fecha_inicio),
        valor_neto=_parse_decimal(valor_neto),
        monto_financiado=_parse_decimal(monto_financiado),
        estado=_normalizar_estado(estado),
        uf_valor=_parse_decimal(uf_valor),
        dolar_valor=_parse_decimal(dolar_valor),
    )
    try:
        crud_lf.actualizar_cotizacion(db, cotizacion=cotizacion, obj_in=obj)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return RedirectResponse(
        url=str(request.url_for("lf_cotizacion_detalle", cotizacion_id=cotizacion_id)),
        status_code=status.HTTP_303_SEE_OTHER,
    )


@router.get("/{cotizacion_id}/amortizacion/excel", name="lf_cotizacion_amortizacion_excel")
def lf_cotizacion_amortizacion_excel(
    cotizacion_id: int,
    db: Session = Depends(get_db),
):
    cotizacion = crud_lf.get_cotizacion(db, cotizacion_id)
    if not cotizacion:
        raise HTTPException(status_code=404, detail="Cotización no encontrada")

    tabla = leasing_financiero.calcular_tabla_amortizacion(cotizacion)
    output = build_amortizacion_excel(cotizacion, tabla)

    filename = f"amortizacion_cotizacion_{cotizacion.id}.xlsx"
    headers = {"Content-Disposition": f'attachment; filename="{filename}"'}

    return StreamingResponse(
        output,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers=headers,
    )


@router.get("/{cotizacion_id}/amortizacion/pdf", name="lf_cotizacion_amortizacion_pdf")
def lf_cotizacion_amortizacion_pdf(
    cotizacion_id: int,
    db: Session = Depends(get_db),
):
    cotizacion = crud_lf.get_cotizacion(db, cotizacion_id)
    if not cotizacion:
        raise HTTPException(status_code=404, detail="Cotización no encontrada")

    tabla = leasing_financiero.calcular_tabla_amortizacion(cotizacion)
    try:
        output = build_amortizacion_pdf(cotizacion, tabla)
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail=str(e)) from e

    filename = f"amortizacion_cotizacion_{cotizacion.id}.pdf"
    headers = {"Content-Disposition": f'attachment; filename="{filename}"'}

    return StreamingResponse(
        output,
        media_type="application/pdf",
        headers=headers,
    )
