# routes/ui/remuneraciones.py
# -*- coding: utf-8 -*-
"""Remuneraciones: periodos, cálculo y contratos laborales (MVP)."""
from __future__ import annotations

import logging
from datetime import date
from decimal import Decimal, InvalidOperation
from typing import Any
from urllib.parse import urlencode

from fastapi import APIRouter, Depends, Request, status
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import select
from sqlalchemy.exc import OperationalError, ProgrammingError, SQLAlchemyError
from sqlalchemy.orm import Session

from core.paths import TEMPLATES_DIR
from core.public_errors import public_error_message
from core.rbac import (
    guard_remuneraciones_aprobacion_finanzas,
    guard_remuneraciones_aprobacion_rrhh,
    guard_remuneraciones_calcular,
    guard_remuneraciones_cerrar_pagar,
    guard_remuneraciones_consulta,
    usuario_puede_aprobar_remuneraciones_finanzas,
    usuario_puede_aprobar_remuneraciones_rrhh,
    usuario_puede_calcular_remuneraciones,
    usuario_puede_cerrar_o_pagar_remuneraciones,
    usuario_puede_gestionar_contratos_laborales,
)
from crud import fondos_rendir as crud_fr
from crud import remuneraciones as crud_rem
from crud.remuneraciones_contabilidad import contabilizar_pago_nomina_periodo
from db.session import get_db
from models.finanzas.compras_finanzas import CentroCosto
from services.remuneraciones.calculo_service import calcular_periodo, transicionar_estado

router = APIRouter(prefix="/remuneraciones", tags=["Remuneraciones"])
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))
logger = logging.getLogger(__name__)


def _redirect(request: Request, route_name: str, *, msg: str | None = None, sev: str = "info", **params: Any) -> RedirectResponse:
    url = str(request.url_for(route_name, **params))
    if msg:
        sep = "&" if "?" in url else "?"
        url = f"{url}{sep}{urlencode({'msg': msg, 'sev': sev})}"
    return RedirectResponse(url=url, status_code=status.HTTP_303_SEE_OTHER)


def _parse_decimal(v: str | None) -> Decimal | None:
    if v is None or str(v).strip() == "":
        return None
    try:
        return Decimal(str(v).strip().replace(",", "."))
    except (InvalidOperation, ValueError):
        return None


def _uid(request: Request) -> int | None:
    auth = getattr(request.state, "auth_user", None)
    if not isinstance(auth, dict):
        return None
    raw = auth.get("uid")
    try:
        return int(raw) if raw is not None else None
    except (TypeError, ValueError):
        return None


@router.get("", response_class=HTMLResponse, name="remuneraciones_periodos_lista")
def periodos_lista(request: Request, db: Session = Depends(get_db)):
    if (redir := guard_remuneraciones_consulta(request)) is not None:
        return redir
    try:
        periodos = crud_rem.listar_periodos_remuneracion(db)
    except (ProgrammingError, OperationalError) as exc:
        logger.exception("Remuneraciones: error de esquema o conexión al listar periodos: %s", exc)
        db.rollback()
        return _redirect(
            request,
            "home",
            msg=(
                "Remuneraciones: no se pudo leer la base (tablas o columnas faltantes). "
                "Ejecute en PostgreSQL el script db/psql/117_remuneraciones_bootstrap.sql en la BD del tenant "
                "o contacte al administrador."
            ),
            sev="danger",
        )
    auth = getattr(request.state, "auth_user", None)
    return templates.TemplateResponse(
        "remuneraciones/periodos_lista.html",
        {
            "request": request,
            "active_menu": "remuneraciones",
            "periodos": periodos,
            "puede_crear_periodo": usuario_puede_calcular_remuneraciones(auth),
            "puede_contratos": usuario_puede_gestionar_contratos_laborales(auth),
        },
    )


@router.get("/periodos/nuevo", response_class=HTMLResponse, name="remuneraciones_periodo_nuevo")
def periodo_nuevo_get(request: Request):
    if (redir := guard_remuneraciones_calcular(request)) is not None:
        return redir
    return templates.TemplateResponse(
        "remuneraciones/periodo_nuevo.html",
        {"request": request, "active_menu": "remuneraciones"},
    )


