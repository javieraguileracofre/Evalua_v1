# routes/ui/fondos_rendir.py
# -*- coding: utf-8 -*-
"""Fondos por rendir: anticipos a trabajadores, gastos y aprobación."""
from __future__ import annotations

import json
import logging
from datetime import datetime
from decimal import Decimal, InvalidOperation
from typing import Any, Optional
from urllib.parse import urlencode

from fastapi import APIRouter, Depends, Query, Request, status
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from core.paths import TEMPLATES_DIR
from core.public_errors import public_error_message
from core.rbac import guard_finanzas_consulta, guard_finanzas_mutacion
from crud.auth import usuarios as crud_auth
from crud import fondos_rendir as crud_fr
from db.session import get_db
from services.fondos_rendir import (
    aprobar_rendicion_y_contabilizar,
    crear_anticipo_y_contabilizar,
    diagnosticar_setup_contable,
)

router = APIRouter(prefix="/fondos-rendir", tags=["Fondos por rendir"])
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


def _parse_decimal(v: str | None) -> Decimal | None:
    if v is None or str(v).strip() == "":
        return None
    try:
        return Decimal(str(v).strip().replace(",", "."))
    except (InvalidOperation, ValueError):
        return None


def _parse_int(v: str | None) -> int | None:
    if v is None or str(v).strip() == "":
        return None
    try:
        return int(str(v).strip(), 10)
    except ValueError:
        return None


def _parse_optional_user_id(v: Any) -> int | None:
    n = _parse_int(str(v) if v is not None else None)
    return n if n and n > 0 else None


def _form_to_dict(form: Any) -> dict[str, Any]:
    out: dict[str, Any] = {}
    try:
        keys = list(form.keys())
    except Exception:
        keys = [k for k in form]
    for k in keys:
        out[str(k)] = form.get(k)
    return out


def _lineas_gasto_json(fondo: Any) -> str:
    rows = []
    for L in sorted(fondo.lineas_gasto, key=lambda x: x.linea):
        rows.append(
            {
                "fecha_gasto": L.fecha_gasto.strftime("%Y-%m-%dT%H:%M"),
                "rubro": L.rubro,
                "descripcion": L.descripcion or "",
                "monto": str(L.monto),
                "nro_documento": L.nro_documento or "",
            }
        )
    return json.dumps(rows, ensure_ascii=False)


# --- Hub / panel ---


@router.get("", response_class=HTMLResponse, name="fondos_rendir_hub")
def fondos_rendir_hub(
    request: Request,
    db: Session = Depends(get_db),
):
    if (redir := guard_finanzas_consulta(request)) is not None:
        return redir
    stats: dict[str, Any] = {
        "n_abiertos": 0,
        "n_pendiente_aprobacion": 0,
        "monto_abiertos": Decimal("0.00"),
        "monto_pendiente_aprobacion": Decimal("0.00"),
        "alertas_rendicion": [],
        "n_total": 0,
        "monto_total": Decimal("0.00"),
        "abiertos_mas_3_dias": 0,
        "abiertos_mas_7_dias": 0,
        "abiertos_mas_15_dias": 0,
        "monto_abierto_por_chofer": [],
        "monto_pendiente_aprobar": Decimal("0.00"),
        "total_rendido": Decimal("0.00"),
        "total_anticipado": Decimal("0.00"),
        "chart": {"estado_labels": [], "estado_montos": [], "estado_counts": [], "mes_labels": [], "mes_montos": [], "mes_n": []},
    }
    conc: dict[str, Any] = {
        "fondos_vencidos": [],
        "fondos_sin_viaje": [],
        "gastos_combustible_sin_viaje": [],
        "viajes_sin_rendicion": [],
        "rendiciones_inconsistentes": [],
        "fondos_chofer_vehiculo_distinto": [],
    }
    mant: dict[str, Any] = {
        "mantenciones_vencidas": [],
        "mantenciones_proximas": [],
        "documentos_por_vencer": [],
    }
    fondos: list[Any] = []
    msg_q = request.query_params.get("msg")
    sev_q = request.query_params.get("sev", "info")
    try:
        stats = crud_fr.dashboard_stats(db)
    except Exception as exc:  # pragma: no cover
        logger.exception("Fondos rendir hub: error en dashboard_stats")
        if not msg_q:
            msg_q = public_error_message(
                exc,
                default=(
                    "Hub cargado con datos parciales. Verifique la migración de transporte/fondos "
                    "(112/113) y la consistencia de esquema."
                ),
            )
            sev_q = "warning"
    try:
        conc = crud_fr.dashboard_conciliacion_transporte(db)
    except Exception as exc:  # pragma: no cover
        logger.exception("Fondos rendir hub: error en dashboard_conciliacion_transporte")
        if not msg_q:
            msg_q = public_error_message(exc, default="Conciliación transporte no disponible temporalmente.")
            sev_q = "warning"
    try:
        mant = crud_fr.alertas_mantencion(db)
    except Exception as exc:  # pragma: no cover
        logger.exception("Fondos rendir hub: error en alertas_mantencion")
        if not msg_q:
            msg_q = public_error_message(exc, default="Alertas de mantención no disponibles temporalmente.")
            sev_q = "warning"
    try:
        fondos = crud_fr.listar_fondos(db, limite=50)
    except Exception as exc:  # pragma: no cover
        logger.exception("Fondos rendir hub: error en listar_fondos")
        if not msg_q:
            msg_q = public_error_message(exc, default="Listado de anticipos no disponible temporalmente.")
            sev_q = "warning"
    setup_contable: dict[str, Any] = {"ok": False, "msg": "", "cuentas": {}}
    try:
        cuentas = diagnosticar_setup_contable(db)
        setup_contable = {
            "ok": True,
            "msg": "Configuración contable validada.",
            "cuentas": cuentas,
        }
    except ValueError as e:
        setup_contable = {
            "ok": False,
            "msg": public_error_message(e),
            "cuentas": {},
        }
    except Exception as exc:  # pragma: no cover
        logger.exception("Fondos rendir hub: error en diagnosticar_setup_contable")
        setup_contable = {
            "ok": False,
            "msg": "Diagnóstico contable no disponible temporalmente.",
            "cuentas": {},
        }
        if not msg_q:
            msg_q = public_error_message(
                exc,
                default=(
                    "Hub cargado con datos parciales. Verifique la migración de transporte/fondos "
                    "(112/113) y la consistencia de esquema."
                ),
            )
            sev_q = "warning"
    return templates.TemplateResponse(
        "fondos_rendir/hub.html",
        {
            "request": request,
            "active_menu": "fondos_rendir",
            "stats": stats,
            "conc": conc,
            "mant": mant,
            "fondos": fondos,
            "setup_contable": setup_contable,
            "msg": msg_q,
            "sev": sev_q,
        },
    )


