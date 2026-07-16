# routes/ui/leasing_financiero.py
# -*- coding: utf-8 -*-
from __future__ import annotations

import logging
import re
from datetime import date
from decimal import Decimal
from typing import List, Optional
from urllib.parse import urlencode

from fastapi import APIRouter, Depends, Form, HTTPException, Request, status
from fastapi.responses import HTMLResponse, RedirectResponse, StreamingResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from core.rbac import (
    guard_leasing_fin_aprobar,
    guard_leasing_fin_consulta,
    guard_leasing_fin_mutacion,
)
from core.paths import TEMPLATES_DIR
from crud.comercial import leasing_fin as crud_lf
from crud.maestros import cliente as crud_cliente
from models.maestros.proveedor import Proveedor
from sqlalchemy import select
from db.session import get_db
from schemas.comercial.leasing_amortizacion import AmortizacionCuota
from schemas.comercial.leasing_cotizacion import (
    ESTADOS_LF,
    LeasingCotizacionCreate,
    LeasingCotizacionRead,
    LeasingCotizacionUpdate,
    LeasingSimulacionInput,
    LeasingSimulacionResumen,
)
from services import leasing_financiero
from services.indicadores_mercado import obtener_uf_dolar_hoy
from services.leasing_financiero_export import build_amortizacion_excel, build_amortizacion_pdf

router = APIRouter(prefix="/comercial/leasing/cotizaciones", tags=["Comercial · Leasing financiero"])
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))
logger = logging.getLogger("evalua.leasing_financiero.ui")


def _parse_decimal(value: str, *, money: bool = False) -> Optional[Decimal]:
    if value is None or not isinstance(value, (str, int, float, Decimal)):
        return None
    value = (value or "").strip()
    if not value:
        return None
    value = value.replace(" ", "")

    # Campos monetarios: soporta miles con "." (es-CL) y "," (en-US)
    if money:
        if re.fullmatch(r"\d{1,3}(\.\d{3})+(,\d+)?", value):
            value = value.replace(".", "").replace(",", ".")
        elif re.fullmatch(r"\d{1,3}(,\d{3})+(\.\d+)?", value):
            value = value.replace(",", "")

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
    if value is None or not isinstance(value, (str, int)):
        return None
    value = (value or "").strip()
    if not value:
        return None
    try:
        return int(value)
    except Exception:
        return None


def _parse_date(value: str) -> Optional[date]:
    if not isinstance(value, str):
        value = "" if value is None else str(value)
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


def _normalizar_periodicidad(value: str | None) -> str:
    v = str(value or "MENSUAL").strip().upper()
    if v not in {"MENSUAL", "TRIMESTRAL", "SEMESTRAL", "ANUAL"}:
        return "MENSUAL"
    return v


def _cotizacion_a_simulacion(cotizacion) -> LeasingSimulacionInput:
    return LeasingSimulacionInput(
        moneda=str(cotizacion.moneda or "CLP"),
        tasa=cotizacion.tasa,
        plazo=cotizacion.plazo,
        opcion_compra=cotizacion.opcion_compra,
        periodos_gracia=cotizacion.periodos_gracia or 0,
        periodicidad=_normalizar_periodicidad(getattr(cotizacion, "periodicidad", "MENSUAL")),
        fecha_inicio=cotizacion.fecha_inicio,
        fecha_primera_cuota=getattr(cotizacion, "fecha_primera_cuota", None),
        valor_neto=cotizacion.valor_neto,
        pago_inicial_tipo=cotizacion.pago_inicial_tipo,
        pago_inicial_valor=cotizacion.pago_inicial_valor,
        financia_seguro=bool(cotizacion.financia_seguro),
        seguro_monto_uf=cotizacion.seguro_monto_uf,
        otros_montos_pesos=cotizacion.otros_montos_pesos,
        comision_apertura=getattr(cotizacion, "comision_apertura", None),
        comision_apertura_tipo=getattr(cotizacion, "comision_apertura_tipo", None),
        financia_comision=bool(getattr(cotizacion, "financia_comision", False)),
        gastos_operacionales=getattr(cotizacion, "gastos_operacionales", None),
        iva_aplica=bool(getattr(cotizacion, "iva_aplica", False)),
        iva_tasa=getattr(cotizacion, "iva_tasa", None),
        iva_recuperable=bool(getattr(cotizacion, "iva_recuperable", True)),
        uf_valor=cotizacion.uf_valor,
        monto_financiado=cotizacion.monto_financiado,
        dolar_valor=cotizacion.dolar_valor,
    )


