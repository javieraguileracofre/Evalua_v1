# routes/ui/transporte_viajes.py
# -*- coding: utf-8 -*-
"""Transporte: hojas de ruta (viajes) y tablero comparativo."""
from __future__ import annotations

import logging
from datetime import datetime
from decimal import Decimal, InvalidOperation
from typing import Any, Optional
from urllib.parse import urlencode

from fastapi import APIRouter, Depends, Query, Request, status
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from core.paths import TEMPLATES_DIR
from core.public_errors import public_error_message
from crud import fondos_rendir as crud_fr
from crud import transporte_viajes as crud_tv
from crud.fondos_rendir import parse_fecha_formulario
from db.session import get_db
from models.maestros.cliente import Cliente
from models.transporte.viaje import ESTADOS_VIAJE

router = APIRouter(prefix="/transporte", tags=["Transporte"])
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


def _form_to_dict(form: Any) -> dict[str, Any]:
    out: dict[str, Any] = {}
    try:
        keys = list(form.keys())
    except Exception:
        keys = [k for k in form]
    for k in keys:
        out[str(k)] = form.get(k)
    return out


def _parse_int(v: Any) -> int | None:
    if v is None or str(v).strip() == "":
        return None
    try:
        return int(str(v).strip())
    except ValueError:
        return None


def _parse_decimal(v: Any) -> Decimal | None:
    if v is None or str(v).strip() == "":
        return None
    try:
        return Decimal(str(v).strip().replace(",", "."))
    except (InvalidOperation, ValueError):
        return None


def _listar_clientes_activos(db: Session) -> list[Cliente]:
    return list(
        db.scalars(
            select(Cliente).where(Cliente.activo.is_(True)).order_by(Cliente.razon_social)
        ).all()
    )


# --- Hub / dashboard ---


@router.get("", response_class=HTMLResponse, name="transporte_hub")
def transporte_hub(
    request: Request,
    db: Session = Depends(get_db),
    msg: Optional[str] = Query(None),
    sev: str = Query("info"),
):
    stats = crud_tv.dashboard_stats(db, dias=120)
    fuel = crud_tv.indicadores_combustible(db, dias=120)
    choferes = crud_tv.comparativo_choferes(db, dias=120, top=14)
    vehiculos = crud_tv.comparativo_vehiculos(db, dias=120, top=10)
    ultimos = crud_tv.ultimos_viajes_resumen(db, limite=18)
    chart_chofer = {
        "labels": [(c["nombre"] or "")[:24] for c in choferes],
        "km_total": [float(c["km_total"] or 0) for c in choferes],
        "horas_promedio": [float(c["horas_promedio"] or 0) for c in choferes],
        "l100": [float(c["l100_promedio"] or 0) for c in choferes],
    }
    chart_flota = {
        "labels": [(v["patente"] or "")[:16] for v in vehiculos],
        "l100": [float(v["l100_promedio"] or 0) for v in vehiculos],
        "ref_l100": [float(v["referencial_l100"] or 0) for v in vehiculos],
    }
    return templates.TemplateResponse(
        "transporte/hub.html",
        {
            "request": request,
            "active_menu": "transporte",
            "stats": stats,
            "comparativo_choferes": choferes,
            "comparativo_vehiculos": vehiculos,
            "ultimos_viajes": ultimos,
            "chart_chofer": chart_chofer,
            "chart_flota": chart_flota,
            "fuel": fuel,
            "msg": msg,
            "sev": sev,
        },
    )


# --- Lista ---


@router.get("/viajes", response_class=HTMLResponse, name="transporte_viajes_lista")
def transporte_viajes_lista(
    request: Request,
    db: Session = Depends(get_db),
    estado: Optional[str] = Query(None),
    empleado_id: Optional[int] = Query(None),
    msg: Optional[str] = Query(None),
    sev: str = Query("info"),
):
    viajes = crud_tv.listar_viajes(db, estado=estado, empleado_id=empleado_id, limite=400)
    empleados = crud_fr.listar_empleados(db, solo_activos=True)
    return templates.TemplateResponse(
        "transporte/viajes_lista.html",
        {
            "request": request,
            "active_menu": "transporte",
            "viajes": viajes,
            "empleados": empleados,
            "filtro_estado": estado,
            "filtro_empleado_id": empleado_id,
            "estados_viaje": ESTADOS_VIAJE,
            "msg": msg,
            "sev": sev,
        },
    )


