# routes/ui/cuentas_por_pagar.py
# -*- coding: utf-8 -*-
from __future__ import annotations

import json
import logging
from datetime import date
from typing import Any, Optional
from urllib.parse import urlencode

from fastapi import APIRouter, Depends, Form, Query, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from pydantic import ValidationError
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session

from core.config import settings
from core.paths import TEMPLATES_DIR
from core.public_errors import public_error_message
from core.rbac import guard_finanzas_consulta, guard_finanzas_mutacion
from crud.finanzas.cuentas_por_pagar import cuentas_por_pagar as crud_cxp
from db.session import get_db
from schemas.finanzas.cuentas_por_pagar import DocumentoCreate, DocumentoUpdate, PagoCreate

router = APIRouter(prefix="/finanzas/cxp", tags=["Finanzas - Cuentas por Pagar"])
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))
logger = logging.getLogger(__name__)


def _cxp_user_message(exc: BaseException) -> str:
    """Mensaje seguro para el usuario (sin trazas SQL ni detalles internos)."""
    if isinstance(exc, ValidationError):
        parts: list[str] = []
        for err in exc.errors()[:8]:
            loc = " → ".join(str(x) for x in err.get("loc", ()) if x != "body")
            msg = str(err.get("msg", ""))
            if loc:
                parts.append(f"{loc}: {msg}")
            else:
                parts.append(msg)
        return "Revise el formulario: " + "; ".join(parts) if parts else "Datos del formulario no válidos."
    if isinstance(exc, ValueError):
        return public_error_message(exc)
    if isinstance(exc, SQLAlchemyError):
        logger.exception("CxP: error de base de datos")
        orig = getattr(exc, "orig", None)
        raw = str(orig or exc).strip()
        low = raw.lower()
        if (
            "invalid input value for enum" in low
            or "invalidtextrepresentation" in low.replace(" ", "")
            or "no es válida para el enum" in low
            or "no es valida para el enum" in low
        ):
            base = (
                "Un valor no coincide con las opciones permitidas en base de datos "
                "(estado, tipo de documento u otro campo enumerado). "
            )
            if settings.app_debug:
                return base + raw[:500]
            return base + "Si acaba de actualizar el código, reinicie el servidor y vuelva a intentar."
        if isinstance(exc, IntegrityError):
            if "unique" in low or "duplicate key" in low:
                return (
                    "Ya existe un registro con la misma clave (por ejemplo mismo proveedor, tipo y folio)."
                )
            if "foreign key" in low or "violates foreign key" in low:
                return "Hay una referencia inválida (proveedor, cuentas o categorías). Verifique los datos."
            if raw and settings.app_debug:
                return f"Restricción en base de datos: {raw[:400]}"
        if settings.app_debug and raw:
            return raw[:600]
        return "No se pudo completar la operación en base de datos. Verifique datos, período contable y permisos."
    logger.exception("CxP: error no controlado")
    return "Ocurrió un error inesperado. Si persiste, contacte al administrador."


def _redirect(
    request: Request,
    route_name: str,
    *,
    msg: str | None = None,
    sev: str = "info",
    **params: Any,
) -> RedirectResponse:
    url = request.url_for(route_name, **{k: v for k, v in params.items() if v is not None})
    query: dict[str, Any] = {}
    if msg:
        query["msg"] = msg
        query["sev"] = sev
    if query:
        url = f"{url}?{urlencode(query)}"
    return RedirectResponse(url=url, status_code=303)


def _safe_loads(raw: str | None) -> list[dict[str, Any]]:
    if not raw:
        return []
    try:
        data = json.loads(raw)
        return data if isinstance(data, list) else []
    except Exception:
        return []


def _bool_desde_form(val: Optional[str], *, default: bool = True) -> bool:
    if val is None:
        return default
    s = str(val).strip().lower()
    if s in ("0", "false", "off", "no"):
        return False
    return s in ("1", "true", "on", "yes", "si", "sí")


