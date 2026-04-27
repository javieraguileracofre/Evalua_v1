# routes/ui/postventa.py
# -*- coding: utf-8 -*-
from __future__ import annotations

import logging
from datetime import datetime
from typing import Any
from urllib.parse import urlencode

from fastapi import APIRouter, Depends, Form, HTTPException, Query, Request, status
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from core.paths import TEMPLATES_DIR
from core.public_errors import public_error_message
from core.rbac import guard_operacion_consulta, guard_operacion_mutacion
from crud.auth import usuarios as crud_usuarios
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
    query_params: dict[str, Any] | None = None,
    **path_params: Any,
) -> RedirectResponse:
    url = str(request.url_for(route_name, **path_params))
    qp: dict[str, Any] = {}
    if msg:
        qp["msg"] = msg
        qp["sev"] = sev
    if query_params:
        for k, v in query_params.items():
            if v is not None:
                qp[k] = v
    if qp:
        sep = "&" if "?" in url else "?"
        url = f"{url}{sep}{urlencode(qp)}"
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


def _actor_uid(request: Request) -> int | None:
    auth = getattr(request.state, "auth_user", None) or {}
    uid = auth.get("uid") if isinstance(auth, dict) else None
    try:
        return int(uid) if uid is not None else None
    except Exception:
        return None


def _redirect_caso(
    request: Request,
    caso_id: int,
    *,
    msg: str | None = None,
    sev: str = "info",
) -> RedirectResponse:
    return _redirect(
        request,
        "postventa_caso_detalle",
        caso_id=caso_id,
        msg=msg,
        sev=sev,
    )


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
    filas: list[dict[str, Any]] = []
    stats: dict[str, Any] = {
        "n_interacciones_30d": 0,
        "n_interacciones_total": 0,
        "n_solicitudes_abiertas": 0,
        "n_solicitudes_total": 0,
        "chart": {
            "tipo_labels": [],
            "tipo_counts": [],
            "estado_labels": [],
            "estado_counts": [],
            "prioridad_labels": [],
            "prioridad_counts": [],
            "mes_labels": [],
            "mes_int": [],
            "mes_sol": [],
        },
    }
    metricas: dict[str, Any] = {
        "casos_abiertos": 0,
        "casos_nuevos_7d": 0,
        "casos_nuevos_30d": 0,
        "casos_resueltos_30d": 0,
        "promedio_horas_primera_respuesta": 0.0,
        "promedio_horas_resolucion": 0.0,
        "casos_vencidos_sla": 0,
        "casos_por_usuario_asignado": [],
        "casos_por_estado": [],
        "casos_por_prioridad": [],
        "backlog_sin_asignar": 0,
    }
    try:
        filas = crud_postventa.listar_clientes_resumen_postventa(db, busqueda=q, limit=100)
    except Exception as exc:  # pragma: no cover
        logger.exception("Postventa hub: error listando clientes resumen")
        msg = msg or public_error_message(exc, default="Hub cargado con datos parciales.")
        sev = "warning"
    try:
        stats = crud_postventa.hub_dashboard_stats(db)
    except Exception as exc:  # pragma: no cover
        logger.exception("Postventa hub: error calculando dashboard stats")
        msg = msg or public_error_message(exc, default="Hub cargado con estadísticas parciales.")
        sev = "warning"
    try:
        metricas = crud_postventa.metricas_postventa(db)
    except Exception as exc:  # pragma: no cover
        logger.exception("Postventa hub: error calculando métricas")
        msg = msg or public_error_message(exc, default="Hub cargado con métricas parciales.")
        sev = "warning"
    return templates.TemplateResponse(
        "postventa/hub.html",
        {
            "request": request,
            "q": q,
            "filas": filas,
            "stats": stats,
            "metricas": metricas,
            "msg": msg,
            "sev": sev,
            "active_menu": "postventa",
        },
    )


