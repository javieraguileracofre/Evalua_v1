# routes/ui/proveedor.py
# -*- coding: utf-8 -*-
from __future__ import annotations

import json
import logging
from typing import Any, Optional
from urllib.parse import urlencode

from fastapi import APIRouter, Depends, Form, Query, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from core.paths import TEMPLATES_DIR
from core.public_errors import public_error_message
from crud.finanzas.proveedor_fin import proveedor_fin as crud_proveedor_fin
from crud.maestros.proveedor import proveedor as crud_proveedor
from db.session import get_db
from schemas.finanzas.proveedor_fin import ProveedorFinUpdate
from schemas.maestros.proveedor import ProveedorCreate, ProveedorUpdate

router = APIRouter(prefix="/proveedores", tags=["Maestros - Proveedores"])
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))
logger = logging.getLogger("evalua.proveedor.ui")


def _build_url_with_params(base_url: str, **params: Any) -> str:
    clean_params = {k: v for k, v in params.items() if v is not None}
    if not clean_params:
        return base_url
    return f"{base_url}?{urlencode(clean_params, doseq=True)}"


def _redirect(
    request: Request,
    route_name: str,
    msg: str,
    sev: str = "info",
    **path_params: Any,
) -> RedirectResponse:
    url = str(request.url_for(route_name, **path_params))
    final_url = _build_url_with_params(url, msg=msg, sev=sev)
    return RedirectResponse(final_url, status_code=303)


def _clean_optional_str(value: Optional[str]) -> Optional[str]:
    if value is None:
        return None
    value = value.strip()
    return value or None


def _parse_json_list(raw_value: str, field_name: str) -> list[dict[str, Any]]:
    raw_value = (raw_value or "[]").strip()

    try:
        data = json.loads(raw_value)
    except json.JSONDecodeError as e:
        raise ValueError(f"El bloque {field_name} contiene JSON inválido.") from e

    if data is None:
        return []

    if not isinstance(data, list):
        raise ValueError(f"El bloque {field_name} debe ser una lista.")

    normalized: list[dict[str, Any]] = []
    for idx, item in enumerate(data, start=1):
        if not isinstance(item, dict):
            raise ValueError(f"El elemento {idx} de {field_name} no es un objeto válido.")
        normalized.append(item)

    return normalized


def _payload_desde_form(
    *,
    rut: str,
    razon_social: str,
    nombre_fantasia: Optional[str],
    giro: Optional[str],
    email: Optional[str],
    telefono: Optional[str],
    sitio_web: Optional[str],
    condicion_pago_dias: int,
    limite_credito: str,
    activo: Optional[str],
    notas: Optional[str],
    bancos_json: str,
    contactos_json: str,
    direcciones_json: str,
) -> dict[str, Any]:
    return {
        "rut": rut.strip(),
        "razon_social": razon_social.strip(),
        "nombre_fantasia": _clean_optional_str(nombre_fantasia),
        "giro": _clean_optional_str(giro),
        "email": _clean_optional_str(email),
        "telefono": _clean_optional_str(telefono),
        "sitio_web": _clean_optional_str(sitio_web),
        "condicion_pago_dias": condicion_pago_dias,
        "limite_credito": (limite_credito or "0").strip(),
        "activo": activo == "on",
        "notas": _clean_optional_str(notas),
        "bancos": _parse_json_list(bancos_json, "bancos"),
        "contactos": _parse_json_list(contactos_json, "contactos"),
        "direcciones": _parse_json_list(direcciones_json, "direcciones"),
    }


def _payload_fin_desde_form(
    *,
    fin_condicion_pago_dias: int,
    fin_limite_credito: str,
    fin_estado: str,
    fin_notas: Optional[str],
) -> ProveedorFinUpdate:
    return ProveedorFinUpdate(
        condicion_pago_dias=fin_condicion_pago_dias,
        limite_credito=(fin_limite_credito or "0").strip(),
        estado=(fin_estado or "ACTIVO").strip().upper(),
        notas=_clean_optional_str(fin_notas),
    )


@router.get("", response_class=HTMLResponse, name="proveedor_lista")
def proveedor_lista(
    request: Request,
    q: Optional[str] = Query(None),
    solo_activos: bool = Query(False),
    msg: Optional[str] = Query(None),
    sev: str = Query("info"),
    db: Session = Depends(get_db),
):
    proveedores = crud_proveedor.list_proveedores(
        db,
        q=_clean_optional_str(q),
        solo_activos=solo_activos,
    )
    resumen = crud_proveedor.get_resumen(db)

    return templates.TemplateResponse(
        "proveedores/proveedores.html",
        {
            "request": request,
            "active_menu": "proveedores",
            "proveedores": proveedores,
            "resumen": resumen,
            "filtros": {
                "q": q or "",
                "solo_activos": solo_activos,
            },
            "msg": msg,
            "sev": sev,
        },
    )