def _payload_documento_desde_form(
    *,
    proveedor_id: int,
    tipo: str,
    folio: str,
    fecha_emision: str,
    fecha_recepcion: Optional[str],
    fecha_vencimiento: str,
    moneda: str,
    tipo_cambio: str,
    es_exento: str,
    referencia: Optional[str],
    observaciones: Optional[str],
    detalles_json: str,
    impuestos_json: Optional[str],
    tipo_compra_contable: str = "GASTO",
    cuenta_gasto_codigo: Optional[str] = None,
    cuenta_proveedores_codigo: Optional[str] = None,
    generar_asiento_contable: Optional[str] = None,
    generar_default: bool = True,
) -> dict[str, Any]:
    return {
        "proveedor_id": proveedor_id,
        "tipo": tipo,
        "folio": folio,
        "fecha_emision": fecha_emision,
        "fecha_recepcion": fecha_recepcion or None,
        "fecha_vencimiento": fecha_vencimiento,
        "moneda": moneda,
        "tipo_cambio": tipo_cambio,
        "es_exento": es_exento,
        "referencia": referencia,
        "observaciones": observaciones,
        "detalles": _safe_loads(detalles_json),
        "impuestos": _safe_loads(impuestos_json),
        "tipo_compra_contable": (tipo_compra_contable or "GASTO").strip().upper(),
        "cuenta_gasto_codigo": cuenta_gasto_codigo,
        "cuenta_proveedores_codigo": cuenta_proveedores_codigo,
        "generar_asiento_contable": _bool_desde_form(
            generar_asiento_contable, default=generar_default
        ),
    }


@router.get("", response_class=HTMLResponse, name="cxp_lista")
def cxp_lista(
    request: Request,
    q: Optional[str] = Query(None),
    proveedor_id: Optional[int] = Query(None),
    estado: Optional[str] = Query(None),
    solo_abiertos: bool = Query(False),
    msg: Optional[str] = Query(None),
    sev: str = Query("info"),
    db: Session = Depends(get_db),
):
    if (redir := guard_finanzas_consulta(request)) is not None:
        return redir
    resumen = crud_cxp.get_resumen(db)
    documentos = crud_cxp.list_documentos(
        db,
        q=q,
        proveedor_id=proveedor_id,
        estado=estado,
        solo_abiertos=solo_abiertos,
    )
    catalogos = crud_cxp.get_catalogos(db)

    return templates.TemplateResponse(
        "finanzas/cxp_lista.html",
        {
            "request": request,
            "active_menu": "cxp",
            "cxp_schema_ok": crud_cxp.ap_tablas_operativas(db),
            "resumen": resumen,
            "documentos": documentos,
            "proveedores": catalogos["proveedores"],
            "filtros": {
                "q": q or "",
                "proveedor_id": proveedor_id,
                "estado": estado or "",
                "solo_abiertos": solo_abiertos,
            },
            "msg": msg,
            "sev": sev,
        },
    )


@router.get("/nuevo", response_class=HTMLResponse, name="cxp_nuevo")
def cxp_nuevo(
    request: Request,
    msg: Optional[str] = Query(None),
    sev: str = Query("info"),
    db: Session = Depends(get_db),
):
    if (redir := guard_finanzas_mutacion(request)) is not None:
        return redir
    catalogos = crud_cxp.get_catalogos(db)

    return templates.TemplateResponse(
        "finanzas/cxp_form.html",
        {
            "request": request,
            "active_menu": "cxp",
            "cxp_schema_ok": crud_cxp.ap_tablas_operativas(db),
            "modo": "nuevo",
            "documento": None,
            "proveedor_public_id": None,
            "detalles_iniciales": [],
            "impuestos_iniciales": [],
            "proveedores": catalogos["proveedores"],
            "categorias": catalogos["categorias"],
            "centros": catalogos["centros"],
            "cuentas_movimiento": catalogos.get("cuentas_movimiento") or [],
            "fecha_hoy": date.today().isoformat(),
            "msg": msg,
            "sev": sev,
        },
    )


@router.post("/nuevo", name="cxp_crear")
def cxp_crear(
    request: Request,
    proveedor_id: int = Form(...),
    tipo: str = Form(...),
    folio: str = Form(...),
    fecha_emision: str = Form(...),
    fecha_recepcion: Optional[str] = Form(None),
    fecha_vencimiento: str = Form(...),
    moneda: str = Form("CLP"),
    tipo_cambio: str = Form("1"),
    es_exento: str = Form("NO"),
    referencia: Optional[str] = Form(None),
    observaciones: Optional[str] = Form(None),
    tipo_compra_contable: str = Form("GASTO"),
    cuenta_gasto_codigo: Optional[str] = Form(None),
    cuenta_proveedores_codigo: Optional[str] = Form(None),
    generar_asiento_contable: Optional[str] = Form(None),
    detalles_json: str = Form(...),
    impuestos_json: Optional[str] = Form("[]"),
    db: Session = Depends(get_db),
):
    if (redir := guard_finanzas_mutacion(request)) is not None:
        return redir
    try:
        payload = DocumentoCreate(
            **_payload_documento_desde_form(
                proveedor_id=proveedor_id,
                tipo=tipo,
                folio=folio,
                fecha_emision=fecha_emision,
                fecha_recepcion=fecha_recepcion,
                fecha_vencimiento=fecha_vencimiento,
                moneda=moneda,
                tipo_cambio=tipo_cambio,
                es_exento=es_exento,
                referencia=referencia,
                observaciones=observaciones,
                detalles_json=detalles_json,
                impuestos_json=impuestos_json,
                tipo_compra_contable=tipo_compra_contable,
                cuenta_gasto_codigo=cuenta_gasto_codigo,
                cuenta_proveedores_codigo=cuenta_proveedores_codigo,
                generar_asiento_contable=generar_asiento_contable,
                generar_default=True,
            )
        )
        doc = crud_cxp.create_documento(db, payload)
        return _redirect(
            request,
            "cxp_detalle",
            documento_id=doc.id,
            msg="Documento creado correctamente.",
            sev="success",
        )
    except (ValidationError, ValueError, SQLAlchemyError) as e:
        return _redirect(
            request,
            "cxp_nuevo",
            msg=f"No se pudo crear el documento. {_cxp_user_message(e)}",
            sev="danger",
        )