@router.post("/periodos/nuevo", name="remuneraciones_periodo_crear")
async def periodo_nuevo_post(request: Request, db: Session = Depends(get_db)):
    if (redir := guard_remuneraciones_calcular(request)) is not None:
        return redir
    fd = await request.form()
    try:
        anio = int(str(fd.get("anio") or "").strip())
        mes = int(str(fd.get("mes") or "").strip())
        pr = crud_rem.crear_periodo_remuneracion(db, anio=anio, mes=mes, usuario_creador_id=_uid(request))
        db.commit()
        return _redirect(request, "remuneraciones_periodo_detalle", msg="Periodo creado.", periodo_id=pr.id)
    except (ValueError, TypeError) as e:
        try:
            db.rollback()
        except Exception:
            pass
        return templates.TemplateResponse(
            "remuneraciones/periodo_nuevo.html",
            {
                "request": request,
                "active_menu": "remuneraciones",
                "error": str(e),
                "anio": fd.get("anio"),
                "mes": fd.get("mes"),
            },
            status_code=status.HTTP_400_BAD_REQUEST,
        )
    except SQLAlchemyError:
        logger.exception("Crear periodo remuneración")
        try:
            db.rollback()
        except Exception:
            pass
        return templates.TemplateResponse(
            "remuneraciones/periodo_nuevo.html",
            {
                "request": request,
                "active_menu": "remuneraciones",
                "error": public_error_message("No se pudo guardar el periodo."),
            },
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )


@router.get("/periodos/{periodo_id:int}", response_class=HTMLResponse, name="remuneraciones_periodo_detalle")
def periodo_detalle(request: Request, periodo_id: int, db: Session = Depends(get_db)):
    if (redir := guard_remuneraciones_consulta(request)) is not None:
        return redir
    pr = crud_rem.obtener_periodo_remuneracion(db, periodo_id)
    if not pr:
        return _redirect(request, "remuneraciones_periodos_lista", msg="Periodo no encontrado.", sev="warning")
    auth = getattr(request.state, "auth_user", None)
    return templates.TemplateResponse(
        "remuneraciones/periodo_detalle.html",
        {
            "request": request,
            "active_menu": "remuneraciones",
            "pr": pr,
            "puede_calcular": usuario_puede_calcular_remuneraciones(auth),
            "puede_aprobar_rrhh": usuario_puede_aprobar_remuneraciones_rrhh(auth),
            "puede_aprobar_finanzas": usuario_puede_aprobar_remuneraciones_finanzas(auth),
            "puede_cerrar_pagar": usuario_puede_cerrar_o_pagar_remuneraciones(auth),
            "puede_contratos": usuario_puede_gestionar_contratos_laborales(auth),
        },
    )


@router.post("/periodos/{periodo_id:int}/calcular", name="remuneraciones_periodo_calcular")
def periodo_calcular(request: Request, periodo_id: int, db: Session = Depends(get_db)):
    if (redir := guard_remuneraciones_calcular(request)) is not None:
        return redir
    try:
        calcular_periodo(db, periodo_id)
        db.commit()
        return _redirect(request, "remuneraciones_periodo_detalle", msg="Cálculo actualizado.", periodo_id=periodo_id)
    except ValueError as e:
        try:
            db.rollback()
        except Exception:
            pass
        return _redirect(request, "remuneraciones_periodo_detalle", msg=str(e), sev="warning", periodo_id=periodo_id)
    except SQLAlchemyError:
        logger.exception("Calcular remuneración")
        try:
            db.rollback()
        except Exception:
            pass
        return _redirect(
            request,
            "remuneraciones_periodo_detalle",
            msg=public_error_message("Error al calcular."),
            sev="danger",
            periodo_id=periodo_id,
        )