# --- Nuevo / editar ---


@router.get("/viajes/nuevo", response_class=HTMLResponse, name="transporte_viaje_nuevo")
def transporte_viaje_nuevo(request: Request, db: Session = Depends(get_db)):
    empleados = crud_fr.listar_empleados(db, solo_activos=True)
    vehiculos = crud_fr.listar_vehiculos_transporte(db, solo_activos=True)
    clientes = _listar_clientes_activos(db)
    fondos = crud_tv.listar_fondos_para_viaje(db)
    fecha_default = datetime.now().strftime("%Y-%m-%dT%H:%M")
    return templates.TemplateResponse(
        "transporte/viaje_form.html",
        {
            "request": request,
            "active_menu": "transporte",
            "modo": "nuevo",
            "viaje": None,
            "empleados": empleados,
            "vehiculos": vehiculos,
            "clientes": clientes,
            "fondos": fondos,
            "fecha_default": fecha_default,
        },
    )


@router.post("/viajes/nuevo", name="transporte_viaje_crear")
async def transporte_viaje_crear(request: Request, db: Session = Depends(get_db)):
    fd = _form_to_dict(await request.form())
    try:
        crud_tv.crear_viaje(
            db,
            empleado_id=int(fd.get("empleado_id") or 0),
            vehiculo_transporte_id=_parse_int(fd.get("vehiculo_transporte_id")),
            cliente_id=_parse_int(fd.get("cliente_id")),
            fondo_rendir_id=_parse_int(fd.get("fondo_rendir_id")),
            origen=str(fd.get("origen") or ""),
            destino=str(fd.get("destino") or ""),
            referencia_carga=str(fd.get("referencia_carga") or "") or None,
            programado_salida=parse_fecha_formulario(str(fd.get("programado_salida") or "") or None),
            programado_llegada=parse_fecha_formulario(str(fd.get("programado_llegada") or "") or None),
            notas=str(fd.get("notas") or "") or None,
        )
        db.commit()
    except (ValueError, TypeError) as e:
        db.rollback()
        return _redirect(request, "transporte_viaje_nuevo", msg=public_error_message(e), sev="danger")
    except SQLAlchemyError:
        db.rollback()
        logger.exception("transporte_viaje_crear")
        return _redirect(
            request,
            "transporte_viaje_nuevo",
            msg="No se pudo crear el viaje.",
            sev="danger",
        )
    return _redirect(
        request,
        "transporte_viajes_lista",
        msg="Hoja de ruta creada en borrador.",
        sev="success",
    )


@router.get("/viajes/{viaje_id}/editar", response_class=HTMLResponse, name="transporte_viaje_editar")
def transporte_viaje_editar(request: Request, viaje_id: int, db: Session = Depends(get_db)):
    v = crud_tv.obtener_viaje(db, viaje_id)
    if not v:
        return _redirect(request, "transporte_viajes_lista", msg="Viaje no encontrado.", sev="warning")
    if v.estado not in ("BORRADOR", "CERRADO"):
        return _redirect(
            request,
            "transporte_viaje_detalle",
            viaje_id=viaje_id,
            msg="Solo se pueden corregir viajes en BORRADOR o CERRADO.",
            sev="info",
        )
    empleados = crud_fr.listar_empleados(db, solo_activos=True)
    vehiculos = crud_fr.listar_vehiculos_transporte(db, solo_activos=True)
    clientes = _listar_clientes_activos(db)
    fondos = crud_tv.listar_fondos_para_viaje(db)
    return templates.TemplateResponse(
        "transporte/viaje_form.html",
        {
            "request": request,
            "active_menu": "transporte",
            "modo": "editar",
            "viaje": v,
            "empleados": empleados,
            "vehiculos": vehiculos,
            "clientes": clientes,
            "fondos": fondos,
            "fecha_default": None,
        },
    )