@router.get("/{documento_id}", response_class=HTMLResponse, name="cxp_detalle")
def cxp_detalle(
    request: Request,
    documento_id: int,
    msg: Optional[str] = Query(None),
    sev: str = Query("info"),
    db: Session = Depends(get_db),
):
    if (redir := guard_finanzas_consulta(request)) is not None:
        return redir
    data = crud_cxp.get_documento_view(db, documento_id)
    if not data:
        return _redirect(request, "cxp_lista", msg="Documento no encontrado.", sev="warning")

    return templates.TemplateResponse(
        "finanzas/cxp_detalle.html",
        {
            "request": request,
            "active_menu": "cxp",
            "cxp_schema_ok": crud_cxp.ap_tablas_operativas(db),
            "data": data,
            "msg": msg,
            "sev": sev,
        },
    )


@router.get("/{documento_id}/editar", response_class=HTMLResponse, name="cxp_editar")
def cxp_editar(
    request: Request,
    documento_id: int,
    msg: Optional[str] = Query(None),
    sev: str = Query("info"),
    db: Session = Depends(get_db),
):
    if (redir := guard_finanzas_mutacion(request)) is not None:
        return redir
    documento = crud_cxp.get_documento(db, documento_id)
    if not documento:
        return _redirect(request, "cxp_lista", msg="Documento no encontrado.", sev="warning")

    if getattr(documento, "asiento_id", None):
        return _redirect(
            request,
            "cxp_detalle",
            documento_id=documento_id,
            msg="Este documento ya está contabilizado y no admite edición desde el formulario.",
            sev="warning",
        )

    catalogos = crud_cxp.get_catalogos(db)

    return templates.TemplateResponse(
        "finanzas/cxp_form.html",
        {
            "request": request,
            "active_menu": "cxp",
            "cxp_schema_ok": crud_cxp.ap_tablas_operativas(db),
            "modo": "editar",
            "documento": documento,
            "proveedor_public_id": crud_cxp.proveedor_publico_id_de_documento(documento),
            "detalles_iniciales": crud_cxp.serialize_detalles(documento),
            "impuestos_iniciales": crud_cxp.serialize_impuestos(documento),
            "proveedores": catalogos["proveedores"],
            "categorias": catalogos["categorias"],
            "centros": catalogos["centros"],
            "cuentas_movimiento": catalogos.get("cuentas_movimiento") or [],
            "fecha_hoy": date.today().isoformat(),
            "msg": msg,
            "sev": sev,
        },
    )


@router.post("/{documento_id}/editar", name="cxp_actualizar")
def cxp_actualizar(
    request: Request,
    documento_id: int,
    proveedor_id: int = Form(...),
    tipo: str = Form(...),
    folio: str = Form(...),
    fecha_emision: str = Form(...),
    fecha_recepcion: Optional[str] = Form(None),
    fecha_vencimiento: str = Form(...),
    moneda: str = Form("CLP"),
    tipo_cambio: str = Form("1"),
    es_exento: str = Form("NO"),
    referencia: Optional[str] = Form(None),
    observaciones: Optional[str] = Form(None),
    tipo_compra_contable: str = Form("GASTO"),
    cuenta_gasto_codigo: Optional[str] = Form(None),
    cuenta_proveedores_codigo: Optional[str] = Form(None),
    generar_asiento_contable: Optional[str] = Form(None),
    detalles_json: str = Form(...),
    impuestos_json: Optional[str] = Form("[]"),
    db: Session = Depends(get_db),
):
    if (redir := guard_finanzas_mutacion(request)) is not None:
        return redir
    try:
        payload = DocumentoUpdate(
            **_payload_documento_desde_form(
                proveedor_id=proveedor_id,
                tipo=tipo,
                folio=folio,
                fecha_emision=fecha_emision,
                fecha_recepcion=fecha_recepcion,
                fecha_vencimiento=fecha_vencimiento,
                moneda=moneda,
                tipo_cambio=tipo_cambio,
                es_exento=es_exento,
                referencia=referencia,
                observaciones=observaciones,
                detalles_json=detalles_json,
                impuestos_json=impuestos_json,
                tipo_compra_contable=tipo_compra_contable,
                cuenta_gasto_codigo=cuenta_gasto_codigo,
                cuenta_proveedores_codigo=cuenta_proveedores_codigo,
                generar_asiento_contable=generar_asiento_contable,
                generar_default=False,
            )
        )
        crud_cxp.update_documento(db, documento_id, payload)
        return _redirect(
            request,
            "cxp_detalle",
            documento_id=documento_id,
            msg="Documento actualizado correctamente.",
            sev="success",
        )
    except (ValidationError, ValueError, SQLAlchemyError) as e:
        return _redirect(
            request,
            "cxp_editar",
            documento_id=documento_id,
            msg=f"No se pudo actualizar el documento. {_cxp_user_message(e)}",
            sev="danger",
        )