# --- Empleados ---


@router.get("/empleados", response_class=HTMLResponse, name="fondos_rendir_empleados")
def fondos_rendir_empleados(
    request: Request,
    db: Session = Depends(get_db),
    todos: Optional[str] = Query(None),
):
    if (redir := guard_finanzas_consulta(request)) is not None:
        return redir
    solo_activos = todos != "1"
    empleados = crud_fr.listar_empleados(db, solo_activos=solo_activos)
    return templates.TemplateResponse(
        "fondos_rendir/empleados_lista.html",
        {
            "request": request,
            "active_menu": "fondos_rendir",
            "empleados": empleados,
            "solo_activos": solo_activos,
        },
    )


@router.get("/empleados/nuevo", response_class=HTMLResponse, name="fondos_rendir_empleado_nuevo")
def fondos_rendir_empleado_nuevo(request: Request, db: Session = Depends(get_db)):
    if (redir := guard_finanzas_mutacion(request)) is not None:
        return redir
    usuarios_portal = crud_auth.listar_usuarios(db)
    return templates.TemplateResponse(
        "fondos_rendir/empleado_form.html",
        {
            "request": request,
            "active_menu": "fondos_rendir",
            "empleado": None,
            "modo": "nuevo",
            "usuarios_portal": usuarios_portal,
        },
    )


@router.post("/empleados/nuevo", name="fondos_rendir_empleado_crear")
async def fondos_rendir_empleado_crear(
    request: Request,
    db: Session = Depends(get_db),
):
    if (redir := guard_finanzas_mutacion(request)) is not None:
        return redir
    fd = _form_to_dict(await request.form())
    try:
        crud_fr.crear_empleado(
            db,
            rut=str(fd.get("rut") or ""),
            nombre_completo=str(fd.get("nombre_completo") or ""),
            cargo=str(fd.get("cargo") or "") or None,
            email=str(fd.get("email") or "") or None,
            telefono=str(fd.get("telefono") or "") or None,
            auth_usuario_id=_parse_optional_user_id(fd.get("auth_usuario_id")),
        )
        db.commit()
    except ValueError as e:
        db.rollback()
        return _redirect(request, "fondos_rendir_empleado_nuevo", msg=public_error_message(e), sev="danger")
    except SQLAlchemyError:
        db.rollback()
        logger.exception("Empleado crear")
        return _redirect(
            request,
            "fondos_rendir_empleado_nuevo",
            msg="No se pudo guardar el empleado.",
            sev="danger",
        )
    return _redirect(
        request,
        "fondos_rendir_empleados",
        msg="Empleado registrado correctamente.",
        sev="success",
    )