@router.get("/nuevo", response_class=HTMLResponse, name="proveedor_nuevo")
def proveedor_nuevo(
    request: Request,
    msg: Optional[str] = Query(None),
    sev: str = Query("info"),
):
    return templates.TemplateResponse(
        "proveedores/form_proveedor.html",
        {
            "request": request,
            "active_menu": "proveedores",
            "modo": "nuevo",
            "proveedor": None,
            "proveedor_fin": None,
            "resumen_financiero": None,
            "bancos_iniciales": [],
            "contactos_iniciales": [],
            "direcciones_iniciales": [],
            "msg": msg,
            "sev": sev,
        },
    )


@router.post("/nuevo", name="proveedor_crear")
def proveedor_crear(
    request: Request,
    rut: str = Form(...),
    razon_social: str = Form(...),
    nombre_fantasia: Optional[str] = Form(None),
    giro: Optional[str] = Form(None),
    email: Optional[str] = Form(None),
    telefono: Optional[str] = Form(None),
    sitio_web: Optional[str] = Form(None),
    condicion_pago_dias: int = Form(30),
    limite_credito: str = Form("0"),
    activo: Optional[str] = Form(None),
    notas: Optional[str] = Form(None),
    bancos_json: str = Form("[]"),
    contactos_json: str = Form("[]"),
    direcciones_json: str = Form("[]"),
    fin_condicion_pago_dias: int = Form(30),
    fin_limite_credito: str = Form("0"),
    fin_estado: str = Form("ACTIVO"),
    fin_notas: Optional[str] = Form(None),
    db: Session = Depends(get_db),
):
    try:
        payload = ProveedorCreate(
            **_payload_desde_form(
                rut=rut,
                razon_social=razon_social,
                nombre_fantasia=nombre_fantasia,
                giro=giro,
                email=email,
                telefono=telefono,
                sitio_web=sitio_web,
                condicion_pago_dias=condicion_pago_dias,
                limite_credito=limite_credito,
                activo=activo,
                notas=notas,
                bancos_json=bancos_json,
                contactos_json=contactos_json,
                direcciones_json=direcciones_json,
            )
        )

        prov = crud_proveedor.create_proveedor(db, payload)

        payload_fin = _payload_fin_desde_form(
            fin_condicion_pago_dias=fin_condicion_pago_dias,
            fin_limite_credito=fin_limite_credito,
            fin_estado=fin_estado,
            fin_notas=fin_notas,
        )
        crud_proveedor_fin.upsert(db, payload_fin, prov.id)

        return _redirect(
            request,
            "proveedor_editar",
            "Proveedor creado correctamente.",
            "success",
            proveedor_id=prov.id,
        )

    except Exception as e:
        logger.exception("Crear proveedor")
        return _redirect(
            request,
            "proveedor_nuevo",
            public_error_message(e, default="No se pudo crear el proveedor."),
            "danger",
        )


@router.get("/{proveedor_id}/editar", response_class=HTMLResponse, name="proveedor_editar")
def proveedor_editar(
    request: Request,
    proveedor_id: int,
    msg: Optional[str] = Query(None),
    sev: str = Query("info"),
    db: Session = Depends(get_db),
):
    prov = crud_proveedor.get_proveedor(db, proveedor_id)
    if not prov:
        return _redirect(
            request,
            "proveedor_lista",
            "Proveedor no encontrado.",
            "warning",
        )

    prov_fin = crud_proveedor_fin.get_by_proveedor_id(db, proveedor_id)
    resumen_financiero = crud_proveedor_fin.get_resumen_financiero(db, proveedor_id)

    bancos = [
        {
            "banco": x.banco,
            "tipo_cuenta": x.tipo_cuenta,
            "numero_cuenta": x.numero_cuenta,
            "titular": x.titular,
            "rut_titular": x.rut_titular,
            "email_pago": x.email_pago,
            "es_principal": x.es_principal,
            "activo": x.activo,
        }
        for x in (prov.bancos or [])
    ]

    contactos = [
        {
            "nombre": x.nombre,
            "cargo": x.cargo,
            "email": x.email,
            "telefono": x.telefono,
            "es_principal": x.es_principal,
            "activo": x.activo,
        }
        for x in (prov.contactos or [])
    ]

    direcciones = [
        {
            "linea1": x.linea1,
            "linea2": x.linea2,
            "comuna": x.comuna,
            "ciudad": x.ciudad,
            "region": x.region,
            "pais": x.pais,
            "codigo_postal": x.codigo_postal,
            "es_principal": x.es_principal,
            "activo": x.activo,
        }
        for x in (prov.direcciones or [])
    ]

    return templates.TemplateResponse(
        "proveedores/form_proveedor.html",
        {
            "request": request,
            "active_menu": "proveedores",
            "modo": "editar",
            "proveedor": prov,
            "proveedor_fin": prov_fin,
            "resumen_financiero": resumen_financiero,
            "bancos_iniciales": bancos,
            "contactos_iniciales": contactos,
            "direcciones_iniciales": direcciones,
            "msg": msg,
            "sev": sev,
        },
    )