@router.post("/viajes/{viaje_id}/editar", name="transporte_viaje_actualizar")
async def transporte_viaje_actualizar(request: Request, viaje_id: int, db: Session = Depends(get_db)):
    v = crud_tv.obtener_viaje(db, viaje_id)
    if not v:
        return _redirect(request, "transporte_viajes_lista", msg="Viaje no encontrado.", sev="warning")
    fd = _form_to_dict(await request.form())
    try:
        crud_tv.actualizar_viaje_corregible(
            db,
            v,
            empleado_id=int(fd.get("empleado_id") or 0),
            vehiculo_transporte_id=_parse_int(fd.get("vehiculo_transporte_id")),
            cliente_id=_parse_int(fd.get("cliente_id")),
            fondo_rendir_id=_parse_int(fd.get("fondo_rendir_id")),
            origen=str(fd.get("origen") or ""),
            destino=str(fd.get("destino") or ""),
            referencia_carga=str(fd.get("referencia_carga") or "") or None,
            programado_salida=parse_fecha_formulario(str(fd.get("programado_salida") or "") or None),
            programado_llegada=parse_fecha_formulario(str(fd.get("programado_llegada") or "") or None),
            notas=str(fd.get("notas") or "") or None,
        )
        db.commit()
    except ValueError as e:
        db.rollback()
        return _redirect(request, "transporte_viaje_editar", viaje_id=viaje_id, msg=public_error_message(e), sev="danger")
    except SQLAlchemyError:
        db.rollback()
        return _redirect(
            request,
            "transporte_viaje_editar",
            viaje_id=viaje_id,
            msg="No se pudo guardar.",
            sev="danger",
        )
    return _redirect(
        request,
        "transporte_viaje_detalle",
        viaje_id=viaje_id,
        msg="Corrección guardada.",
        sev="success",
    )


# --- Detalle + acciones ---


@router.get("/viajes/{viaje_id}", response_class=HTMLResponse, name="transporte_viaje_detalle")
def transporte_viaje_detalle(
    request: Request,
    viaje_id: int,
    db: Session = Depends(get_db),
    msg: Optional[str] = Query(None),
    sev: str = Query("info"),
):
    v = crud_tv.obtener_viaje(db, viaje_id)
    if not v:
        return _redirect(request, "transporte_viajes_lista", msg="Viaje no encontrado.", sev="warning")
    metricas = crud_tv.metricas_viaje_dict(v)
    fecha_default = datetime.now().strftime("%Y-%m-%dT%H:%M")
    return templates.TemplateResponse(
        "transporte/viaje_detalle.html",
        {
            "request": request,
            "active_menu": "transporte",
            "viaje": v,
            "metricas": metricas,
            "fecha_default": fecha_default,
            "msg": msg,
            "sev": sev,
        },
    )


@router.post("/viajes/{viaje_id}/iniciar", name="transporte_viaje_iniciar")
async def transporte_viaje_iniciar(request: Request, viaje_id: int, db: Session = Depends(get_db)):
    v = crud_tv.obtener_viaje(db, viaje_id)
    if not v:
        return _redirect(request, "transporte_viajes_lista", msg="Viaje no encontrado.", sev="warning")
    fd = _form_to_dict(await request.form())
    rs = parse_fecha_formulario(str(fd.get("real_salida") or "") or None)
    if rs is None:
        return _redirect(
            request,
            "transporte_viaje_detalle",
            viaje_id=viaje_id,
            msg="Indique una fecha/hora de salida válida.",
            sev="danger",
        )
    oi = _parse_int(fd.get("odometro_inicio"))
    if oi is None:
        return _redirect(
            request,
            "transporte_viaje_detalle",
            viaje_id=viaje_id,
            msg="Indique odómetro de salida.",
            sev="danger",
        )
    try:
        crud_tv.iniciar_viaje(db, v, real_salida=rs, odometro_inicio=oi)
        db.commit()
    except ValueError as e:
        db.rollback()
        return _redirect(request, "transporte_viaje_detalle", viaje_id=viaje_id, msg=public_error_message(e), sev="danger")
    except SQLAlchemyError:
        db.rollback()
        return _redirect(
            request,
            "transporte_viaje_detalle",
            viaje_id=viaje_id,
            msg="No se pudo iniciar el viaje.",
            sev="danger",
        )
    return _redirect(
        request,
        "transporte_viaje_detalle",
        viaje_id=viaje_id,
        msg="Viaje en curso. Registre el cierre al finalizar.",
        sev="success",
    )