@router.get("/empleados/{empleado_id}/editar", response_class=HTMLResponse, name="fondos_rendir_empleado_editar")
def fondos_rendir_empleado_editar(
    request: Request,
    empleado_id: int,
    db: Session = Depends(get_db),
):
    if (redir := guard_finanzas_mutacion(request)) is not None:
        return redir
    e = crud_fr.obtener_empleado(db, empleado_id)
    if not e:
        return _redirect(request, "fondos_rendir_empleados", msg="Empleado no encontrado.", sev="warning")
    usuarios_portal = crud_auth.listar_usuarios(db)
    return templates.TemplateResponse(
        "fondos_rendir/empleado_form.html",
        {
            "request": request,
            "active_menu": "fondos_rendir",
            "empleado": e,
            "modo": "editar",
            "usuarios_portal": usuarios_portal,
        },
    )


@router.post("/empleados/{empleado_id}/editar", name="fondos_rendir_empleado_actualizar")
async def fondos_rendir_empleado_actualizar(
    request: Request,
    empleado_id: int,
    db: Session = Depends(get_db),
):
    if (redir := guard_finanzas_mutacion(request)) is not None:
        return redir
    fd = _form_to_dict(await request.form())
    activo = str(fd.get("activo") or "").lower() in ("1", "on", "true", "si", "sí")
    try:
        crud_fr.actualizar_empleado(
            db,
            empleado_id,
            rut=str(fd.get("rut") or ""),
            nombre_completo=str(fd.get("nombre_completo") or ""),
            cargo=str(fd.get("cargo") or "") or None,
            email=str(fd.get("email") or "") or None,
            telefono=str(fd.get("telefono") or "") or None,
            activo=activo,
            auth_usuario_id=_parse_optional_user_id(fd.get("auth_usuario_id")),
        )
        db.commit()
    except ValueError as e:
        db.rollback()
        return _redirect(
            request,
            "fondos_rendir_empleado_editar",
            empleado_id=empleado_id,
            msg=public_error_message(e),
            sev="danger",
        )
    except SQLAlchemyError:
        db.rollback()
        return _redirect(
            request,
            "fondos_rendir_empleado_editar",
            empleado_id=empleado_id,
            msg="No se pudo actualizar el empleado.",
            sev="danger",
        )
    return _redirect(
        request,
        "fondos_rendir_empleados",
        msg="Datos del empleado actualizados.",
        sev="success",
    )


# --- Vehículos flota ---


@router.get("/vehiculos", response_class=HTMLResponse, name="fondos_rendir_vehiculos")
def fondos_rendir_vehiculos(
    request: Request,
    db: Session = Depends(get_db),
    todos: Optional[str] = Query(None),
):
    if (redir := guard_finanzas_consulta(request)) is not None:
        return redir
    solo_activos = todos != "1"
    vehiculos = crud_fr.listar_vehiculos_transporte(db, solo_activos=solo_activos)
    return templates.TemplateResponse(
        "fondos_rendir/vehiculos_lista.html",
        {
            "request": request,
            "active_menu": "fondos_rendir",
            "vehiculos": vehiculos,
            "solo_activos": solo_activos,
        },
    )


@router.get("/vehiculos/nuevo", response_class=HTMLResponse, name="fondos_rendir_vehiculo_nuevo")
def fondos_rendir_vehiculo_nuevo(request: Request):
    if (redir := guard_finanzas_mutacion(request)) is not None:
        return redir
    return templates.TemplateResponse(
        "fondos_rendir/vehiculo_form.html",
        {
            "request": request,
            "active_menu": "fondos_rendir",
            "vehiculo": None,
            "modo": "nuevo",
        },
    )