@router.post("/{proveedor_id}/editar", name="proveedor_actualizar")
def proveedor_actualizar(
    request: Request,
    proveedor_id: int,
    rut: str = Form(...),
    razon_social: str = Form(...),
    nombre_fantasia: Optional[str] = Form(None),
    giro: Optional[str] = Form(None),
    email: Optional[str] = Form(None),
    telefono: Optional[str] = Form(None),
    sitio_web: Optional[str] = Form(None),
    condicion_pago_dias: int = Form(30),
    limite_credito: str = Form("0"),
    activo: Optional[str] = Form(None),
    notas: Optional[str] = Form(None),
    bancos_json: str = Form("[]"),
    contactos_json: str = Form("[]"),
    direcciones_json: str = Form("[]"),
    fin_condicion_pago_dias: int = Form(30),
    fin_limite_credito: str = Form("0"),
    fin_estado: str = Form("ACTIVO"),
    fin_notas: Optional[str] = Form(None),
    db: Session = Depends(get_db),
):
    try:
        payload = ProveedorUpdate(
            **_payload_desde_form(
                rut=rut,
                razon_social=razon_social,
                nombre_fantasia=nombre_fantasia,
                giro=giro,
                email=email,
                telefono=telefono,
                sitio_web=sitio_web,
                condicion_pago_dias=condicion_pago_dias,
                limite_credito=limite_credito,
                activo=activo,
                notas=notas,
                bancos_json=bancos_json,
                contactos_json=contactos_json,
                direcciones_json=direcciones_json,
            )
        )

        crud_proveedor.update_proveedor(db, proveedor_id, payload)

        payload_fin = _payload_fin_desde_form(
            fin_condicion_pago_dias=fin_condicion_pago_dias,
            fin_limite_credito=fin_limite_credito,
            fin_estado=fin_estado,
            fin_notas=fin_notas,
        )
        crud_proveedor_fin.upsert(db, payload_fin, proveedor_id)

        return _redirect(
            request,
            "proveedor_editar",
            "Proveedor actualizado correctamente.",
            "success",
            proveedor_id=proveedor_id,
        )

    except Exception as e:
        logger.exception("Actualizar proveedor proveedor_id=%s", proveedor_id)
        return _redirect(
            request,
            "proveedor_editar",
            public_error_message(e, default="No se pudo actualizar el proveedor."),
            "danger",
            proveedor_id=proveedor_id,
        )


@router.post("/{proveedor_id}/estado", name="proveedor_estado")
def proveedor_estado(
    request: Request,
    proveedor_id: int,
    activo: str = Form(...),
    db: Session = Depends(get_db),
):
    try:
        crud_proveedor.cambiar_estado(db, proveedor_id, activo.strip().lower() == "true")
        return _redirect(
            request,
            "proveedor_lista",
            "Estado del proveedor actualizado correctamente.",
            "success",
        )
    except Exception as e:
        logger.exception("Cambiar estado proveedor proveedor_id=%s", proveedor_id)
        return _redirect(
            request,
            "proveedor_lista",
            public_error_message(e, default="No se pudo cambiar el estado del proveedor."),
            "danger",
        )


@router.post("/{proveedor_id}/eliminar", name="proveedor_eliminar")
def proveedor_eliminar(
    request: Request,
    proveedor_id: int,
    db: Session = Depends(get_db),
):
    try:
        crud_proveedor_fin.delete_by_proveedor_id(db, proveedor_id)
        crud_proveedor.delete_proveedor(db, proveedor_id)
        return _redirect(
            request,
            "proveedor_lista",
            "Proveedor eliminado correctamente.",
            "success",
        )
    except Exception as e:
        logger.exception("Eliminar proveedor proveedor_id=%s", proveedor_id)
        return _redirect(
            request,
            "proveedor_lista",
            public_error_message(e, default="No se pudo eliminar el proveedor."),
            "danger",
        )