@router.get("/postventa/casos", response_class=HTMLResponse, name="postventa_casos_lista")
def postventa_casos_lista(
    request: Request,
    estado: str | None = Query(None),
    prioridad: str | None = Query(None),
    asignado_a_id: int | None = Query(None),
    cliente_id: int | None = Query(None),
    q: str | None = Query(None),
    vista: str | None = Query(None),
    msg: str | None = Query(None),
    sev: str = Query("info"),
    db: Session = Depends(get_db),
):
    if (redir := guard_operacion_consulta(request)) is not None:
        return redir
    actor = getattr(request.state, "auth_user", None) or {}
    uid = _actor_uid(request)
    if vista == "mis_casos" and uid:
        asignado_a_id = uid
    elif vista == "sin_asignar":
        asignado_a_id = 0
    elif vista == "urgentes":
        prioridad = "URGENTE"
    elif vista == "vencidos":
        estado = None
    elif vista == "resueltos":
        estado = "RESUELTO"
    casos = []
    metricas = {
        "casos_abiertos": 0,
        "casos_nuevos_7d": 0,
        "casos_nuevos_30d": 0,
        "casos_resueltos_30d": 0,
        "promedio_horas_primera_respuesta": 0.0,
        "promedio_horas_resolucion": 0.0,
        "casos_vencidos_sla": 0,
        "casos_por_usuario_asignado": [],
        "casos_por_estado": [],
        "casos_por_prioridad": [],
        "backlog_sin_asignar": 0,
    }
    usuarios = []
    try:
        casos = crud_postventa.listar_casos(
            db,
            estado=estado,
            prioridad=prioridad,
            asignado_a_id=asignado_a_id,
            cliente_id=cliente_id,
            q=q,
        )
        if vista == "vencidos":
            casos = [c for c in casos if (getattr(c, "sla_estado", "OK") == "VENCIDO")]
    except Exception as exc:  # pragma: no cover
        logger.exception("Postventa casos: error listando bandeja")
        msg = msg or public_error_message(exc, default="Bandeja cargada con datos parciales.")
        sev = "warning"
    try:
        metricas = crud_postventa.metricas_postventa(db)
    except Exception as exc:  # pragma: no cover
        logger.exception("Postventa casos: error calculando métricas")
        msg = msg or public_error_message(exc, default="Métricas no disponibles temporalmente.")
        sev = "warning"
    try:
        usuarios = crud_usuarios.listar_usuarios(db, limite=200)
    except Exception as exc:  # pragma: no cover
        logger.exception("Postventa casos: error listando usuarios")
        msg = msg or public_error_message(exc, default="No se pudo cargar listado de usuarios.")
        sev = "warning"
    return templates.TemplateResponse(
        "postventa/casos_lista.html",
        {
            "request": request,
            "casos": casos,
            "metricas": metricas,
            "estado": estado,
            "prioridad": prioridad,
            "asignado_a_id": asignado_a_id,
            "cliente_id": cliente_id,
            "q": q,
            "vista": vista,
            "usuarios": usuarios,
            "auth_user": actor,
            "msg": msg,
            "sev": sev,
            "active_menu": "postventa",
        },
    )


@router.get("/postventa/casos/nuevo", response_class=HTMLResponse, name="postventa_caso_nuevo")
def postventa_caso_nuevo_form(
    request: Request,
    cliente_id: int | None = Query(None),
    titulo: str | None = Query(None),
    descripcion: str | None = Query(None),
    categoria: str | None = Query(None),
    prioridad: str | None = Query(None),
    origen: str | None = Query(None),
    msg: str | None = Query(None),
    sev: str = Query("info"),
    db: Session = Depends(get_db),
):
    if (redir := guard_operacion_consulta(request)) is not None:
        return redir
    clientes, _ = crud_cliente.listar_clientes(db, skip=0, limit=150)
    return templates.TemplateResponse(
        "postventa/caso_form.html",
        {
            "request": request,
            "clientes": clientes,
            "cliente_id": cliente_id,
            "titulo": titulo or "",
            "descripcion": descripcion or "",
            "categoria": categoria or "CONSULTA",
            "prioridad": prioridad or "MEDIA",
            "origen": origen or "INTERNO",
            "msg": msg,
            "sev": sev,
            "active_menu": "postventa",
        },
    )


@router.post("/postventa/casos/nuevo", name="postventa_caso_nuevo_post")
def postventa_caso_nuevo_post(
    request: Request,
    cliente_id: int = Form(...),
    titulo: str = Form(...),
    descripcion: str = Form(...),
    categoria: str = Form("CONSULTA"),
    prioridad: str = Form("MEDIA"),
    origen: str = Form("INTERNO"),
    db: Session = Depends(get_db),
):
    if (redir := guard_operacion_mutacion(request)) is not None:
        return redir
    if not cliente_id:
        return _redirect(
            request,
            "postventa_caso_nuevo",
            msg="Debe seleccionar un cliente.",
            sev="warning",
            query_params={
                "titulo": titulo,
                "descripcion": descripcion,
                "categoria": categoria,
                "prioridad": prioridad,
                "origen": origen,
            },
        )
    cliente = crud_cliente.get_cliente(db, cliente_id)
    if not cliente:
        return _redirect(
            request,
            "postventa_caso_nuevo",
            msg="Debe seleccionar un cliente.",
            sev="warning",
            query_params={
                "titulo": titulo,
                "descripcion": descripcion,
                "categoria": categoria,
                "prioridad": prioridad,
                "origen": origen,
            },
        )
    try:
        caso = crud_postventa.crear_caso(
            db,
            cliente_id=cliente_id,
            titulo=titulo,
            descripcion=descripcion,
            categoria=categoria,
            prioridad=prioridad,
            origen=origen,
            creado_por_id=_actor_uid(request),
        )
    except Exception as exc:
        logger.exception("Crear caso postventa cliente_id=%s", cliente_id)
        return _redirect(
            request,
            "postventa_caso_nuevo",
            msg="No se pudo crear el caso. Verifique que la migración Postventa CRM esté aplicada.",
            sev="danger",
            query_params={
                "cliente_id": cliente_id,
                "titulo": titulo,
                "descripcion": descripcion,
                "categoria": categoria,
                "prioridad": prioridad,
                "origen": origen,
            },
        )
    return _redirect_caso(request, caso.id, msg="Caso creado correctamente.", sev="success")