@router.post("/vehiculos/nuevo", name="fondos_rendir_vehiculo_crear")
async def fondos_rendir_vehiculo_crear(
    request: Request,
    db: Session = Depends(get_db),
):
    if (redir := guard_finanzas_mutacion(request)) is not None:
        return redir
    fd = _form_to_dict(await request.form())
    try:
        crud_fr.crear_vehiculo_transporte(
            db,
            patente=str(fd.get("patente") or ""),
            marca=str(fd.get("marca") or ""),
            modelo=str(fd.get("modelo") or ""),
            anio=_parse_int(fd.get("anio")),
            observaciones=str(fd.get("observaciones") or "") or None,
            consumo_referencial_l100km=_parse_decimal(fd.get("consumo_referencial_l100km")),
            tipo_vehiculo=str(fd.get("tipo_vehiculo") or "") or None,
            capacidad_carga=_parse_decimal(fd.get("capacidad_carga")),
            odometro_actual=_parse_int(fd.get("odometro_actual")),
            estado_operativo=str(fd.get("estado_operativo") or "DISPONIBLE"),
            fecha_revision_tecnica=crud_fr.parse_fecha_formulario_date(str(fd.get("fecha_revision_tecnica") or "") or None),
            fecha_permiso_circulacion=crud_fr.parse_fecha_formulario_date(str(fd.get("fecha_permiso_circulacion") or "") or None),
            fecha_seguro=crud_fr.parse_fecha_formulario_date(str(fd.get("fecha_seguro") or "") or None),
            fecha_proxima_mantencion=crud_fr.parse_fecha_formulario_date(str(fd.get("fecha_proxima_mantencion") or "") or None),
            km_proxima_mantencion=_parse_int(fd.get("km_proxima_mantencion")),
        )
        db.commit()
    except ValueError as e:
        db.rollback()
        return _redirect(request, "fondos_rendir_vehiculo_nuevo", msg=public_error_message(e), sev="danger")
    except SQLAlchemyError:
        db.rollback()
        return _redirect(
            request,
            "fondos_rendir_vehiculo_nuevo",
            msg="No se pudo guardar el vehículo.",
            sev="danger",
        )
    return _redirect(
        request,
        "fondos_rendir_vehiculos",
        msg="Vehículo de flota registrado.",
        sev="success",
    )


@router.get("/vehiculos/{vid}/editar", response_class=HTMLResponse, name="fondos_rendir_vehiculo_editar")
def fondos_rendir_vehiculo_editar(
    request: Request,
    vid: int,
    db: Session = Depends(get_db),
):
    if (redir := guard_finanzas_mutacion(request)) is not None:
        return redir
    v = crud_fr.obtener_vehiculo(db, vid)
    if not v:
        return _redirect(request, "fondos_rendir_vehiculos", msg="Vehículo no encontrado.", sev="warning")
    return templates.TemplateResponse(
        "fondos_rendir/vehiculo_form.html",
        {
            "request": request,
            "active_menu": "fondos_rendir",
            "vehiculo": v,
            "modo": "editar",
        },
    )


@router.post("/vehiculos/{vid}/editar", name="fondos_rendir_vehiculo_actualizar")
async def fondos_rendir_vehiculo_actualizar(
    request: Request,
    vid: int,
    db: Session = Depends(get_db),
):
    if (redir := guard_finanzas_mutacion(request)) is not None:
        return redir
    fd = _form_to_dict(await request.form())
    activo = str(fd.get("activo") or "").lower() in ("1", "on", "true", "si", "sí")
    try:
        crud_fr.actualizar_vehiculo_transporte(
            db,
            vid,
            patente=str(fd.get("patente") or ""),
            marca=str(fd.get("marca") or ""),
            modelo=str(fd.get("modelo") or ""),
            anio=_parse_int(fd.get("anio")),
            observaciones=str(fd.get("observaciones") or "") or None,
            activo=activo,
            consumo_referencial_l100km=_parse_decimal(fd.get("consumo_referencial_l100km")),
            tipo_vehiculo=str(fd.get("tipo_vehiculo") or "") or None,
            capacidad_carga=_parse_decimal(fd.get("capacidad_carga")),
            odometro_actual=_parse_int(fd.get("odometro_actual")),
            estado_operativo=str(fd.get("estado_operativo") or "DISPONIBLE"),
            fecha_revision_tecnica=crud_fr.parse_fecha_formulario_date(str(fd.get("fecha_revision_tecnica") or "") or None),
            fecha_permiso_circulacion=crud_fr.parse_fecha_formulario_date(str(fd.get("fecha_permiso_circulacion") or "") or None),
            fecha_seguro=crud_fr.parse_fecha_formulario_date(str(fd.get("fecha_seguro") or "") or None),
            fecha_proxima_mantencion=crud_fr.parse_fecha_formulario_date(str(fd.get("fecha_proxima_mantencion") or "") or None),
            km_proxima_mantencion=_parse_int(fd.get("km_proxima_mantencion")),
        )
        db.commit()
    except ValueError as e:
        db.rollback()
        return _redirect(request, "fondos_rendir_vehiculo_editar", vid=vid, msg=public_error_message(e), sev="danger")
    except SQLAlchemyError:
        db.rollback()
        return _redirect(
            request,
            "fondos_rendir_vehiculo_editar",
            vid=vid,
            msg="No se pudo actualizar el vehículo.",
            sev="danger",
        )
    return _redirect(
        request,
        "fondos_rendir_vehiculos",
        msg="Vehículo actualizado.",
        sev="success",
    )


# --- Anticipos ---