@router.post("/viajes/{viaje_id}/cerrar", name="transporte_viaje_cerrar")
async def transporte_viaje_cerrar(request: Request, viaje_id: int, db: Session = Depends(get_db)):
    v = crud_tv.obtener_viaje(db, viaje_id)
    if not v:
        return _redirect(request, "transporte_viajes_lista", msg="Viaje no encontrado.", sev="warning")
    fd = _form_to_dict(await request.form())
    rl = parse_fecha_formulario(str(fd.get("real_llegada") or "") or None)
    if rl is None:
        return _redirect(
            request,
            "transporte_viaje_detalle",
            viaje_id=viaje_id,
            msg="Indique una fecha/hora de llegada válida.",
            sev="danger",
        )
    of = _parse_int(fd.get("odometro_fin"))
    if of is None:
        return _redirect(
            request,
            "transporte_viaje_detalle",
            viaje_id=viaje_id,
            msg="Indique odómetro de llegada.",
            sev="danger",
        )
    lit = _parse_decimal(fd.get("litros_combustible"))
    motivo_desvio = str(fd.get("motivo_desvio") or "")
    observaciones_cierre = str(fd.get("observaciones_cierre") or "")
    try:
        crud_tv.cerrar_viaje(
            db,
            v,
            real_llegada=rl,
            odometro_fin=of,
            litros_combustible=lit,
            motivo_desvio=motivo_desvio,
            observaciones_cierre=observaciones_cierre,
        )
        db.commit()
    except ValueError as e:
        db.rollback()
        return _redirect(request, "transporte_viaje_detalle", viaje_id=viaje_id, msg=public_error_message(e), sev="danger")
    except SQLAlchemyError:
        db.rollback()
        return _redirect(
            request,
            "transporte_viaje_detalle",
            viaje_id=viaje_id,
            msg="No se pudo cerrar el viaje.",
            sev="danger",
        )
    return _redirect(
        request,
        "transporte_viaje_detalle",
        viaje_id=viaje_id,
        msg="Viaje cerrado. Métricas disponibles en el tablero.",
        sev="success",
    )


@router.post("/viajes/{viaje_id}/anular", name="transporte_viaje_anular")
async def transporte_viaje_anular(request: Request, viaje_id: int, db: Session = Depends(get_db)):
    v = crud_tv.obtener_viaje(db, viaje_id)
    if not v:
        return _redirect(request, "transporte_viajes_lista", msg="Viaje no encontrado.", sev="warning")
    fd = _form_to_dict(await request.form())
    motivo = str(fd.get("motivo_anulacion") or "").strip()
    if not motivo:
        return _redirect(
            request,
            "transporte_viaje_detalle",
            viaje_id=viaje_id,
            msg="Indique el motivo de anulación.",
            sev="danger",
        )
    try:
        crud_tv.anular_viaje(db, v, motivo=motivo)
        db.commit()
    except ValueError as e:
        db.rollback()
        return _redirect(request, "transporte_viaje_detalle", viaje_id=viaje_id, msg=public_error_message(e), sev="danger")
    except SQLAlchemyError:
        db.rollback()
        return _redirect(
            request,
            "transporte_viaje_detalle",
            viaje_id=viaje_id,
            msg="No se pudo anular.",
            sev="danger",
        )
    return _redirect(
        request,
        "transporte_viajes_lista",
        msg="Viaje anulado.",
        sev="warning",
    )


@router.post("/viajes/{viaje_id}/eliminar", name="transporte_viaje_eliminar")
async def transporte_viaje_eliminar(request: Request, viaje_id: int, db: Session = Depends(get_db)):
    v = crud_tv.obtener_viaje(db, viaje_id)
    if not v:
        return _redirect(request, "transporte_viajes_lista", msg="Viaje no encontrado.", sev="warning")
    try:
        crud_tv.eliminar_viaje(db, v)
        db.commit()
    except ValueError as e:
        db.rollback()
        return _redirect(request, "transporte_viaje_detalle", viaje_id=viaje_id, msg=public_error_message(e), sev="danger")
    except SQLAlchemyError:
        db.rollback()
        return _redirect(
            request,
            "transporte_viaje_detalle",
            viaje_id=viaje_id,
            msg="No se pudo borrar la hoja de ruta.",
            sev="danger",
        )
    return _redirect(
        request,
        "transporte_viajes_lista",
        msg="Hoja de ruta eliminada.",
        sev="success",
    )