@router.get("/{documento_id}/pagar", response_class=HTMLResponse, name="cxp_pagar_form")
def cxp_pagar_form(
    request: Request,
    documento_id: int,
    msg: Optional[str] = Query(None),
    sev: str = Query("info"),
    db: Session = Depends(get_db),
):
    if (redir := guard_finanzas_mutacion(request)) is not None:
        return redir
    data = crud_cxp.get_documento_view(db, documento_id)
    if not data:
        return _redirect(request, "cxp_lista", msg="Documento no encontrado.", sev="warning")

    doc = data["documento"]
    documentos_abiertos = crud_cxp.documentos_abiertos_proveedor(db, doc.proveedor_id)
    bancos = crud_cxp.get_bancos_proveedor(db, doc.proveedor_id)

    return templates.TemplateResponse(
        "finanzas/cxp_pago_form.html",
        {
            "request": request,
            "active_menu": "cxp",
            "cxp_schema_ok": crud_cxp.ap_tablas_operativas(db),
            "data": data,
            "proveedor_public_id": doc.proveedor_id,
            "documentos_abiertos": documentos_abiertos,
            "bancos": bancos,
            "fecha_hoy": date.today().isoformat(),
            "msg": msg,
            "sev": sev,
        },
    )


@router.post("/{documento_id}/pagar", name="cxp_pagar")
def cxp_pagar(
    request: Request,
    documento_id: int,
    proveedor_id: int = Form(...),
    fecha_pago: str = Form(...),
    medio_pago: str = Form(...),
    referencia: Optional[str] = Form(None),
    banco_proveedor_id: Optional[str] = Form(None),
    moneda: str = Form("CLP"),
    tipo_cambio: str = Form("1"),
    observaciones: Optional[str] = Form(None),
    aplicaciones_json: str = Form(...),
    db: Session = Depends(get_db),
):
    if (redir := guard_finanzas_mutacion(request)) is not None:
        return redir
    try:
        payload = PagoCreate(
            proveedor_id=proveedor_id,
            fecha_pago=fecha_pago,
            medio_pago=medio_pago,
            referencia=referencia,
            banco_proveedor_id=(
                int(str(banco_proveedor_id).strip())
                if banco_proveedor_id is not None and str(banco_proveedor_id).strip() != ""
                else None
            ),
            moneda=moneda,
            tipo_cambio=tipo_cambio,
            observaciones=observaciones,
            aplicaciones=_safe_loads(aplicaciones_json),
        )

        crud_cxp.registrar_pago(db, payload)

        return _redirect(
            request,
            "cxp_detalle",
            documento_id=documento_id,
            msg="Pago registrado correctamente.",
            sev="success",
        )
    except (ValidationError, ValueError, SQLAlchemyError) as e:
        return _redirect(
            request,
            "cxp_pagar_form",
            documento_id=documento_id,
            msg=f"No se pudo registrar el pago. {_cxp_user_message(e)}",
            sev="danger",
        )


@router.post("/{documento_id}/eliminar", name="cxp_eliminar")
def cxp_eliminar(
    request: Request,
    documento_id: int,
    db: Session = Depends(get_db),
):
    if (redir := guard_finanzas_mutacion(request)) is not None:
        return redir
    try:
        crud_cxp.eliminar_documento(db, documento_id)
        return _redirect(
            request,
            "cxp_lista",
            msg="Documento eliminado correctamente.",
            sev="success",
        )
    except (ValidationError, ValueError, SQLAlchemyError) as e:
        return _redirect(
            request,
            "cxp_detalle",
            documento_id=documento_id,
            msg=f"No se pudo eliminar el documento. {_cxp_user_message(e)}",
            sev="danger",
        )