def _validar_fx_moneda(moneda: str, uf_valor: Optional[Decimal], dolar_valor: Optional[Decimal]) -> None:
    if moneda == "USD" and (dolar_valor is None or dolar_valor <= 0):
        raise ValueError("Para cotizar en USD debe informar Valor dólar mayor a 0.")
    if moneda == "UF" and (uf_valor is None or uf_valor <= 0):
        raise ValueError("Para cotizar en UF debe informar Valor UF mayor a 0.")


def _redirect_cotizaciones_list(
    request: Request,
    *,
    msg: str | None = None,
    sev: str = "info",
    estado: str | None = None,
    moneda: str | None = None,
    ejecutivo: str | None = None,
    fecha_desde: str | None = None,
    fecha_hasta: str | None = None,
) -> RedirectResponse:
    url = str(request.url_for("lf_cotizaciones_list"))
    params: dict[str, str] = {}
    for key, value in (
        ("estado", estado),
        ("moneda", moneda),
        ("ejecutivo", ejecutivo),
        ("fecha_desde", fecha_desde),
        ("fecha_hasta", fecha_hasta),
    ):
        if value:
            params[key] = value
    if msg:
        params["msg"] = msg
        params["sev"] = sev
    if params:
        url = f"{url}?{urlencode(params)}"
    return RedirectResponse(url=url, status_code=status.HTTP_303_SEE_OTHER)


@router.get("/hub", response_class=HTMLResponse, name="leasing_financiero_hub_internal", include_in_schema=False)
def leasing_financiero_hub(request: Request, db: Session = Depends(get_db)):
    if (redir := guard_leasing_fin_consulta(request)) is not None:
        return redir
    resumen = crud_lf.get_hub_resumen(db)
    mercado = None
    try:
        mercado = obtener_uf_dolar_hoy()
    except Exception:
        mercado = None
    return templates.TemplateResponse(
        "comercial/leasing_financiero/hub.html",
        {
            "request": request,
            **resumen,
            "mercado": mercado,
            "active_menu": "leasing_financiero",
        },
    )


@router.get("/api/rates/today", name="api_lf_rates_today")
def api_lf_rates_today():
    try:
        return obtener_uf_dolar_hoy()
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"No fue posible obtener UF/USD: {exc}") from exc


@router.get("/", response_class=HTMLResponse, name="lf_cotizaciones_list")
def lf_cotizaciones_list(request: Request, db: Session = Depends(get_db)):
    if (redir := guard_leasing_fin_consulta(request)) is not None:
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


@router.post("/eliminar-masivo", name="lf_cotizaciones_eliminar_masivo")
def lf_cotizaciones_eliminar_masivo(
    request: Request,
    ids: List[int] = Form(default=[]),
    estado: str = Form(""),
    moneda: str = Form(""),
    ejecutivo: str = Form(""),
    fecha_desde: str = Form(""),
    fecha_hasta: str = Form(""),
    db: Session = Depends(get_db),
):
    if (redir := guard_leasing_fin_mutacion(request)) is not None:
        return redir
    filtros = {
        "estado": estado,
        "moneda": moneda,
        "ejecutivo": ejecutivo,
        "fecha_desde": fecha_desde,
        "fecha_hasta": fecha_hasta,
    }
    try:
        resultado = crud_lf.eliminar_cotizaciones(db, ids=ids)
    except ValueError as exc:
        return _redirect_cotizaciones_list(request, msg=str(exc), sev="warning", **filtros)
    except SQLAlchemyError as exc:
        logger.exception("Error SQL al eliminar cotizaciones LF masivamente")
        return _redirect_cotizaciones_list(
            request,
            msg="No fue posible eliminar las cotizaciones por un problema de base de datos.",
            sev="danger",
            **filtros,
        )

    eliminadas = int(resultado.get("eliminadas") or 0)
    bloqueadas = int(resultado.get("bloqueadas") or 0)
    if bloqueadas:
        msg = (
            f"Se eliminaron {eliminadas} cotización(es). "
            f"{bloqueadas} no se eliminaron por estar activadas o vigentes."
        )
        sev = "warning"
    else:
        msg = f"Se eliminaron {eliminadas} cotización(es) correctamente."
        sev = "success"
    return _redirect_cotizaciones_list(request, msg=msg, sev=sev, **filtros)