@router.get("/anticipos", response_class=HTMLResponse, name="fondos_rendir_anticipos")
def fondos_rendir_anticipos(request: Request, db: Session = Depends(get_db)):
    if (redir := guard_finanzas_consulta(request)) is not None:
        return redir
    fondos = crud_fr.listar_fondos(db, limite=500)
    return templates.TemplateResponse(
        "fondos_rendir/fondos_lista.html",
        {
            "request": request,
            "active_menu": "fondos_rendir",
            "fondos": fondos,
        },
    )


@router.get("/anticipos/nuevo", response_class=HTMLResponse, name="fondos_rendir_fondo_nuevo")
def fondos_rendir_fondo_nuevo(request: Request, db: Session = Depends(get_db)):
    if (redir := guard_finanzas_mutacion(request)) is not None:
        return redir
    empleados = crud_fr.listar_empleados(db, solo_activos=True)
    vehiculos = crud_fr.listar_vehiculos_transporte(db, solo_activos=True)
    fecha_default = datetime.now().strftime("%Y-%m-%dT%H:%M")
    setup_msg: str | None = None
    setup_sev = "info"
    try:
        diagnosticar_setup_contable(db)
    except ValueError as e:
        setup_msg = public_error_message(e)
        setup_sev = "warning"
    return templates.TemplateResponse(
        "fondos_rendir/fondo_form.html",
        {
            "request": request,
            "active_menu": "fondos_rendir",
            "empleados": empleados,
            "vehiculos": vehiculos,
            "fecha_default": fecha_default,
            "msg": setup_msg,
            "sev": setup_sev,
        },
    )


@router.post("/anticipos/nuevo", name="fondos_rendir_fondo_crear")
async def fondos_rendir_fondo_crear(
    request: Request,
    db: Session = Depends(get_db),
):
    if (redir := guard_finanzas_mutacion(request)) is not None:
        return redir
    fd = _form_to_dict(await request.form())
    eid = _parse_int(fd.get("empleado_id"))
    vid = _parse_int(fd.get("vehiculo_transporte_id"))
    monto = _parse_decimal(fd.get("monto_anticipo"))
    fr_dt = crud_fr.parse_fecha_formulario(str(fd.get("fecha_entrega") or ""))
    if fr_dt is None:
        fr_dt = datetime.utcnow()
    try:
        if eid is None:
            raise ValueError("Seleccione un trabajador.")
        if monto is None or monto <= 0:
            raise ValueError("Indique un monto de anticipo válido.")
        f = crear_anticipo_y_contabilizar(
            db,
            empleado_id=eid,
            vehiculo_transporte_id=vid,
            monto_anticipo=monto,
            fecha_entrega=fr_dt,
            observaciones=str(fd.get("observaciones") or "") or None,
        )
        db.commit()
        db.refresh(f)
    except ValueError as e:
        db.rollback()
        return _redirect(request, "fondos_rendir_fondo_nuevo", msg=public_error_message(e), sev="danger")
    except SQLAlchemyError:
        db.rollback()
        logger.exception("Fondo crear")
        return _redirect(
            request,
            "fondos_rendir_fondo_nuevo",
            msg="No se pudo registrar el anticipo.",
            sev="danger",
        )
    return _redirect(
        request,
        "fondos_rendir_fondo_detalle",
        fondo_id=f.id,
        msg=f"Anticipo {f.folio} creado (asiento de entrega contable registrado). Registre los gastos y envíe la rendición.",
        sev="success",
    )


@router.get(
    "/diagnostico-contable",
    response_class=HTMLResponse,
    name="fondos_rendir_diagnostico_contable",
)
def fondos_rendir_diagnostico_contable(
    request: Request,
    db: Session = Depends(get_db),
):
    if (redir := guard_finanzas_consulta(request)) is not None:
        return redir
    try:
        setup = diagnosticar_setup_contable(db)
        msg = (
            "Configuración contable OK. "
            f"Anticipo: {setup['anticipo']['codigo']} | "
            f"Caja: {setup['caja']['codigo']} | "
            f"Gasto: {setup['gasto']['codigo']}."
        )
        return _redirect(request, "fondos_rendir_hub", msg=msg, sev="success")
    except ValueError as e:
        return _redirect(
            request,
            "fondos_rendir_hub",
            msg=public_error_message(e),
            sev="danger",
        )