@router.post("/periodos/{periodo_id:int}/aprobar-rrhh", name="remuneraciones_periodo_aprobar_rrhh")
def periodo_aprobar_rrhh(request: Request, periodo_id: int, db: Session = Depends(get_db)):
    if (redir := guard_remuneraciones_aprobacion_rrhh(request)) is not None:
        return redir
    try:
        transicionar_estado(db, periodo_id, "APROBADO_RRHH", usuario_id=_uid(request))
        db.commit()
        return _redirect(request, "remuneraciones_periodo_detalle", msg="Aprobado RRHH.", periodo_id=periodo_id)
    except ValueError as e:
        try:
            db.rollback()
        except Exception:
            pass
        return _redirect(request, "remuneraciones_periodo_detalle", msg=str(e), sev="warning", periodo_id=periodo_id)
    except SQLAlchemyError:
        logger.exception("Aprobar RRHH remuneración")
        try:
            db.rollback()
        except Exception:
            pass
        return _redirect(
            request,
            "remuneraciones_periodo_detalle",
            msg=public_error_message("Error al aprobar."),
            sev="danger",
            periodo_id=periodo_id,
        )


@router.post("/periodos/{periodo_id:int}/aprobar-finanzas", name="remuneraciones_periodo_aprobar_finanzas")
def periodo_aprobar_finanzas(request: Request, periodo_id: int, db: Session = Depends(get_db)):
    if (redir := guard_remuneraciones_aprobacion_finanzas(request)) is not None:
        return redir
    try:
        transicionar_estado(db, periodo_id, "APROBADO_FINANZAS", usuario_id=_uid(request))
        db.commit()
        return _redirect(request, "remuneraciones_periodo_detalle", msg="Aprobado Finanzas.", periodo_id=periodo_id)
    except ValueError as e:
        try:
            db.rollback()
        except Exception:
            pass
        return _redirect(request, "remuneraciones_periodo_detalle", msg=str(e), sev="warning", periodo_id=periodo_id)
    except SQLAlchemyError:
        logger.exception("Aprobar finanzas remuneración")
        try:
            db.rollback()
        except Exception:
            pass
        return _redirect(
            request,
            "remuneraciones_periodo_detalle",
            msg=public_error_message("Error al aprobar."),
            sev="danger",
            periodo_id=periodo_id,
        )


@router.post("/periodos/{periodo_id:int}/cerrar", name="remuneraciones_periodo_cerrar")
def periodo_cerrar(request: Request, periodo_id: int, db: Session = Depends(get_db)):
    if (redir := guard_remuneraciones_cerrar_pagar(request)) is not None:
        return redir
    try:
        transicionar_estado(db, periodo_id, "CERRADO", usuario_id=_uid(request))
        db.commit()
        return _redirect(request, "remuneraciones_periodo_detalle", msg="Periodo cerrado.", periodo_id=periodo_id)
    except ValueError as e:
        try:
            db.rollback()
        except Exception:
            pass
        return _redirect(request, "remuneraciones_periodo_detalle", msg=str(e), sev="warning", periodo_id=periodo_id)
    except SQLAlchemyError:
        logger.exception("Cerrar remuneración")
        try:
            db.rollback()
        except Exception:
            pass
        return _redirect(
            request,
            "remuneraciones_periodo_detalle",
            msg=public_error_message("Error al cerrar."),
            sev="danger",
            periodo_id=periodo_id,
        )


@router.post("/periodos/{periodo_id:int}/pagar", name="remuneraciones_periodo_pagar")
def periodo_pagar(request: Request, periodo_id: int, db: Session = Depends(get_db)):
    if (redir := guard_remuneraciones_cerrar_pagar(request)) is not None:
        return redir
    try:
        pr = transicionar_estado(db, periodo_id, "PAGADO", usuario_id=_uid(request))
        auth_u = getattr(request.state, "auth_user", None) or {}
        usuario_lbl = str(auth_u.get("email") or auth_u.get("nombre") or "").strip() or None
        contabilizar_pago_nomina_periodo(db, pr, usuario=usuario_lbl)
        db.commit()
        msg = "Marcado como pagado."
        if pr.asiento_pago_id:
            msg += f" Asiento contable n.º {pr.asiento_pago_id}."
        return _redirect(request, "remuneraciones_periodo_detalle", msg=msg, periodo_id=periodo_id)
    except ValueError as e:
        try:
            db.rollback()
        except Exception:
            pass
        return _redirect(request, "remuneraciones_periodo_detalle", msg=str(e), sev="warning", periodo_id=periodo_id)
    except SQLAlchemyError:
        logger.exception("Pagar remuneración")
        try:
            db.rollback()
        except Exception:
            pass
        return _redirect(
            request,
            "remuneraciones_periodo_detalle",
            msg=public_error_message("Error al marcar pagado."),
            sev="danger",
            periodo_id=periodo_id,
        )