@router.get("/postventa/casos/{caso_id}", response_class=HTMLResponse, name="postventa_caso_detalle")
def postventa_caso_detalle(
    request: Request,
    caso_id: int,
    msg: str | None = Query(None),
    sev: str = Query("info"),
    db: Session = Depends(get_db),
):
    if (redir := guard_operacion_consulta(request)) is not None:
        return redir
    caso = crud_postventa.get_caso(db, caso_id)
    if not caso:
        raise HTTPException(status_code=404, detail="Caso no encontrado")
    cliente = crud_cliente.get_cliente(db, caso.cliente_id)
    eventos = crud_postventa.listar_eventos_caso(db, caso_id)
    usuarios = crud_usuarios.listar_usuarios(db, limite=200)
    return templates.TemplateResponse(
        "postventa/caso_detalle.html",
        {
            "request": request,
            "caso": caso,
            "cliente": cliente,
            "eventos": eventos,
            "usuarios": usuarios,
            "estados": list(crud_postventa.ESTADOS_CASO_ORDEN),
            "msg": msg,
            "sev": sev,
            "active_menu": "postventa",
        },
    )


@router.post("/postventa/casos/{caso_id}/comentario", name="postventa_caso_comentario")
def postventa_caso_comentario(
    request: Request,
    caso_id: int,
    contenido: str = Form(...),
    visibilidad: str = Form("INTERNA"),
    db: Session = Depends(get_db),
):
    if (redir := guard_operacion_mutacion(request)) is not None:
        return redir
    caso = crud_postventa.get_caso(db, caso_id)
    if not caso:
        raise HTTPException(status_code=404)
    crud_postventa.agregar_evento_caso(
        db,
        caso_id=caso.id,
        cliente_id=caso.cliente_id,
        usuario_id=_actor_uid(request),
        tipo="COMENTARIO" if (visibilidad or "").upper() == "PUBLICA" else "NOTA_INTERNA",
        visibilidad=visibilidad,
        contenido=contenido,
    )
    db.commit()
    return _redirect_caso(request, caso_id, msg="Comentario agregado.", sev="success")


@router.post("/postventa/casos/{caso_id}/asignar", name="postventa_caso_asignar")
def postventa_caso_asignar(
    request: Request,
    caso_id: int,
    usuario_id: int | None = Form(None),
    db: Session = Depends(get_db),
):
    if (redir := guard_operacion_mutacion(request)) is not None:
        return redir
    updated = crud_postventa.asignar_caso(
        db,
        caso_id=caso_id,
        usuario_id=usuario_id,
        actor_id=_actor_uid(request),
    )
    if not updated:
        raise HTTPException(status_code=404)
    return _redirect_caso(request, caso_id, msg="Caso asignado.", sev="success")


@router.post("/postventa/casos/{caso_id}/estado", name="postventa_caso_estado")
def postventa_caso_estado(
    request: Request,
    caso_id: int,
    estado: str = Form(...),
    comentario: str | None = Form(None),
    db: Session = Depends(get_db),
):
    if (redir := guard_operacion_mutacion(request)) is not None:
        return redir
    updated = crud_postventa.cambiar_estado_caso(
        db,
        caso_id=caso_id,
        estado=estado,
        actor_id=_actor_uid(request),
        comentario=comentario,
    )
    if not updated:
        return _redirect_caso(request, caso_id, msg="Estado no válido.", sev="warning")
    return _redirect_caso(request, caso_id, msg="Estado actualizado.", sev="success")


@router.post("/postventa/casos/{caso_id}/email", name="postventa_caso_email")
def postventa_caso_email(
    request: Request,
    caso_id: int,
    to: str = Form(...),
    subject: str = Form(...),
    body: str = Form(...),
    db: Session = Depends(get_db),
):
    if (redir := guard_operacion_mutacion(request)) is not None:
        return redir
    try:
        crud_postventa.enviar_email_caso(
            db,
            caso_id=caso_id,
            to=to,
            subject=subject,
            body=body,
            actor=getattr(request.state, "auth_user", None) or {},
        )
    except Exception as exc:
        logger.exception("Enviar email caso_id=%s", caso_id)
        return _redirect_caso(
            request,
            caso_id,
            msg=public_error_message(exc, default="No se pudo enviar el correo del caso."),
            sev="danger",
        )
    return _redirect_caso(request, caso_id, msg="Correo enviado y trazado en muro.", sev="success")


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