@router.get("/anticipos/{fondo_id}", response_class=HTMLResponse, name="fondos_rendir_fondo_detalle")
def fondos_rendir_fondo_detalle(
    request: Request,
    fondo_id: int,
    db: Session = Depends(get_db),
    msg: Optional[str] = Query(None),
    sev: str = Query("info"),
):
    if (redir := guard_finanzas_consulta(request)) is not None:
        return redir
    f = crud_fr.obtener_fondo(db, fondo_id)
    if not f:
        return _redirect(request, "fondos_rendir_anticipos", msg="Anticipo no encontrado.", sev="warning")
    total_g = crud_fr.total_gastos_orm(list(f.lineas_gasto))
    saldo = (f.monto_anticipo - total_g).quantize(Decimal("0.01"))
    gastos_json = _lineas_gasto_json(f) if f.lineas_gasto else "[]"
    if not f.lineas_gasto:
        gastos_json = json.dumps(
            [
                {
                    "fecha_gasto": datetime.now().strftime("%Y-%m-%dT%H:%M"),
                    "rubro": "Combustible",
                    "descripcion": "",
                    "monto": "0",
                    "nro_documento": "",
                }
            ],
            ensure_ascii=False,
        )
    return templates.TemplateResponse(
        "fondos_rendir/fondo_detalle.html",
        {
            "request": request,
            "active_menu": "fondos_rendir",
            "fondo": f,
            "total_gastos": total_g,
            "saldo": saldo,
            "gastos_json": gastos_json,
            "rubros": crud_fr.RUBROS_GASTO,
            "msg": msg,
            "sev": sev,
        },
    )


@router.get(
    "/anticipos/{fondo_id}/imprimir",
    response_class=HTMLResponse,
    name="fondos_rendir_fondo_imprimir",
)
def fondos_rendir_fondo_imprimir(
    request: Request,
    fondo_id: int,
    db: Session = Depends(get_db),
):
    if (redir := guard_finanzas_consulta(request)) is not None:
        return redir
    f = crud_fr.obtener_fondo(db, fondo_id)
    if not f:
        return _redirect(request, "fondos_rendir_anticipos", msg="Anticipo no encontrado.", sev="warning")
    total_g = crud_fr.total_gastos_orm(list(f.lineas_gasto))
    saldo = (f.monto_anticipo - total_g).quantize(Decimal("0.01"))
    return templates.TemplateResponse(
        "fondos_rendir/fondo_detalle_print.html",
        {
            "request": request,
            "fondo": f,
            "total_gastos": total_g,
            "saldo": saldo,
        },
    )


@router.post("/anticipos/{fondo_id}/gastos", name="fondos_rendir_fondo_guardar_gastos")
async def fondos_rendir_fondo_guardar_gastos(
    request: Request,
    fondo_id: int,
    db: Session = Depends(get_db),
):
    if (redir := guard_finanzas_mutacion(request)) is not None:
        return redir
    form = await request.form()
    fd = _form_to_dict(form)
    raw = str(fd.get("gastos_json") or "")
    try:
        rows = crud_fr.parse_gastos_json(raw)
        f = crud_fr.obtener_fondo(db, fondo_id)
        if not f:
            raise ValueError("Anticipo no encontrado.")
        if f.estado != "ABIERTO":
            raise ValueError("Solo puede editar gastos con el anticipo en estado Abierto.")
        crud_fr.sync_gastos_lineas(db, fondo_id, rows)
        db.commit()
    except ValueError as e:
        db.rollback()
        return _redirect(
            request,
            "fondos_rendir_fondo_detalle",
            fondo_id=fondo_id,
            msg=public_error_message(e),
            sev="danger",
        )
    except SQLAlchemyError:
        db.rollback()
        return _redirect(
            request,
            "fondos_rendir_fondo_detalle",
            fondo_id=fondo_id,
            msg="No se pudieron guardar los gastos.",
            sev="danger",
        )
    return _redirect(
        request,
        "fondos_rendir_fondo_detalle",
        fondo_id=fondo_id,
        msg="Gastos guardados.",
        sev="success",
    )


@router.post("/anticipos/{fondo_id}/enviar", name="fondos_rendir_fondo_enviar")
def fondos_rendir_fondo_enviar(
    request: Request,
    fondo_id: int,
    db: Session = Depends(get_db),
):
    if (redir := guard_finanzas_mutacion(request)) is not None:
        return redir
    try:
        crud_fr.enviar_rendicion(db, fondo_id)
        db.commit()
    except ValueError as e:
        db.rollback()
        return _redirect(
            request,
            "fondos_rendir_fondo_detalle",
            fondo_id=fondo_id,
            msg=public_error_message(e),
            sev="danger",
        )
    except SQLAlchemyError:
        db.rollback()
        return _redirect(
            request,
            "fondos_rendir_fondo_detalle",
            fondo_id=fondo_id,
            msg="No se pudo enviar la rendición.",
            sev="danger",
        )
    return _redirect(
        request,
        "fondos_rendir_fondo_detalle",
        fondo_id=fondo_id,
        msg="Rendición enviada. Queda pendiente de aprobación.",
        sev="success",
    )