@router.post("/{cotizacion_id}/eliminar", name="lf_cotizacion_eliminar")
def lf_cotizacion_eliminar(
    request: Request,
    cotizacion_id: int,
    estado: str = Form(""),
    moneda: str = Form(""),
    ejecutivo: str = Form(""),
    fecha_desde: str = Form(""),
    fecha_hasta: str = Form(""),
    db: Session = Depends(get_db),
):
    if (redir := guard_leasing_fin_mutacion(request)) is not None:
        return redir
    filtros = {
        "estado": estado,
        "moneda": moneda,
        "ejecutivo": ejecutivo,
        "fecha_desde": fecha_desde,
        "fecha_hasta": fecha_hasta,
    }
    try:
        resultado = crud_lf.eliminar_cotizaciones(db, ids=[cotizacion_id])
    except ValueError as exc:
        return _redirect_cotizaciones_list(request, msg=str(exc), sev="warning", **filtros)
    except SQLAlchemyError:
        logger.exception("Error SQL al eliminar cotización LF #%s", cotizacion_id)
        return _redirect_cotizaciones_list(
            request,
            msg="No fue posible eliminar la cotización por un problema de base de datos.",
            sev="danger",
            **filtros,
        )

    if int(resultado.get("eliminadas") or 0) == 0:
        return _redirect_cotizaciones_list(
            request,
            msg="La cotización no puede eliminarse (activada, vigente o con contabilidad).",
            sev="warning",
            **filtros,
        )
    return _redirect_cotizaciones_list(
        request,
        msg=f"Cotización #{cotizacion_id} eliminada correctamente.",
        sev="success",
        **filtros,
    )


@router.get("/nueva", response_class=HTMLResponse, name="lf_cotizacion_nueva_form")
def lf_cotizacion_nueva_form(
    request: Request,
    cliente_id: int | None = None,
    db: Session = Depends(get_db),
):
    if (redir := guard_leasing_fin_mutacion(request)) is not None:
        return redir
    clientes, _hay_mas = crud_cliente.listar_clientes(db, activos_solo=False, busqueda=None, skip=0, limit=500)
    proveedores = list(
        db.scalars(
            select(Proveedor).where(Proveedor.activo.is_(True)).order_by(Proveedor.razon_social.asc()).limit(500)
        )
    )
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
            "fecha_hoy": date.today().isoformat(),
            "proveedores": proveedores,
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
    bien_descripcion: str = Form(""),
    bien_tipo: str = Form(""),
    fecha_primera_cuota: str = Form(""),
    periodicidad: str = Form("MENSUAL"),
    comision_apertura: str = Form(""),
    comision_apertura_tipo: str = Form(""),
    financia_comision: object = Form(False),
    gastos_operacionales: str = Form(""),
    iva_aplica: object = Form(False),
    iva_tasa: str = Form(""),
    iva_recuperable: object = Form(True),
    observaciones: str = Form(""),
    proveedor_id: str = Form(""),
    tasa_fondeo: str = Form(""),
    spread_margen: str = Form(""),
    activo_marca: str = Form(""),
    activo_modelo: str = Form(""),
    activo_serie: str = Form(""),
    activo_chasis: str = Form(""),
):
    if (redir := guard_leasing_fin_mutacion(request)) is not None:
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
        monto=_parse_decimal(monto, money=True),
        moneda=moneda_norm,
        tasa=_parse_decimal(tasa),
        plazo=_parse_int(plazo),
        opcion_compra=_parse_decimal(opcion_compra, money=True),
        periodos_gracia=_parse_int(periodos_gracia) or 0,
        periodicidad=_normalizar_periodicidad(periodicidad),
        fecha_inicio=_parse_date(fecha_inicio),
        fecha_primera_cuota=_parse_date(fecha_primera_cuota),
        bien_descripcion=(bien_descripcion or None),
        bien_tipo=(bien_tipo or None),
        valor_neto=_parse_decimal(valor_neto, money=True),
        pago_inicial_tipo=(pago_inicial_tipo or None),
        pago_inicial_valor=_parse_decimal(pago_inicial_valor, money=True),
        financia_seguro=_parse_bool(financia_seguro),
        seguro_monto_uf=_parse_decimal(seguro_monto_uf, money=True),
        otros_montos_pesos=_parse_decimal(otros_montos_pesos, money=True),
        comision_apertura=_parse_decimal(comision_apertura, money=True),
        comision_apertura_tipo=(comision_apertura_tipo or None),
        financia_comision=_parse_bool(financia_comision),
        gastos_operacionales=_parse_decimal(gastos_operacionales, money=True),
        iva_aplica=_parse_bool(iva_aplica),
        iva_tasa=_parse_decimal(iva_tasa),
        iva_recuperable=_parse_bool(iva_recuperable),
        observaciones=(observaciones or None),
        concesionario=(concesionario or None),
        ejecutivo=(ejecutivo or None),
        proveedor_id=_parse_int(proveedor_id) if str(proveedor_id or "").strip() else None,
        tasa_fondeo=_parse_decimal(tasa_fondeo),
        spread_margen=_parse_decimal(spread_margen),
        activo_marca=(activo_marca or None),
        activo_modelo=(activo_modelo or None),
        activo_serie=(activo_serie or None),
        activo_chasis=(activo_chasis or None),
        fecha_cotizacion=_parse_date(fecha_cotizacion),
        uf_valor=uf_val,
        monto_financiado=_parse_decimal(monto_financiado, money=True),
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
    bien_descripcion: str = Form(""),
    bien_tipo: str = Form(""),
    fecha_primera_cuota: str = Form(""),
    periodicidad: str = Form("MENSUAL"),
    comision_apertura: str = Form(""),
    comision_apertura_tipo: str = Form(""),
    financia_comision: object = Form(False),
    gastos_operacionales: str = Form(""),
    iva_aplica: object = Form(False),
    iva_tasa: str = Form(""),
    iva_recuperable: object = Form(True),
    observaciones: str = Form(""),
    proveedor_id: str = Form(""),
    tasa_fondeo: str = Form(""),
    spread_margen: str = Form(""),
    activo_marca: str = Form(""),
    activo_modelo: str = Form(""),
    activo_serie: str = Form(""),
    activo_chasis: str = Form(""),
):
    if (redir := guard_leasing_fin_mutacion(request)) is not None:
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
        bien_descripcion=bien_descripcion,
        bien_tipo=bien_tipo,
        fecha_primera_cuota=fecha_primera_cuota,
        periodicidad=periodicidad,
        comision_apertura=comision_apertura,
        comision_apertura_tipo=comision_apertura_tipo,
        financia_comision=financia_comision,
        gastos_operacionales=gastos_operacionales,
        iva_aplica=iva_aplica,
        iva_tasa=iva_tasa,
        iva_recuperable=iva_recuperable,
        observaciones=observaciones,
        proveedor_id=proveedor_id,
        tasa_fondeo=tasa_fondeo,
        spread_margen=spread_margen,
        activo_marca=activo_marca,
        activo_modelo=activo_modelo,
        activo_serie=activo_serie,
        activo_chasis=activo_chasis,
    )


