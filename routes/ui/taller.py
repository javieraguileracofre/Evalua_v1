# routes/ui/taller.py
# -*- coding: utf-8 -*-
"""Taller automotriz: órdenes de servicio y vehículos."""
from __future__ import annotations

import json
import logging
from datetime import datetime
from typing import Any, Optional
from urllib.parse import urlencode

from fastapi import APIRouter, Depends, Query, Request, status
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from core.paths import TEMPLATES_DIR
from core.public_errors import public_error_message
from crud.comercial import taller as crud_taller
from db.session import get_db
from models import Cliente

router = APIRouter(prefix="/taller", tags=["Taller"])
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))
logger = logging.getLogger(__name__)


def _redirect(
    request: Request,
    route_name: str,
    *,
    msg: str | None = None,
    sev: str = "info",
    **path_params: Any,
) -> RedirectResponse:
    url = str(request.url_for(route_name, **path_params))
    if msg:
        q = urlencode({"msg": msg, "sev": sev})
        sep = "&" if "?" in url else "?"
        url = f"{url}{sep}{q}"
    return RedirectResponse(url=url, status_code=status.HTTP_303_SEE_OTHER)


def _parse_dt(value: str | None, *, required: bool = False) -> datetime | None:
    if not value or not str(value).strip():
        return None if not required else datetime.utcnow()
    raw = str(value).strip().replace("T", " ")
    try:
        return datetime.fromisoformat(raw)
    except ValueError:
        pass
    for fmt in ("%Y-%m-%d %H:%M", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
        try:
            return datetime.strptime(raw[: len(fmt)], fmt)
        except ValueError:
            continue
    if required:
        return datetime.utcnow()
    return None


def _parse_int(value: str | None) -> int | None:
    if value is None or str(value).strip() == "":
        return None
    try:
        return int(str(value).strip(), 10)
    except ValueError:
        return None


def _ingreso_grua_desde_form(fd: dict[str, Any]) -> bool | None:
    v = fd.get("ingreso_grua")
    if v is None or str(v).strip() == "":
        return None
    s = str(v).strip().upper()
    if s == "SI":
        return True
    if s == "NO":
        return False
    return None


def _cotizacion_afecta_iva_desde_form(fd: dict[str, Any]) -> bool:
    return _bool_form(fd.get("cotizacion_afecta_iva"))


def _bool_form(v: Any) -> bool:
    if v is None:
        return False
    s = str(v).strip().lower()
    return s in ("1", "true", "on", "yes", "si", "sí")


def _lineas_cotizacion_json_template(orden: Any) -> str:
    if not orden or not getattr(orden, "lineas_cotizacion", None):
        return "[]"
    rows: list[dict[str, Any]] = []
    for L in sorted(orden.lineas_cotizacion, key=lambda x: x.linea):
        rows.append(
            {
                "descripcion": L.descripcion,
                "cantidad": str(L.cantidad),
                "precio_unitario": str(L.precio_unitario),
            }
        )
    return json.dumps(rows, ensure_ascii=False)


def _form_to_dict(form: Any) -> dict[str, Any]:
    """Starlette FormData: iterar claves de forma compatible."""
    out: dict[str, Any] = {}
    try:
        keys = list(form.keys())
    except Exception:
        keys = [k for k in form]
    for k in keys:
        out[str(k)] = form.get(k)
    return out


@router.get("", response_class=HTMLResponse, name="taller_hub")
def taller_hub(
    request: Request,
    db: Session = Depends(get_db),
    msg: Optional[str] = Query(None),
    sev: str = Query("info"),
):
    stats = crud_taller.conteos_hub(db)
    ultimas_ordenes = crud_taller.listar_ordenes(db, limit=25)
    return templates.TemplateResponse(
        "taller/hub.html",
        {
            "request": request,
            "active_menu": "taller",
            "stats": stats,
            "ultimas_ordenes": ultimas_ordenes,
            "msg": msg,
            "sev": sev,
        },
    )


@router.get("/ordenes", response_class=HTMLResponse, name="taller_ordenes_lista")
def taller_ordenes_lista(
    request: Request,
    db: Session = Depends(get_db),
    estado: Optional[str] = Query(None),
    msg: Optional[str] = Query(None),
    sev: str = Query("info"),
):
    ordenes = crud_taller.listar_ordenes(db, estado=estado)
    return templates.TemplateResponse(
        "taller/orden_lista.html",
        {
            "request": request,
            "active_menu": "taller",
            "ordenes": ordenes,
            "filtro_estado": estado,
            "estados": crud_taller.ESTADOS_ORDEN,
            "msg": msg,
            "sev": sev,
        },
    )


@router.get("/ordenes/nueva", response_class=HTMLResponse, name="taller_orden_nueva")
def taller_orden_nueva(
    request: Request,
    db: Session = Depends(get_db),
    cliente_id: Optional[int] = Query(None),
    msg: Optional[str] = Query(None),
    sev: str = Query("info"),
):
    clientes = db.query(Cliente).filter(Cliente.activo.is_(True)).order_by(Cliente.razon_social).all()
    vehiculos = []
    if cliente_id:
        vehiculos = crud_taller.listar_vehiculos_cliente(db, cliente_id)
    fecha_default = datetime.now().strftime("%Y-%m-%dT%H:%M")
    return templates.TemplateResponse(
        "taller/orden_form.html",
        {
            "request": request,
            "active_menu": "taller",
            "modo": "nueva",
            "orden": None,
            "clientes": clientes,
            "cliente_pre": cliente_id,
            "vehiculos": vehiculos,
            "estados": crud_taller.ESTADOS_ORDEN,
            "niveles_comb": crud_taller.NIVELES_COMBUSTIBLE,
            "testigo_labels": crud_taller.TESTIGO_LABELS,
            "inv_labels": crud_taller.INV_LABELS,
            "checks_state": {},
            "fecha_default": fecha_default,
            "lineas_cotizacion_json": "[]",
            "msg": msg,
            "sev": sev,
        },
    )


@router.post("/ordenes/nueva", name="taller_orden_crear")
async def taller_orden_crear(request: Request, db: Session = Depends(get_db)):
    form = await request.form()
    fd = _form_to_dict(form)

    try:
        cliente_id = int(fd.get("cliente_id") or 0)
    except (TypeError, ValueError):
        return _redirect(
            request,
            "taller_orden_nueva",
            msg="Seleccione un cliente válido en el listado e intente nuevamente.",
            sev="danger",
        )

    vid_raw = fd.get("vehiculo_id")
    vehiculo_id: int | None = None
    nuevo: dict[str, Any] | None = None

    if str(vid_raw or "") == "nuevo":
        nuevo = {
            "patente": str(fd.get("nv_patente") or ""),
            "marca": str(fd.get("nv_marca") or ""),
            "modelo": str(fd.get("nv_modelo") or ""),
            "color": str(fd.get("nv_color") or "") or None,
            "anio": _parse_int(fd.get("nv_anio")),
            "vin": str(fd.get("nv_vin") or "") or None,
            "km_actual": _parse_int(fd.get("nv_km")),
        }
    elif vid_raw not in (None, "", "0"):
        try:
            vehiculo_id = int(vid_raw)
        except (TypeError, ValueError):
            return _redirect(
                request,
                "taller_orden_nueva",
                msg="Indique un vehículo existente o elija la opción para registrar uno nuevo.",
                sev="danger",
            )
    else:
        return _redirect(
            request,
            "taller_orden_nueva",
            msg="Debe asociar un vehículo a la orden: elija uno de la lista o complete el registro de un vehículo nuevo.",
            sev="danger",
        )

    fr = _parse_dt(fd.get("fecha_recepcion"), required=True)
    assert fr is not None
    fent = _parse_dt(fd.get("fecha_entrega_estimada"), required=False)

    estado = str(fd.get("estado") or "RECIBIDA").strip().upper()
    nivel = str(fd.get("nivel_combustible") or "").strip() or None

    checks = crud_taller.campos_check_desde_form(fd)
    danos = {
        "frente": (str(fd.get("dano_vista_frente") or "").strip() or None),
        "atras": (str(fd.get("dano_vista_atras") or "").strip() or None),
        "izquierda": (str(fd.get("dano_vista_izquierda") or "").strip() or None),
        "derecha": (str(fd.get("dano_vista_derecha") or "").strip() or None),
    }

    try:
        lineas_cot = crud_taller.parse_cotizacion_json(
            str(fd.get("cotizacion_json") or "") if fd.get("cotizacion_json") else None
        )
    except ValueError as e:
        return _redirect(request, "taller_orden_nueva", msg=public_error_message(e), sev="danger")

    try:
        orden = crud_taller.crear_orden_servicio(
            db,
            cliente_id=cliente_id,
            vehiculo_id=vehiculo_id,
            nuevo_vehiculo=nuevo,
            fecha_recepcion=fr,
            fecha_entrega_estimada=fent,
            contacto_nombre=str(fd.get("contacto_nombre") or "") or None,
            contacto_telefono=str(fd.get("contacto_telefono") or "") or None,
            trabajo_solicitado=str(fd.get("trabajo_solicitado") or "") or None,
            observaciones=str(fd.get("observaciones") or "") or None,
            estado=estado,
            campos_check=checks,
            nivel_combustible=nivel,
            danos=danos,
            pagare_monto=None,
            pagare_ciudad=None,
            pagare_tasa=None,
            ingreso_grua=_ingreso_grua_desde_form(fd),
            ote_num=str(fd.get("ote_num") or "") or None,
            email_contacto=str(fd.get("email_contacto") or "") or None,
            cotizacion_afecta_iva=_cotizacion_afecta_iva_desde_form(fd),
        )
        crud_taller.sync_lineas_cotizacion(db, int(orden.id), lineas_cot)
        db.commit()
        db.refresh(orden)
    except ValueError as e:
        db.rollback()
        return _redirect(request, "taller_orden_nueva", msg=public_error_message(e), sev="danger")
    except SQLAlchemyError:
        db.rollback()
        logger.exception("Taller: no se pudo guardar la orden de servicio")
        return _redirect(
            request,
            "taller_orden_nueva",
            msg="No pudimos registrar la orden. Compruebe la conexión a la base de datos, permisos del usuario y que existan las tablas del módulo Taller.",
            sev="danger",
        )

    return _redirect(
        request,
        "taller_orden_detalle",
        orden_id=orden.id,
        msg="La orden quedó registrada correctamente. Puede revisar el detalle, continuar la edición o imprimir el documento.",
        sev="success",
    )


@router.get("/ordenes/{orden_id}", response_class=HTMLResponse, name="taller_orden_detalle")
def taller_orden_detalle(
    request: Request,
    orden_id: int,
    db: Session = Depends(get_db),
    msg: Optional[str] = Query(None),
    sev: str = Query("info"),
):
    orden = crud_taller.obtener_orden(db, orden_id)
    if not orden:
        return _redirect(
            request,
            "taller_ordenes_lista",
            msg="No encontramos esa orden. Puede haber sido eliminada o el enlace ya no es válido.",
            sev="warning",
        )
    sub = crud_taller.subtotal_desde_lineas_orm(list(orden.lineas_cotizacion))
    tot = crud_taller.totales_cotizacion(sub, afecta_iva=bool(orden.cotizacion_afecta_iva))
    return templates.TemplateResponse(
        "taller/orden_detalle.html",
        {
            "request": request,
            "active_menu": "taller",
            "orden": orden,
            "totales_cot": tot,
            "msg": msg,
            "sev": sev,
        },
    )


@router.get("/ordenes/{orden_id}/editar", response_class=HTMLResponse, name="taller_orden_editar")
def taller_orden_editar(
    request: Request,
    orden_id: int,
    db: Session = Depends(get_db),
    msg: Optional[str] = Query(None),
    sev: str = Query("info"),
):
    orden = crud_taller.obtener_orden(db, orden_id)
    if not orden:
        return _redirect(
            request,
            "taller_ordenes_lista",
            msg="No encontramos esa orden. Puede haber sido eliminada o el enlace ya no es válido.",
            sev="warning",
        )
    clientes = db.query(Cliente).filter(Cliente.activo.is_(True)).order_by(Cliente.razon_social).all()
    vehiculos = crud_taller.listar_vehiculos_cliente(db, orden.cliente_id)
    checks_state = crud_taller.checks_desde_orden(orden)
    return templates.TemplateResponse(
        "taller/orden_form.html",
        {
            "request": request,
            "active_menu": "taller",
            "modo": "editar",
            "orden": orden,
            "clientes": clientes,
            "cliente_pre": orden.cliente_id,
            "vehiculos": vehiculos,
            "estados": crud_taller.ESTADOS_ORDEN,
            "niveles_comb": crud_taller.NIVELES_COMBUSTIBLE,
            "testigo_labels": crud_taller.TESTIGO_LABELS,
            "inv_labels": crud_taller.INV_LABELS,
            "checks_state": checks_state,
            "fecha_default": None,
            "lineas_cotizacion_json": _lineas_cotizacion_json_template(orden),
            "msg": msg,
            "sev": sev,
        },
    )


@router.post("/ordenes/{orden_id}/editar", name="taller_orden_actualizar")
async def taller_orden_actualizar(
    request: Request,
    orden_id: int,
    db: Session = Depends(get_db),
):
    form = await request.form()
    fd = _form_to_dict(form)

    fr = _parse_dt(fd.get("fecha_recepcion"), required=False)
    fent = _parse_dt(fd.get("fecha_entrega_estimada"), required=False)
    estado = str(fd.get("estado") or "RECIBIDA").strip().upper()
    nivel = str(fd.get("nivel_combustible") or "").strip() or None
    checks = crud_taller.campos_check_desde_form(fd)
    danos = {
        "frente": (str(fd.get("dano_vista_frente") or "").strip() or None),
        "atras": (str(fd.get("dano_vista_atras") or "").strip() or None),
        "izquierda": (str(fd.get("dano_vista_izquierda") or "").strip() or None),
        "derecha": (str(fd.get("dano_vista_derecha") or "").strip() or None),
    }

    try:
        lineas_cot = crud_taller.parse_cotizacion_json(
            str(fd.get("cotizacion_json") or "") if fd.get("cotizacion_json") else None
        )
    except ValueError as e:
        return _redirect(
            request,
            "taller_orden_editar",
            orden_id=orden_id,
            msg=public_error_message(e),
            sev="danger",
        )

    try:
        orden = crud_taller.actualizar_orden_servicio(
            db,
            orden_id,
            fecha_recepcion=fr,
            estado=estado,
            fecha_entrega_estimada=fent,
            contacto_nombre=str(fd.get("contacto_nombre") or "") or None,
            contacto_telefono=str(fd.get("contacto_telefono") or "") or None,
            trabajo_solicitado=str(fd.get("trabajo_solicitado") or "") or None,
            observaciones=str(fd.get("observaciones") or "") or None,
            campos_check=checks,
            nivel_combustible=nivel,
            danos=danos,
            pagare_monto=None,
            pagare_ciudad=None,
            pagare_tasa=None,
            ingreso_grua=_ingreso_grua_desde_form(fd),
            ote_num=str(fd.get("ote_num") or "") or None,
            email_contacto=str(fd.get("email_contacto") or "") or None,
            cotizacion_afecta_iva=_cotizacion_afecta_iva_desde_form(fd),
        )
        crud_taller.sync_lineas_cotizacion(db, orden_id, lineas_cot)
        db.commit()
        db.refresh(orden)
    except ValueError as e:
        db.rollback()
        return _redirect(
            request,
            "taller_orden_editar",
            orden_id=orden_id,
            msg=public_error_message(e),
            sev="danger",
        )
    except SQLAlchemyError:
        db.rollback()
        logger.exception("Taller: error al actualizar orden %s", orden_id)
        return _redirect(
            request,
            "taller_orden_editar",
            orden_id=orden_id,
            msg="No pudimos aplicar los cambios. Verifique la conexión a la base de datos o contacte a soporte si el problema continúa.",
            sev="danger",
        )

    return _redirect(
        request,
        "taller_orden_detalle",
        orden_id=orden.id,
        msg="Los cambios se guardaron correctamente. El detalle de la orden refleja la información más reciente.",
        sev="success",
    )


@router.get("/ordenes/{orden_id}/imprimir", response_class=HTMLResponse, name="taller_orden_imprimir")
def taller_orden_imprimir(
    request: Request,
    orden_id: int,
    db: Session = Depends(get_db),
):
    orden = crud_taller.obtener_orden(db, orden_id)
    if not orden:
        return _redirect(
            request,
            "taller_ordenes_lista",
            msg="No encontramos esa orden. Puede haber sido eliminada o el enlace ya no es válido.",
            sev="warning",
        )
    checks = crud_taller.checks_desde_orden(orden)
    needle = {"E": -75, "1/4": -35, "1/2": 0, "3/4": 35, "F": 75}.get(orden.nivel_combustible or "", 0)
    sub = crud_taller.subtotal_desde_lineas_orm(list(orden.lineas_cotizacion))
    tot = crud_taller.totales_cotizacion(sub, afecta_iva=bool(orden.cotizacion_afecta_iva))
    lineas_ord = sorted(orden.lineas_cotizacion, key=lambda x: x.linea)
    return templates.TemplateResponse(
        "taller/orden_imprimir.html",
        {
            "request": request,
            "orden": orden,
            "empresa_nombre": "Evalua ERP — Taller",
            "checks": checks,
            "needle_angle": needle,
            "totales_cot": tot,
            "lineas_cotizacion": lineas_ord,
        },
    )