@router.post("/anticipos/{fondo_id}/aprobar", name="fondos_rendir_fondo_aprobar")
def fondos_rendir_fondo_aprobar(
    request: Request,
    fondo_id: int,
    db: Session = Depends(get_db),
):
    if (redir := guard_finanzas_mutacion(request)) is not None:
        return redir
    try:
        aprobar_rendicion_y_contabilizar(db, fondo_id=fondo_id)
        db.commit()
    except ValueError as e:
        db.rollback()
        return _redirect(
            request,
            "fondos_rendir_fondo_detalle",
            fondo_id=fondo_id,
            msg=public_error_message(e),
            sev="danger",
        )
    except SQLAlchemyError:
        db.rollback()
        logger.exception("Fondo aprobar + contabilidad")
        return _redirect(
            request,
            "fondos_rendir_fondo_detalle",
            fondo_id=fondo_id,
            msg="No se pudo aprobar o generar el asiento contable.",
            sev="danger",
        )
    return _redirect(
        request,
        "fondos_rendir_fondo_detalle",
        fondo_id=fondo_id,
        msg="Rendición aprobada y asiento de liquidación generado.",
        sev="success",
    )


@router.post("/anticipos/{fondo_id}/rechazar", name="fondos_rendir_fondo_rechazar")
async def fondos_rendir_fondo_rechazar(
    request: Request,
    fondo_id: int,
    db: Session = Depends(get_db),
):
    if (redir := guard_finanzas_mutacion(request)) is not None:
        return redir
    form = await request.form()
    motivo = str(form.get("motivo_rechazo") or "")
    try:
        crud_fr.rechazar_rendicion(db, fondo_id, motivo)
        db.commit()
    except ValueError as e:
        db.rollback()
        return _redirect(
            request,
            "fondos_rendir_fondo_detalle",
            fondo_id=fondo_id,
            msg=public_error_message(e),
            sev="danger",
        )
    except SQLAlchemyError:
        db.rollback()
        return _redirect(
            request,
            "fondos_rendir_fondo_detalle",
            fondo_id=fondo_id,
            msg="No se pudo registrar el rechazo.",
            sev="danger",
        )
    return _redirect(
        request,
        "fondos_rendir_fondo_detalle",
        fondo_id=fondo_id,
        msg="Rendición rechazada. Puede reabrir para corregir.",
        sev="warning",
    )


@router.post("/anticipos/{fondo_id}/eliminar", name="fondos_rendir_fondo_eliminar")
def fondos_rendir_fondo_eliminar(
    request: Request,
    fondo_id: int,
    db: Session = Depends(get_db),
):
    if (redir := guard_finanzas_mutacion(request)) is not None:
        return redir
    try:
        crud_fr.eliminar_fondo_rendir(db, fondo_id)
        db.commit()
    except ValueError as e:
        db.rollback()
        return _redirect(
            request,
            "fondos_rendir_fondo_detalle",
            fondo_id=fondo_id,
            msg=public_error_message(e),
            sev="danger",
        )
    except SQLAlchemyError:
        db.rollback()
        logger.exception("Eliminar fondo rendir %s", fondo_id)
        return _redirect(
            request,
            "fondos_rendir_fondo_detalle",
            fondo_id=fondo_id,
            msg="No se pudo eliminar el registro.",
            sev="danger",
        )
    return _redirect(
        request,
        "fondos_rendir_anticipos",
        msg="Anticipo eliminado correctamente.",
        sev="success",
    )


@router.post("/anticipos/{fondo_id}/reabrir", name="fondos_rendir_fondo_reabrir")
def fondos_rendir_fondo_reabrir(
    request: Request,
    fondo_id: int,
    db: Session = Depends(get_db),
):
    if (redir := guard_finanzas_mutacion(request)) is not None:
        return redir
    try:
        crud_fr.reabrir_tras_rechazo(db, fondo_id)
        db.commit()
    except ValueError as e:
        db.rollback()
        return _redirect(
            request,
            "fondos_rendir_fondo_detalle",
            fondo_id=fondo_id,
            msg=public_error_message(e),
            sev="danger",
        )
    except SQLAlchemyError:
        db.rollback()
        return _redirect(
            request,
            "fondos_rendir_fondo_detalle",
            fondo_id=fondo_id,
            msg="No se pudo reabrir.",
            sev="danger",
        )
    return _redirect(
        request,
        "fondos_rendir_fondo_detalle",
        fondo_id=fondo_id,
        msg="Anticipo reabierto. Ajuste los gastos y vuelva a enviar.",
        sev="success",
    )


