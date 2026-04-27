# routes/ui/postventa.py
# -*- coding: utf-8 -*-
from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, Form, HTTPException, Query, Request, status
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from core.paths import TEMPLATES_DIR
from core.public_errors import public_error_message
from core.rbac import guard_operacion_consulta, guard_operacion_mutacion
from crud.maestros import cliente as crud_cliente
from crud.postventa import postventa as crud_postventa
from db.session import get_db

router = APIRouter(tags=["Postventa"])
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))
logger = logging.getLogger("evalua.postventa.ui")


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


def _parse_fecha_evento(raw: str | None) -> datetime | None:
    if not raw or not str(raw).strip():
        return None
    try:
        return datetime.fromisoformat(str(raw).strip())
    except ValueError:
        return None


def _parse_duracion(raw: str | None) -> int | None:
    if not raw or not str(raw).strip():
        return None
    try:
        n = int(str(raw).strip())
        return n if n >= 0 else None
    except ValueError:
        return None


def _construir_timeline(
    interacciones: list,
    solicitudes: list,
) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for it in interacciones:
        items.append(
            {
                "tipo": "interaccion",
                "fecha": it.fecha_evento,
                "ref": it,
            }
        )
    for sol in solicitudes:
        items.append(
            {
                "tipo": "solicitud",
                "fecha": sol.fecha_apertura,
                "ref": sol,
            }
        )
    items.sort(key=lambda x: x["fecha"], reverse=True)
    return items


@router.get("/postventa", response_class=HTMLResponse, name="postventa_hub")
def postventa_hub(
    request: Request,
    q: str | None = Query(None),
    msg: str | None = Query(None),
    sev: str = Query("info"),
    db: Session = Depends(get_db),
):
    if (redir := guard_operacion_consulta(request)) is not None:
        return redir
    filas = crud_postventa.listar_clientes_resumen_postventa(db, busqueda=q, limit=100)
    stats = crud_postventa.hub_dashboard_stats(db)
    return templates.TemplateResponse(
        "postventa/hub.html",
        {
            "request": request,
            "q": q,
            "filas": filas,
            "stats": stats,
            "msg": msg,
            "sev": sev,
            "active_menu": "postventa",
        },
    )


@router.get("/postventa/cliente/{cliente_id}", response_class=HTMLResponse, name="postventa_ficha_cliente")
def postventa_ficha_cliente(
    request: Request,
    cliente_id: int,
    msg: str | None = Query(None),
    sev: str = Query("info"),
    db: Session = Depends(get_db),
):
    if (redir := guard_operacion_consulta(request)) is not None:
        return redir
    cliente = crud_cliente.get_cliente(db, cliente_id)
    if not cliente:
        raise HTTPException(status_code=404, detail="Cliente no encontrado")

    interacciones = crud_postventa.listar_interacciones(db, cliente_id=cliente_id, limit=100)
    solicitudes = crud_postventa.listar_solicitudes(db, cliente_id=cliente_id, limit=100)
    conteos = crud_postventa.contar_por_cliente(db, cliente_id)
    timeline = _construir_timeline(interacciones, solicitudes)

    return templates.TemplateResponse(
        "postventa/ficha_cliente.html",
        {
            "request": request,
            "cliente": cliente,
            "interacciones": interacciones,
            "solicitudes": solicitudes,
            "timeline": timeline,
            "conteos": conteos,
            "msg": msg,
            "sev": sev,
            "active_menu": "postventa",
        },
    )


@router.post("/postventa/cliente/{cliente_id}/interaccion", name="postventa_registrar_interaccion")
def postventa_registrar_interaccion(
    request: Request,
    cliente_id: int,
    tipo: str = Form(...),
    asunto: str | None = Form(None),
    detalle: str = Form(...),
    duracion_minutos: str | None = Form(None),
    resultado: str | None = Form(None),
    registrado_por: str | None = Form(None),
    fecha_evento: str | None = Form(None),
    db: Session = Depends(get_db),
):
    if (redir := guard_operacion_mutacion(request)) is not None:
        return redir
    cliente = crud_cliente.get_cliente(db, cliente_id)
    if not cliente:
        raise HTTPException(status_code=404)

    try:
        crud_postventa.crear_interaccion(
            db,
            cliente_id=cliente_id,
            tipo=tipo,
            asunto=asunto,
            detalle=detalle,
            duracion_minutos=_parse_duracion(duracion_minutos),
            resultado=resultado,
            registrado_por=registrado_por,
            fecha_evento=_parse_fecha_evento(fecha_evento),
        )
    except Exception as exc:  # pragma: no cover
        logger.exception("Registrar interacción postventa cliente_id=%s", cliente_id)
        return _redirect(
            request,
            "postventa_ficha_cliente",
            cliente_id=cliente_id,
            msg=public_error_message(exc, default="No se pudo registrar la interacción."),
            sev="danger",
        )

    return _redirect(
        request,
        "postventa_ficha_cliente",
        cliente_id=cliente_id,
        msg="Interacción registrada correctamente.",
        sev="success",
    )


@router.post("/postventa/cliente/{cliente_id}/solicitud", name="postventa_registrar_solicitud")
def postventa_registrar_solicitud(
    request: Request,
    cliente_id: int,
    titulo: str = Form(...),
    descripcion: str = Form(...),
    categoria: str = Form(...),
    prioridad: str = Form(...),
    db: Session = Depends(get_db),
):
    if (redir := guard_operacion_mutacion(request)) is not None:
        return redir
    cliente = crud_cliente.get_cliente(db, cliente_id)
    if not cliente:
        raise HTTPException(status_code=404)

    try:
        crud_postventa.crear_solicitud(
            db,
            cliente_id=cliente_id,
            titulo=titulo,
            descripcion=descripcion,
            categoria=categoria,
            prioridad=prioridad,
        )
    except Exception as exc:  # pragma: no cover
        logger.exception("Crear solicitud postventa cliente_id=%s", cliente_id)
        return _redirect(
            request,
            "postventa_ficha_cliente",
            cliente_id=cliente_id,
            msg=public_error_message(exc, default="No se pudo crear la solicitud."),
            sev="danger",
        )

    return _redirect(
        request,
        "postventa_ficha_cliente",
        cliente_id=cliente_id,
        msg="Solicitud registrada correctamente.",
        sev="success",
    )


@router.post("/postventa/solicitud/{solicitud_id}/estado", name="postventa_actualizar_estado_solicitud")
def postventa_actualizar_estado_solicitud(
    request: Request,
    solicitud_id: int,
    estado: str = Form(...),
    db: Session = Depends(get_db),
):
    if (redir := guard_operacion_mutacion(request)) is not None:
        return redir
    sol = crud_postventa.get_solicitud(db, solicitud_id)
    if not sol:
        raise HTTPException(status_code=404)

    actualizado = crud_postventa.actualizar_estado_solicitud(db, solicitud_id=solicitud_id, nuevo_estado=estado)
    if not actualizado:
        return _redirect(
            request,
            "postventa_ficha_cliente",
            cliente_id=sol.cliente_id,
            msg="Estado no válido.",
            sev="warning",
        )

    return _redirect(
        request,
        "postventa_ficha_cliente",
        cliente_id=sol.cliente_id,
        msg="Estado de solicitud actualizado.",
        sev="success",
    )