@router.get("/contratos/nuevo", response_class=HTMLResponse, name="remuneraciones_contrato_nuevo")
def contrato_nuevo_get(request: Request, db: Session = Depends(get_db), empleado_id: int | None = None):
    auth = getattr(request.state, "auth_user", None)
    if not usuario_puede_gestionar_contratos_laborales(auth):
        q = urlencode(
            {
                "msg": "No tiene permiso para contratos laborales (Administrador o RRHH).",
                "sev": "danger",
            }
        )
        return RedirectResponse(url=f"/?{q}", status_code=status.HTTP_303_SEE_OTHER)
    empleados = crud_fr.listar_empleados(db, solo_activos=True)
    centros = list(db.scalars(select(CentroCosto).where(CentroCosto.estado == "ACTIVO").order_by(CentroCosto.codigo)).all())
    return templates.TemplateResponse(
        "remuneraciones/contrato_nuevo.html",
        {
            "request": request,
            "active_menu": "remuneraciones",
            "empleados": empleados,
            "centros": centros,
            "empleado_id": empleado_id,
        },
    )


@router.post("/contratos/nuevo", name="remuneraciones_contrato_crear")
async def contrato_nuevo_post(request: Request, db: Session = Depends(get_db)):
    auth = getattr(request.state, "auth_user", None)
    if not usuario_puede_gestionar_contratos_laborales(auth):
        q = urlencode(
            {
                "msg": "No tiene permiso para contratos laborales (Administrador o RRHH).",
                "sev": "danger",
            }
        )
        return RedirectResponse(url=f"/?{q}", status_code=status.HTTP_303_SEE_OTHER)
    fd = await request.form()
    try:
        empleado_id = int(str(fd.get("empleado_id") or "").strip())
        fecha_inicio = date.fromisoformat(str(fd.get("fecha_inicio") or "").strip())
        fecha_fin_raw = str(fd.get("fecha_fin") or "").strip()
        fecha_fin = date.fromisoformat(fecha_fin_raw) if fecha_fin_raw else None
        tipo = str(fd.get("tipo_contrato") or "").strip() or None
        jornada = str(fd.get("jornada") or "").strip() or None
        sueldo = _parse_decimal(str(fd.get("sueldo_base") or ""))
        if sueldo is None or sueldo < 0:
            raise ValueError("Sueldo base inválido.")
        cc_raw = str(fd.get("centro_costo_id") or "").strip()
        cc_id = int(cc_raw) if cc_raw else None
        obs = str(fd.get("observaciones") or "").strip() or None
        crud_rem.crear_contrato_laboral(
            db,
            empleado_id=empleado_id,
            fecha_inicio=fecha_inicio,
            fecha_fin=fecha_fin,
            tipo_contrato=tipo,
            jornada=jornada,
            sueldo_base=sueldo,
            centro_costo_id=cc_id,
            observaciones=obs,
        )
        db.commit()
        return _redirect(request, "remuneraciones_periodos_lista", msg="Contrato laboral registrado.")
    except (ValueError, TypeError) as e:
        try:
            db.rollback()
        except Exception:
            pass
        empleados = crud_fr.listar_empleados(db, solo_activos=True)
        centros = list(db.scalars(select(CentroCosto).where(CentroCosto.estado == "ACTIVO").order_by(CentroCosto.codigo)).all())
        return templates.TemplateResponse(
            "remuneraciones/contrato_nuevo.html",
            {
                "request": request,
                "active_menu": "remuneraciones",
                "empleados": empleados,
                "centros": centros,
                "error": str(e),
                "form": dict(fd),
            },
            status_code=status.HTTP_400_BAD_REQUEST,
        )
    except SQLAlchemyError:
        logger.exception("Crear contrato laboral")
        try:
            db.rollback()
        except Exception:
            pass
        return _redirect(
            request,
            "remuneraciones_periodos_lista",
            msg=public_error_message("No se pudo guardar el contrato."),
            sev="danger",
        )