@router.get("/mantenciones", response_class=HTMLResponse, name="fondos_rendir_mantenciones")
def fondos_rendir_mantenciones(
    request: Request,
    db: Session = Depends(get_db),
    vehiculo_id: Optional[int] = Query(None),
):
    if (redir := guard_finanzas_consulta(request)) is not None:
        return redir
    mantenciones: list[Any] = []
    vehiculos: list[Any] = []
    alertas: dict[str, Any] = {
        "mantenciones_vencidas": [],
        "mantenciones_proximas": [],
        "documentos_por_vencer": [],
    }
    msg_q = request.query_params.get("msg")
    sev_q = request.query_params.get("sev", "info")
    try:
        mantenciones = crud_fr.listar_mantenciones(db, vehiculo_id=vehiculo_id)
    except Exception as exc:  # pragma: no cover
        logger.exception("Fondos rendir mantenciones: error en listar_mantenciones")
        if not msg_q:
            msg_q = public_error_message(exc, default="Listado de mantenciones no disponible temporalmente.")
            sev_q = "warning"
    try:
        vehiculos = crud_fr.listar_vehiculos_transporte(db, solo_activos=False)
    except Exception as exc:  # pragma: no cover
        logger.exception("Fondos rendir mantenciones: error en listar_vehiculos_transporte")
        if not msg_q:
            msg_q = public_error_message(exc, default="Listado de vehículos no disponible temporalmente.")
            sev_q = "warning"
    try:
        alertas = crud_fr.alertas_mantencion(db)
    except Exception as exc:  # pragma: no cover
        logger.exception("Fondos rendir mantenciones: error en alertas_mantencion")
        if not msg_q:
            msg_q = public_error_message(exc, default="Alertas de mantención no disponibles temporalmente.")
            sev_q = "warning"
    return templates.TemplateResponse(
        "fondos_rendir/mantenciones_lista.html",
        {
            "request": request,
            "active_menu": "fondos_rendir",
            "mantenciones": mantenciones,
            "vehiculos": vehiculos,
            "vehiculo_id": vehiculo_id,
            "alertas": alertas,
            "msg": msg_q,
            "sev": sev_q,
        },
    )


@router.get("/mantenciones/nueva", response_class=HTMLResponse, name="fondos_rendir_mantencion_nueva")
def fondos_rendir_mantencion_nueva(request: Request, db: Session = Depends(get_db)):
    if (redir := guard_finanzas_mutacion(request)) is not None:
        return redir
    return templates.TemplateResponse(
        "fondos_rendir/mantencion_form.html",
        {
            "request": request,
            "active_menu": "fondos_rendir",
            "vehiculos": crud_fr.listar_vehiculos_transporte(db, solo_activos=True),
            "tipos": ["PREVENTIVA", "CORRECTIVA", "NEUMATICOS", "ACEITE", "OTRO"],
            "hoy": datetime.now().strftime("%Y-%m-%d"),
        },
    )


@router.post("/mantenciones/nueva", name="fondos_rendir_mantencion_crear")
async def fondos_rendir_mantencion_crear(request: Request, db: Session = Depends(get_db)):
    if (redir := guard_finanzas_mutacion(request)) is not None:
        return redir
    fd = _form_to_dict(await request.form())
    try:
        vid = _parse_int(fd.get("vehiculo_transporte_id"))
        if not vid:
            raise ValueError("Seleccione vehículo.")
        fecha = crud_fr.parse_fecha_formulario_date(str(fd.get("fecha") or ""))
        if not fecha:
            raise ValueError("Fecha inválida.")
        crud_fr.crear_mantencion(
            db,
            vehiculo_transporte_id=vid,
            fecha=fecha,
            odometro=_parse_int(fd.get("odometro")),
            tipo=str(fd.get("tipo") or "PREVENTIVA"),
            proveedor=str(fd.get("proveedor") or "") or None,
            documento=str(fd.get("documento") or "") or None,
            costo=_parse_decimal(fd.get("costo")),
            observaciones=str(fd.get("observaciones") or "") or None,
            proxima_fecha=crud_fr.parse_fecha_formulario_date(str(fd.get("proxima_fecha") or "") or None),
            proximo_km=_parse_int(fd.get("proximo_km")),
        )
        db.commit()
    except ValueError as e:
        db.rollback()
        return _redirect(request, "fondos_rendir_mantencion_nueva", msg=public_error_message(e), sev="danger")
    except SQLAlchemyError:
        db.rollback()
        return _redirect(request, "fondos_rendir_mantencion_nueva", msg="No se pudo registrar la mantención.", sev="danger")
    return _redirect(request, "fondos_rendir_mantenciones", msg="Mantención registrada.", sev="success")