@router.post("/api/simular", response_model=LeasingSimulacionResumen, name="api_lf_cotizacion_simular")
def api_lf_cotizacion_simular(obj_in: LeasingSimulacionInput):
    moneda = _normalizar_moneda(obj_in.moneda)
    uf_val = obj_in.uf_valor
    usd_val = obj_in.dolar_valor
    try:
        _validar_fx_moneda(moneda, uf_val, usd_val)
    except ValueError as exc:
        res = leasing_financiero.simular_cotizacion(obj_in)
        res.advertencias = [str(exc), *res.advertencias]
        return res
    payload = obj_in.model_copy(update={"moneda": moneda})
    return leasing_financiero.simular_cotizacion(payload)


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


def _usuario_ui(request: Request) -> str:
    auth = getattr(request.state, "auth_user", None) or {}
    return str(auth.get("email") or auth.get("nombre") or auth.get("uid") or "ui")


def _doc_payload_from_form(**fields: str) -> dict:
    return {k: v for k, v in fields.items() if v is not None}


@router.post("/{cotizacion_id}/estado", name="lf_cotizacion_cambiar_estado")
def lf_cotizacion_cambiar_estado(
    request: Request,
    cotizacion_id: int,
    estado_nuevo: str = Form(...),
    comentario: str = Form(""),
    db: Session = Depends(get_db),
):
    if (redir := guard_leasing_fin_mutacion(request)) is not None:
        return redir
    estado_norm = _normalizar_estado(estado_nuevo)
    estados_criticos = {"APROBADA", "ACTIVADA", "ANULADA", "RECHAZADA"}
    if estado_norm in estados_criticos:
        if (redir := guard_leasing_fin_aprobar(request)) is not None:
            return redir
    cotizacion = crud_lf.get_cotizacion(db, cotizacion_id)
    if not cotizacion:
        raise HTTPException(status_code=404, detail="Cotización no encontrada")
    try:
        crud_lf.cambiar_estado_cotizacion(
            db,
            cotizacion=cotizacion,
            estado_nuevo=estado_norm,
            comentario=(comentario or "").strip() or None,
            usuario=_usuario_ui(request),
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return RedirectResponse(
        url=str(request.url_for("lf_cotizacion_detalle", cotizacion_id=cotizacion_id)),
        status_code=status.HTTP_303_SEE_OTHER,
    )


@router.get("/{cotizacion_id}/documentos/orden-compra", response_class=HTMLResponse, name="lf_doc_oc")
def lf_doc_oc(request: Request, cotizacion_id: int, db: Session = Depends(get_db)):
    if (redir := guard_leasing_fin_consulta(request)) is not None:
        return redir
    cotizacion = crud_lf.get_cotizacion(db, cotizacion_id)
    if not cotizacion:
        raise HTTPException(status_code=404, detail="Cotización no encontrada")
    doc = crud_lf.obtener_ultimo_documento_payload(db, cotizacion_id, "orden_compra")
    return templates.TemplateResponse(
        "comercial/leasing_financiero/doc_oc_builder.html",
        {"request": request, "cotizacion": cotizacion, "doc": doc, "active_menu": "leasing_financiero"},
    )


@router.post("/{cotizacion_id}/documentos/orden-compra", name="lf_doc_oc_save")
def lf_doc_oc_save(
    request: Request,
    cotizacion_id: int,
    proveedor_nombre: str = Form(""),
    numero_documento: str = Form(""),
    fecha_documento: str = Form(""),
    monto_oc: str = Form(""),
    bien_descripcion: str = Form(""),
    estado_documento: str = Form("RECIBIDO"),
    observacion: str = Form(""),
    db: Session = Depends(get_db),
):
    if (redir := guard_leasing_fin_mutacion(request)) is not None:
        return redir
    cotizacion = crud_lf.get_cotizacion(db, cotizacion_id)
    if not cotizacion:
        raise HTTPException(status_code=404, detail="Cotización no encontrada")
    payload = {
        "tipo_documento": "ORDEN_COMPRA",
        "proveedor_nombre": proveedor_nombre.strip(),
        "numero_documento": numero_documento.strip(),
        "fecha_documento": fecha_documento.strip(),
        "monto_oc": monto_oc.strip(),
        "bien_descripcion": bien_descripcion.strip(),
        "estado": estado_documento.strip().upper(),
        "observacion": observacion.strip(),
    }
    try:
        crud_lf.guardar_documento_proceso(db, cotizacion=cotizacion, modulo="orden_compra", payload=payload, usuario=_usuario_ui(request))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return RedirectResponse(url=str(request.url_for("lf_cotizacion_detalle", cotizacion_id=cotizacion_id)), status_code=303)


@router.get("/{cotizacion_id}/documentos/contrato", response_class=HTMLResponse, name="lf_doc_contrato")
def lf_doc_contrato(request: Request, cotizacion_id: int, db: Session = Depends(get_db)):
    if (redir := guard_leasing_fin_consulta(request)) is not None:
        return redir
    cotizacion = crud_lf.get_cotizacion(db, cotizacion_id)
    if not cotizacion:
        raise HTTPException(status_code=404, detail="Cotización no encontrada")
    doc = crud_lf.obtener_ultimo_documento_payload(db, cotizacion_id, "contrato")
    return templates.TemplateResponse(
        "comercial/leasing_financiero/doc_contrato_builder.html",
        {"request": request, "cotizacion": cotizacion, "doc": doc, "active_menu": "leasing_financiero"},
    )


@router.post("/{cotizacion_id}/documentos/contrato", name="lf_doc_contrato_save")
def lf_doc_contrato_save(
    request: Request,
    cotizacion_id: int,
    numero_documento: str = Form(""),
    fecha_documento: str = Form(""),
    numero_operacion: str = Form(""),
    estado_documento: str = Form("FIRMADO"),
    observacion: str = Form(""),
    db: Session = Depends(get_db),
):
    if (redir := guard_leasing_fin_mutacion(request)) is not None:
        return redir
    cotizacion = crud_lf.get_cotizacion(db, cotizacion_id)
    if not cotizacion:
        raise HTTPException(status_code=404, detail="Cotización no encontrada")
    if numero_operacion.strip():
        cotizacion.numero_operacion = numero_operacion.strip()
    if numero_documento.strip():
        cotizacion.numero_contrato = numero_documento.strip()
    payload = {
        "tipo_documento": "CONTRATO",
        "numero_documento": numero_documento.strip(),
        "fecha_documento": fecha_documento.strip(),
        "numero_operacion": numero_operacion.strip(),
        "estado": estado_documento.strip().upper(),
        "observacion": observacion.strip(),
    }
    try:
        crud_lf.guardar_documento_proceso(db, cotizacion=cotizacion, modulo="contrato", payload=payload, usuario=_usuario_ui(request))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return RedirectResponse(url=str(request.url_for("lf_cotizacion_detalle", cotizacion_id=cotizacion_id)), status_code=303)


@router.get("/{cotizacion_id}/documentos/acta", response_class=HTMLResponse, name="lf_doc_acta")
def lf_doc_acta(request: Request, cotizacion_id: int, db: Session = Depends(get_db)):
    if (redir := guard_leasing_fin_consulta(request)) is not None:
        return redir
    cotizacion = crud_lf.get_cotizacion(db, cotizacion_id)
    if not cotizacion:
        raise HTTPException(status_code=404, detail="Cotización no encontrada")
    doc = crud_lf.obtener_ultimo_documento_payload(db, cotizacion_id, "acta_recepcion")
    return templates.TemplateResponse(
        "comercial/leasing_financiero/doc_acta_builder.html",
        {"request": request, "cotizacion": cotizacion, "doc": doc, "active_menu": "leasing_financiero"},
    )


@router.post("/{cotizacion_id}/documentos/acta", name="lf_doc_acta_save")
def lf_doc_acta_save(
    request: Request,
    cotizacion_id: int,
    numero_documento: str = Form(""),
    fecha_documento: str = Form(""),
    lugar_entrega: str = Form(""),
    bien_descripcion: str = Form(""),
    identificador_bien: str = Form(""),
    observacion: str = Form(""),
    db: Session = Depends(get_db),
):
    if (redir := guard_leasing_fin_mutacion(request)) is not None:
        return redir
    cotizacion = crud_lf.get_cotizacion(db, cotizacion_id)
    if not cotizacion:
        raise HTTPException(status_code=404, detail="Cotización no encontrada")
    payload = {
        "tipo_documento": "ACTA_RECEPCION",
        "numero_documento": numero_documento.strip(),
        "fecha_documento": fecha_documento.strip(),
        "lugar_entrega": lugar_entrega.strip(),
        "bien_descripcion": bien_descripcion.strip(),
        "identificador_bien": identificador_bien.strip(),
        "observacion": observacion.strip(),
        "estado": "RECIBIDO",
    }
    try:
        crud_lf.guardar_documento_proceso(db, cotizacion=cotizacion, modulo="acta_recepcion", payload=payload, usuario=_usuario_ui(request))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return RedirectResponse(url=str(request.url_for("lf_cotizacion_detalle", cotizacion_id=cotizacion_id)), status_code=303)


@router.get("/{cotizacion_id}/documentos/factura", response_class=HTMLResponse, name="lf_doc_factura")
def lf_doc_factura(request: Request, cotizacion_id: int, db: Session = Depends(get_db)):
    if (redir := guard_leasing_fin_consulta(request)) is not None:
        return redir
    cotizacion = crud_lf.get_cotizacion(db, cotizacion_id)
    if not cotizacion:
        raise HTTPException(status_code=404, detail="Cotización no encontrada")
    doc = crud_lf.obtener_ultimo_documento_payload(db, cotizacion_id, "factura_proveedor")
    if cotizacion.facturas_compra:
        f = cotizacion.facturas_compra[-1]
        doc = {
            "proveedor_id": f.proveedor_id,
            "nro_factura": f.folio,
            "fecha_factura": str(f.fecha_factura),
            "neto": f.neto,
            "iva": f.iva,
            "total": f.total,
            "ap_documento_id": f.ap_documento_id,
        }
    return templates.TemplateResponse(
        "comercial/leasing_financiero/doc_factura_builder.html",
        {"request": request, "cotizacion": cotizacion, "doc": doc, "active_menu": "leasing_financiero"},
    )


@router.post("/{cotizacion_id}/documentos/factura", name="lf_doc_factura_save")
def lf_doc_factura_save(
    request: Request,
    cotizacion_id: int,
    proveedor_id: str = Form(""),
    proveedor_nombre: str = Form(""),
    nro_factura: str = Form(...),
    fecha_factura: str = Form(...),
    neto: str = Form(...),
    iva: str = Form("0"),
    total: str = Form(...),
    db: Session = Depends(get_db),
):
    if (redir := guard_leasing_fin_mutacion(request)) is not None:
        return redir
    cotizacion = crud_lf.get_cotizacion(db, cotizacion_id)
    if not cotizacion:
        raise HTTPException(status_code=404, detail="Cotización no encontrada")
    payload = {
        "proveedor_id": proveedor_id,
        "proveedor_nombre": proveedor_nombre,
        "folio": nro_factura,
        "nro_factura": nro_factura,
        "fecha_factura": fecha_factura,
        "neto": neto,
        "iva": iva,
        "total": total,
        "estado": "REGISTRADA",
    }
    try:
        crud_lf.guardar_documento_proceso(
            db,
            cotizacion=cotizacion,
            modulo="factura_proveedor",
            payload=payload,
            usuario=_usuario_ui(request),
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return RedirectResponse(url=str(request.url_for("lf_cotizacion_detalle", cotizacion_id=cotizacion_id)), status_code=303)


@router.post("/{cotizacion_id}/workflow/solicitar-pago", name="lf_cotizacion_solicitar_pago")
def lf_cotizacion_solicitar_pago(
    request: Request,
    cotizacion_id: int,
    factura_id: str = Form(""),
    db: Session = Depends(get_db),
):
    if (redir := guard_leasing_fin_aprobar(request)) is not None:
        return redir
    cotizacion = crud_lf.get_cotizacion(db, cotizacion_id)
    if not cotizacion:
        raise HTTPException(status_code=404, detail="Cotización no encontrada")
    try:
        crud_lf.solicitar_pago(
            db,
            cotizacion=cotizacion,
            factura_id=_parse_int(factura_id) if str(factura_id or "").strip() else None,
            usuario=_usuario_ui(request),
            aprobado_por=_usuario_ui(request),
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return RedirectResponse(
        url=str(request.url_for("lf_cotizacion_detalle", cotizacion_id=cotizacion_id)),
        status_code=status.HTTP_303_SEE_OTHER,
    )


@router.get("/{cotizacion_id}", response_class=HTMLResponse, name="lf_cotizacion_detalle")
def lf_cotizacion_detalle(
    request: Request,
    cotizacion_id: int,
    db: Session = Depends(get_db),
):
    if (redir := guard_leasing_fin_consulta(request)) is not None:
        return redir
    cotizacion = crud_lf.get_cotizacion(db, cotizacion_id)
    if not cotizacion:
        raise HTTPException(status_code=404, detail="Cotización no encontrada")

    cotizaciones_cliente = crud_lf.listar_cotizaciones_por_cliente(db, cotizacion.cliente_id)
    workflow = crud_lf.obtener_workflow(cotizacion)
    documentos = crud_lf.listar_documentos_proceso(db, int(cotizacion.id))
    historial = crud_lf.listar_historial(db, int(cotizacion.id))
    resumen = None
    try:
        resumen = leasing_financiero.simular_cotizacion(_cotizacion_a_simulacion(cotizacion))
    except Exception:
        resumen = None

    return templates.TemplateResponse(
        "comercial/leasing_financiero/cotizacion_detalle.html",
        {
            "request": request,
            "cotizacion": cotizacion,
            "resumen": resumen,
            "cotizaciones_cliente": cotizaciones_cliente,
            "workflow": workflow,
            "documentos_proceso": documentos,
            "historial": historial,
            "checklist": cotizacion.checklist_items or [],
            "activo": cotizacion.activo,
            "facturas_compra": cotizacion.facturas_compra or [],
            "solicitudes_pago": cotizacion.solicitudes_pago or [],
            "ordenes_compra": cotizacion.ordenes_compra or [],
            "estados_lf": sorted(ESTADOS_LF),
            "active_menu": "leasing_financiero",
        },
    )


@router.post("/{cotizacion_id}/workflow/sync-credito", name="lf_cotizacion_workflow_sync_credito")
def lf_cotizacion_workflow_sync_credito(
    request: Request,
    cotizacion_id: int,
    db: Session = Depends(get_db),
):
    if (redir := guard_leasing_fin_mutacion(request)) is not None:
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
    if (redir := guard_leasing_fin_mutacion(request)) is not None:
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
    if (redir := guard_leasing_fin_aprobar(request)) is not None:
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
    if (redir := guard_leasing_fin_consulta(request)) is not None:
        return redir
    cotizacion = crud_lf.get_cotizacion(db, cotizacion_id)
    if not cotizacion:
        raise HTTPException(status_code=404, detail="Cotización no encontrada")

    try:
        tabla = leasing_financiero.calcular_tabla_amortizacion(cotizacion)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    total_interes = sum((c.interes for c in tabla), Decimal("0.00"))
    total_rentas = sum((c.cuota for c in tabla if not c.es_opcion_compra), Decimal("0.00"))
    total_opcion = sum((c.cuota for c in tabla if c.es_opcion_compra), Decimal("0.00"))
    total_pagado = total_rentas + total_opcion

    return templates.TemplateResponse(
        "comercial/leasing_financiero/cotizacion_amortizacion.html",
        {
            "request": request,
            "cotizacion": cotizacion,
            "tabla": tabla,
            "total_interes": total_interes,
            "total_rentas": total_rentas,
            "total_opcion": total_opcion,
            "total_pagado": total_pagado,
            "active_menu": "leasing_financiero",
        },
    )


@router.get("/{cotizacion_id}/editar", response_class=HTMLResponse, name="lf_cotizacion_editar_form")
def lf_cotizacion_editar_form(
    request: Request,
    cotizacion_id: int,
    db: Session = Depends(get_db),
):
    if (redir := guard_leasing_fin_mutacion(request)) is not None:
        return redir
    cotizacion = crud_lf.get_cotizacion(db, cotizacion_id)
    if not cotizacion:
        raise HTTPException(status_code=404, detail="Cotización no encontrada")
    clientes, _hay_mas = crud_cliente.listar_clientes(db, activos_solo=False, busqueda=None, skip=0, limit=500)
    proveedores = list(
        db.scalars(
            select(Proveedor).where(Proveedor.activo.is_(True)).order_by(Proveedor.razon_social.asc()).limit(500)
        )
    )
    cliente = cotizacion.cliente
    return templates.TemplateResponse(
        "comercial/leasing_financiero/form_cotizacion.html",
        {
            "request": request,
            "modo": "editar",
            "cotizacion": cotizacion,
            "cliente": cliente,
            "clientes": clientes,
            "has_clientes": bool(clientes),
            "moneda_default": cotizacion.moneda or "CLP",
            "fecha_hoy": date.today().isoformat(),
            "proveedores": proveedores,
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
    bien_descripcion: str = Form(""),
    bien_tipo: str = Form(""),
    fecha_primera_cuota: str = Form(""),
    periodicidad: str = Form("MENSUAL"),
    comision_apertura: str = Form(""),
    comision_apertura_tipo: str = Form(""),
    financia_comision: object = Form(False),
    gastos_operacionales: str = Form(""),
    iva_aplica: object = Form(False),
    iva_tasa: str = Form(""),
    iva_recuperable: object = Form(True),
    observaciones: str = Form(""),
    estado: str = Form("BORRADOR"),
    proveedor_id: str = Form(""),
    tasa_fondeo: str = Form(""),
    spread_margen: str = Form(""),
    activo_marca: str = Form(""),
    activo_modelo: str = Form(""),
    activo_serie: str = Form(""),
    activo_chasis: str = Form(""),
    db: Session = Depends(get_db),
):
    if (redir := guard_leasing_fin_mutacion(request)) is not None:
        return redir
    cotizacion = crud_lf.get_cotizacion(db, cotizacion_id)
    if not cotizacion:
        raise HTTPException(status_code=404, detail="Cotización no encontrada")

    moneda_norm = _normalizar_moneda(moneda)
    uf_val = _parse_decimal(uf_valor)
    usd_val = _parse_decimal(dolar_valor)
    _validar_fx_moneda(moneda_norm, uf_val, usd_val)

    obj = LeasingCotizacionUpdate(
        monto=_parse_decimal(monto, money=True),
        moneda=moneda_norm,
        tasa=_parse_decimal(tasa),
        plazo=_parse_int(plazo),
        opcion_compra=_parse_decimal(opcion_compra, money=True),
        periodos_gracia=_parse_int(periodos_gracia),
        periodicidad=_normalizar_periodicidad(periodicidad),
        fecha_inicio=_parse_date(fecha_inicio),
        fecha_primera_cuota=_parse_date(fecha_primera_cuota),
        bien_descripcion=(bien_descripcion or None),
        bien_tipo=(bien_tipo or None),
        valor_neto=_parse_decimal(valor_neto, money=True),
        pago_inicial_tipo=(pago_inicial_tipo or None),
        pago_inicial_valor=_parse_decimal(pago_inicial_valor, money=True),
        financia_seguro=_parse_bool(financia_seguro),
        seguro_monto_uf=_parse_decimal(seguro_monto_uf, money=True),
        otros_montos_pesos=_parse_decimal(otros_montos_pesos, money=True),
        comision_apertura=_parse_decimal(comision_apertura, money=True),
        comision_apertura_tipo=(comision_apertura_tipo or None),
        financia_comision=_parse_bool(financia_comision),
        gastos_operacionales=_parse_decimal(gastos_operacionales, money=True),
        iva_aplica=_parse_bool(iva_aplica),
        iva_tasa=_parse_decimal(iva_tasa),
        iva_recuperable=_parse_bool(iva_recuperable),
        observaciones=(observaciones or None),
        concesionario=(concesionario or None),
        ejecutivo=(ejecutivo or None),
        proveedor_id=_parse_int(proveedor_id) if str(proveedor_id or "").strip() else None,
        tasa_fondeo=_parse_decimal(tasa_fondeo),
        spread_margen=_parse_decimal(spread_margen),
        activo_marca=(activo_marca or None),
        activo_modelo=(activo_modelo or None),
        activo_serie=(activo_serie or None),
        activo_chasis=(activo_chasis or None),
        fecha_cotizacion=_parse_date(fecha_cotizacion),
        uf_valor=uf_val,
        monto_financiado=_parse_decimal(monto_financiado, money=True),
        dolar_valor=usd_val,
        estado=_normalizar_estado(estado),
    )
    try:
        cotizacion = crud_lf.actualizar_cotizacion(db, cotizacion=cotizacion, obj_in=obj)
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
