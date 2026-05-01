# routes/ui/remuneraciones.py
# -*- coding: utf-8 -*-
"""Remuneraciones: periodos, cálculo y contratos laborales (MVP)."""
from __future__ import annotations

import logging
import csv
from datetime import date
from decimal import Decimal, InvalidOperation
from io import StringIO
from typing import Any
from urllib.parse import urlencode

from fastapi import APIRouter, Depends, Query, Request, status
from fastapi.responses import HTMLResponse, RedirectResponse, Response, StreamingResponse
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
from crud.remuneraciones_contabilidad import (
    contabilizar_pago_nomina_periodo,
    contabilizar_provision_nomina_periodo,
)
from db.session import get_db
from models.finanzas.compras_finanzas import CentroCosto
from services.remuneraciones.banco_transfer_csv import normalizar_formato_masivo
from services.remuneraciones.calculo_service import (
    calcular_periodo,
    puede_editar_periodo,
    transicionar_estado,
)
from services.remuneraciones.liquidacion_pdf import generar_liquidacion_pdf_bytes

router = APIRouter(prefix="/remuneraciones", tags=["Remuneraciones"])
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))
logger = logging.getLogger(__name__)

PARAMETROS_SUGERIDOS: tuple[tuple[str, str], ...] = (
    ("BONO_VIAJE_PCT_VALOR_FLETE", "Porcentaje de bono por viaje sobre valor flete."),
    ("DESCUENTO_AFP_PCT_IMPOSABLE", "Porcentaje AFP sobre base imponible."),
    ("DESCUENTO_SALUD_PCT_IMPOSABLE", "Porcentaje salud sobre base imponible."),
    ("VALOR_HORA_EXTRA", "Valor por hora extra (0 = cálculo automático sueldo/180*1.5)."),
    ("BONO_NOCTURNO_VALOR_HORA", "Valor por hora nocturna."),
)


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


def _registrar_auditoria_si_tabla(
    db: Session,
    *,
    periodo_id: int,
    empleado_id: int | None,
    actor_usuario_id: int | None,
    accion: str,
    detalle: str | None = None,
) -> None:
    try:
        crud_rem.registrar_auditoria_nomina(
            db,
            periodo_id=periodo_id,
            empleado_id=empleado_id,
            actor_usuario_id=actor_usuario_id,
            accion=accion,
            detalle=detalle,
        )
    except ProgrammingError:
        logger.warning("Auditoría remuneraciones: tabla no disponible (aplique parche 120).")


@router.get("/rrhh", response_class=HTMLResponse, name="remuneraciones_rrhh_dashboard")
def rrhh_dashboard(request: Request, db: Session = Depends(get_db)):
    if (redir := guard_remuneraciones_consulta(request)) is not None:
        return redir
    try:
        conteos = crud_rem.conteo_periodos_por_estado(db)
        periodos = crud_rem.listar_periodos_remuneracion(db, limite=24)
        sin_contrato = crud_rem.contar_empleados_activos_sin_contrato_vigente(db)
    except (ProgrammingError, OperationalError) as exc:
        logger.exception("Remuneraciones RRHH dashboard: %s", exc)
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
    pendientes_pago = [p for p in periodos if p.estado == "CERRADO"]
    pendientes_cierre = [p for p in periodos if p.estado == "APROBADO_FINANZAS"]
    pendientes_finanzas = [p for p in periodos if p.estado == "APROBADO_RRHH"]
    pendientes_rrhh = [p for p in periodos if p.estado in ("CALCULADO", "EN_REVISION")]
    return templates.TemplateResponse(
        "remuneraciones/rrhh_dashboard.html",
        {
            "request": request,
            "active_menu": "remuneraciones",
            "conteos": conteos,
            "periodos": periodos,
            "sin_contrato": sin_contrato,
            "pendientes_pago": pendientes_pago,
            "pendientes_cierre": pendientes_cierre,
            "pendientes_finanzas": pendientes_finanzas,
            "pendientes_rrhh": pendientes_rrhh,
            "puede_calcular": usuario_puede_calcular_remuneraciones(auth),
            "puede_aprobar_rrhh": usuario_puede_aprobar_remuneraciones_rrhh(auth),
            "puede_aprobar_finanzas": usuario_puede_aprobar_remuneraciones_finanzas(auth),
            "puede_cerrar_pagar": usuario_puede_cerrar_o_pagar_remuneraciones(auth),
            "puede_contratos": usuario_puede_gestionar_contratos_laborales(auth),
        },
    )


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


@router.get("/parametros", response_class=HTMLResponse, name="remuneraciones_parametros")
def parametros_get(request: Request, db: Session = Depends(get_db), periodo_id: int | None = None):
    if (redir := guard_remuneraciones_calcular(request)) is not None:
        return redir
    periodos = crud_rem.listar_periodos_remuneracion(db, limite=24)
    globales = {p.clave: p for p in crud_rem.listar_parametros_globales(db)}
    periodo = crud_rem.obtener_periodo_remuneracion(db, periodo_id) if periodo_id else None
    por_periodo = (
        {p.clave: p for p in crud_rem.listar_parametros_periodo(db, periodo_id)}
        if (periodo_id and periodo is not None)
        else {}
    )
    claves = sorted({*globales.keys(), *por_periodo.keys(), *(k for k, _ in PARAMETROS_SUGERIDOS)})
    rows: list[dict[str, Any]] = []
    for c in claves:
        g = globales.get(c)
        pp = por_periodo.get(c)
        sugerida = next((x[1] for x in PARAMETROS_SUGERIDOS if x[0] == c), None)
        rows.append(
            {
                "clave": c,
                "descripcion": (pp.descripcion if pp else (g.descripcion if g else sugerida)),
                "global_num": (g.valor_numerico if g else None),
                "global_txt": (g.valor_texto if g else None),
                "periodo_num": (pp.valor_numerico if pp else None),
                "periodo_txt": (pp.valor_texto if pp else None),
            }
        )
    return templates.TemplateResponse(
        "remuneraciones/parametros.html",
        {
            "request": request,
            "active_menu": "remuneraciones",
            "rows": rows,
            "periodos": periodos,
            "periodo_sel": periodo,
            "parametros_sugeridos": PARAMETROS_SUGERIDOS,
        },
    )


@router.post("/parametros", name="remuneraciones_parametros_guardar")
async def parametros_post(request: Request, db: Session = Depends(get_db)):
    if (redir := guard_remuneraciones_calcular(request)) is not None:
        return redir
    fd = await request.form()
    clave = str(fd.get("clave") or "").strip().upper()
    scope = str(fd.get("scope") or "global").strip().lower()
    periodo_raw = str(fd.get("periodo_id") or "").strip()
    descripcion = str(fd.get("descripcion") or "").strip() or None
    val_num = _parse_decimal(str(fd.get("valor_numerico") or "").strip())
    val_txt = str(fd.get("valor_texto") or "").strip() or None
    try:
        if not clave:
            raise ValueError("Clave obligatoria.")
        if scope == "periodo":
            if not periodo_raw:
                raise ValueError("Debe seleccionar periodo para guardar valor mensual.")
            crud_rem.upsert_parametro_periodo(
                db,
                periodo_id=int(periodo_raw),
                clave=clave,
                valor_numerico=val_num,
                valor_texto=val_txt,
                descripcion=descripcion,
            )
        else:
            crud_rem.upsert_parametro_global(
                db,
                clave=clave,
                valor_numerico=val_num,
                valor_texto=val_txt,
                descripcion=descripcion,
            )
        db.commit()
        params: dict[str, Any] = {"msg": "Parámetro guardado."}
        if periodo_raw:
            params["periodo_id"] = int(periodo_raw)
        return _redirect(request, "remuneraciones_parametros", **params)
    except (ValueError, TypeError) as e:
        db.rollback()
        params = {"msg": str(e), "sev": "warning"}
        if periodo_raw:
            params["periodo_id"] = int(periodo_raw)
        return _redirect(request, "remuneraciones_parametros", **params)
    except SQLAlchemyError:
        logger.exception("Guardar parámetro remuneraciones")
        db.rollback()
        params = {"msg": public_error_message("No se pudo guardar el parámetro."), "sev": "danger"}
        if periodo_raw:
            params["periodo_id"] = int(periodo_raw)
        return _redirect(request, "remuneraciones_parametros", **params)


@router.get("/periodos/{periodo_id:int}/libro", response_class=HTMLResponse, name="remuneraciones_libro")
def libro_periodo(request: Request, periodo_id: int, db: Session = Depends(get_db)):
    if (redir := guard_remuneraciones_consulta(request)) is not None:
        return redir
    pr = crud_rem.obtener_libro_periodo(db, periodo_id)
    if not pr:
        return _redirect(request, "remuneraciones_periodos_lista", msg="Periodo no encontrado.", sev="warning")
    rows = crud_rem.construir_libro_rows(pr)
    totales = crud_rem.totales_libro(rows)
    return templates.TemplateResponse(
        "remuneraciones/libro.html",
        {
            "request": request,
            "active_menu": "remuneraciones",
            "pr": pr,
            "rows": rows,
            "totales": totales,
        },
    )


@router.get("/periodos/{periodo_id:int}/libro.csv", name="remuneraciones_libro_csv")
def libro_periodo_csv(request: Request, periodo_id: int, db: Session = Depends(get_db)):
    if (redir := guard_remuneraciones_consulta(request)) is not None:
        return redir
    pr = crud_rem.obtener_libro_periodo(db, periodo_id)
    if not pr:
        return _redirect(request, "remuneraciones_periodos_lista", msg="Periodo no encontrado.", sev="warning")
    rows = crud_rem.construir_libro_rows(pr)
    sio = StringIO()
    writer = csv.writer(sio, delimiter=";")
    writer.writerow(
        [
            "Empleado",
            "Cargo",
            "Horas extras",
            "Haberes imponibles",
            "Haberes no imponibles",
            "Descuentos legales",
            "Otros descuentos",
            "Liquido",
        ]
    )
    for r in rows:
        writer.writerow(
            [
                r["empleado"],
                r["cargo"],
                r["horas_extras"],
                r["haberes_imponibles"],
                r["haberes_no_imponibles"],
                r["descuentos_legales"],
                r["otros_descuentos"],
                r["liquido"],
            ]
        )
    name = f"libro_remuneraciones_{pr.anio}_{pr.mes:02d}.csv"
    return Response(
        content=sio.getvalue(),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{name}"'},
    )


@router.get("/periodos/{periodo_id:int}/libro.xlsx", name="remuneraciones_libro_xlsx")
def libro_periodo_xlsx(request: Request, periodo_id: int, db: Session = Depends(get_db)):
    if (redir := guard_remuneraciones_consulta(request)) is not None:
        return redir
    pr = crud_rem.obtener_libro_periodo(db, periodo_id)
    if not pr:
        return _redirect(request, "remuneraciones_periodos_lista", msg="Periodo no encontrado.", sev="warning")
    content = crud_rem.exportar_libro_xlsx(pr)
    name = f"libro_remuneraciones_{pr.anio}_{pr.mes:02d}.xlsx"
    return Response(
        content=content,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{name}"'},
    )


@router.get(
    "/periodos/{periodo_id:int}/trabajadores/{empleado_id:int}/liquidacion.pdf",
    name="remuneraciones_liquidacion_pdf",
)
def liquidacion_pdf(request: Request, periodo_id: int, empleado_id: int, db: Session = Depends(get_db)):
    if (redir := guard_remuneraciones_consulta(request)) is not None:
        return redir
    det = crud_rem.obtener_detalle_periodo_empleado(db, periodo_id, empleado_id)
    if det is None or det.periodo is None:
        return _redirect(request, "remuneraciones_periodos_lista", msg="Detalle no encontrado.", sev="warning")
    data = generar_liquidacion_pdf_bytes(
        periodo_label=f"{det.periodo.mes:02d}/{det.periodo.anio}",
        empleado_nombre=(det.empleado.nombre_completo if det.empleado else f"ID {empleado_id}"),
        empleado_cargo=det.cargo_snapshot,
        detalle_resumen={
            "hab_imp": det.total_haberes_imponibles,
            "hab_no": det.total_haberes_no_imponibles,
            "des_leg": det.total_descuentos_legales,
            "des_otr": det.total_otros_descuentos,
            "liquido": det.liquido_a_pagar,
        },
        items_rows=[
            {
                "concepto": (it.concepto.nombre if it.concepto else "—"),
                "origen": it.origen,
                "cantidad": it.cantidad,
                "valor_unitario": it.valor_unitario,
                "monto_total": it.monto_total,
            }
            for it in det.items
        ],
    )
    filename = f"liquidacion_{empleado_id}_{det.periodo.anio}_{det.periodo.mes:02d}.pdf"
    return StreamingResponse(
        iter([data]),
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get(
    "/periodos/{periodo_id:int}/transferencias-banco.csv",
    name="remuneraciones_transferencias_banco_csv",
)
def transferencias_banco_csv(
    request: Request,
    periodo_id: int,
    formato: str = Query(
        "generico",
        description="generico, pesos_cl, banco_estado, bci, banco_chile, santander, scotiabank, security",
    ),
    db: Session = Depends(get_db),
):
    if (redir := guard_remuneraciones_consulta(request)) is not None:
        return redir
    fmt = normalizar_formato_masivo(formato)
    try:
        content = crud_rem.exportar_transferencias_nomina_csv(db, periodo_id, formato=fmt)
    except ValueError as e:
        return _redirect(
            request,
            "remuneraciones_periodos_lista",
            msg=str(e),
            sev="warning",
        )
    pr = crud_rem.obtener_periodo_remuneracion(db, periodo_id)
    label = f"{pr.mes:02d}_{pr.anio}" if pr else str(periodo_id)
    suf = "" if fmt == "generico" else f"_{fmt}"
    name = f"transferencias_nomina_{label}{suf}.csv"
    return Response(
        content=content.encode("utf-8"),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{name}"'},
    )


@router.post(
    "/periodos/{periodo_id:int}/empleados/{empleado_id:int}/items-manuales",
    name="remuneraciones_item_manual_crear",
)
async def item_manual_crear(
    request: Request,
    periodo_id: int,
    empleado_id: int,
    db: Session = Depends(get_db),
):
    if (redir := guard_remuneraciones_calcular(request)) is not None:
        return redir
    fd = await request.form()
    try:
        concepto_id = int(str(fd.get("concepto_id") or "").strip())
        monto = _parse_decimal(str(fd.get("monto") or "").strip())
        motivo = str(fd.get("motivo") or "").strip()
        if monto is None:
            raise ValueError("Monto inválido.")
        crud_rem.agregar_item_manual_nomina(
            db,
            periodo_id=periodo_id,
            empleado_id=empleado_id,
            concepto_id=concepto_id,
            monto=monto,
            motivo=motivo,
            actor_usuario_id=_uid(request),
        )
        db.commit()
        return _redirect(
            request,
            "remuneraciones_periodo_detalle",
            msg="Ajuste manual aplicado. Revise totales y liquidación PDF.",
            periodo_id=periodo_id,
        )
    except (ValueError, TypeError) as e:
        db.rollback()
        return _redirect(
            request,
            "remuneraciones_periodo_detalle",
            msg=str(e),
            sev="warning",
            periodo_id=periodo_id,
        )
    except SQLAlchemyError:
        logger.exception("Agregar ítem manual remuneración")
        db.rollback()
        return _redirect(
            request,
            "remuneraciones_periodo_detalle",
            msg=public_error_message("No se pudo registrar el ajuste."),
            sev="danger",
            periodo_id=periodo_id,
        )


@router.post(
    "/periodos/{periodo_id:int}/empleados/{empleado_id:int}/items-manuales/{item_id:int}/eliminar",
    name="remuneraciones_item_manual_eliminar",
)
def item_manual_eliminar(
    request: Request,
    periodo_id: int,
    empleado_id: int,
    item_id: int,
    db: Session = Depends(get_db),
):
    if (redir := guard_remuneraciones_calcular(request)) is not None:
        return redir
    try:
        crud_rem.eliminar_item_manual_nomina(
            db,
            periodo_id=periodo_id,
            empleado_id=empleado_id,
            item_id=item_id,
            actor_usuario_id=_uid(request),
        )
        db.commit()
        return _redirect(
            request,
            "remuneraciones_periodo_detalle",
            msg="Línea de ajuste eliminada.",
            periodo_id=periodo_id,
        )
    except (ValueError, TypeError) as e:
        db.rollback()
        return _redirect(
            request,
            "remuneraciones_periodo_detalle",
            msg=str(e),
            sev="warning",
            periodo_id=periodo_id,
        )
    except SQLAlchemyError:
        logger.exception("Eliminar ítem manual remuneración")
        db.rollback()
        return _redirect(
            request,
            "remuneraciones_periodo_detalle",
            msg=public_error_message("No se pudo eliminar la línea."),
            sev="danger",
            periodo_id=periodo_id,
        )


@router.get("/periodos/{periodo_id:int}/horas", response_class=HTMLResponse, name="remuneraciones_horas")
def horas_get(request: Request, periodo_id: int, db: Session = Depends(get_db)):
    if (redir := guard_remuneraciones_calcular(request)) is not None:
        return redir
    pr = crud_rem.obtener_periodo_remuneracion(db, periodo_id)
    if not pr:
        return _redirect(request, "remuneraciones_periodos_lista", msg="Periodo no encontrado.", sev="warning")
    existing = {h.empleado_id: h for h in crud_rem.listar_horas_periodo(db, periodo_id)}
    empleados = crud_fr.listar_empleados(db, solo_activos=True)
    rows = []
    for e in empleados:
        h = existing.get(e.id)
        rows.append(
            {
                "empleado": e,
                "horas_ordinarias": (h.horas_ordinarias if h else Decimal("0")),
                "horas_extras": (h.horas_extras if h else Decimal("0")),
                "horas_nocturnas": (h.horas_nocturnas if h else Decimal("0")),
                "motivo_ajuste": (h.motivo_ajuste if h else ""),
                "es_ajuste_manual": bool(h.es_ajuste_manual) if h else False,
            }
        )
    return templates.TemplateResponse(
        "remuneraciones/horas_periodo.html",
        {"request": request, "active_menu": "remuneraciones", "pr": pr, "rows": rows},
    )


@router.post("/periodos/{periodo_id:int}/horas", name="remuneraciones_horas_guardar")
async def horas_post(request: Request, periodo_id: int, db: Session = Depends(get_db)):
    if (redir := guard_remuneraciones_calcular(request)) is not None:
        return redir
    fd = await request.form()
    uid = _uid(request)
    try:
        for key in fd.keys():
            if not str(key).startswith("empleado_"):
                continue
            empleado_id = int(str(key).split("_", 1)[1])
            ho = _parse_decimal(str(fd.get(f"ho_{empleado_id}") or "0")) or Decimal("0")
            hx = _parse_decimal(str(fd.get(f"hx_{empleado_id}") or "0")) or Decimal("0")
            hn = _parse_decimal(str(fd.get(f"hn_{empleado_id}") or "0")) or Decimal("0")
            motivo = str(fd.get(f"motivo_{empleado_id}") or "").strip() or None
            manual = str(fd.get(f"manual_{empleado_id}") or "").strip().lower() in {"on", "1", "true", "si"}
            crud_rem.guardar_horas_periodo(
                db,
                periodo_id=periodo_id,
                empleado_id=empleado_id,
                horas_ordinarias=ho,
                horas_extras=hx,
                horas_nocturnas=hn,
                es_ajuste_manual=manual,
                motivo_ajuste=motivo,
                usuario_ajuste_id=uid,
            )
        db.commit()
        return _redirect(
            request,
            "remuneraciones_periodo_detalle",
            msg="Horas mensuales guardadas. Recalcule el período para aplicar cambios.",
            periodo_id=periodo_id,
        )
    except (ValueError, TypeError) as e:
        db.rollback()
        return _redirect(request, "remuneraciones_horas", msg=str(e), sev="warning", periodo_id=periodo_id)
    except SQLAlchemyError:
        logger.exception("Guardar horas periodo")
        db.rollback()
        return _redirect(
            request,
            "remuneraciones_horas",
            msg=public_error_message("No se pudo guardar la carga de horas."),
            sev="danger",
            periodo_id=periodo_id,
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
    puede_ajustar = bool(
        usuario_puede_calcular_remuneraciones(auth) and puede_editar_periodo(pr)
    )
    conceptos_ajuste = (
        crud_rem.listar_conceptos_remuneracion_activos(db) if puede_ajustar else []
    )
    try:
        audit_logs = crud_rem.listar_auditoria_periodo_vista(db, periodo_id, limite=50)
    except ProgrammingError:
        audit_logs = []
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
            "puede_ajustar": puede_ajustar,
            "conceptos_ajuste": conceptos_ajuste,
            "audit_logs": audit_logs,
        },
    )


@router.post("/periodos/{periodo_id:int}/provision-contable", name="remuneraciones_periodo_provision_contable")
def periodo_provision_contable(request: Request, periodo_id: int, db: Session = Depends(get_db)):
    if (redir := guard_remuneraciones_cerrar_pagar(request)) is not None:
        return redir
    pr = crud_rem.obtener_periodo_remuneracion(db, periodo_id)
    if not pr:
        return _redirect(request, "remuneraciones_periodos_lista", msg="Periodo no encontrado.", sev="warning")
    if getattr(pr, "asiento_provision_id", None):
        return _redirect(
            request,
            "remuneraciones_periodo_detalle",
            msg="Este período ya tiene provisión contable registrada.",
            sev="warning",
            periodo_id=periodo_id,
        )
    if pr.estado not in ("APROBADO_FINANZAS", "CERRADO"):
        return _redirect(
            request,
            "remuneraciones_periodo_detalle",
            msg="La provisión solo está disponible con el período aprobado por finanzas o cerrado (antes de marcar pagado).",
            sev="warning",
            periodo_id=periodo_id,
        )
    auth_u = getattr(request.state, "auth_user", None) or {}
    usuario_lbl = str(auth_u.get("email") or auth_u.get("nombre") or "").strip() or None
    try:
        aid = contabilizar_provision_nomina_periodo(db, pr, usuario=usuario_lbl)
        if aid is None:
            db.rollback()
            return _redirect(
                request,
                "remuneraciones_periodo_detalle",
                msg="No hay líquido para provisionar o faltan cuentas en el plan (gasto / sueldos por pagar).",
                sev="warning",
                periodo_id=periodo_id,
            )
        _registrar_auditoria_si_tabla(
            db,
            periodo_id=periodo_id,
            empleado_id=None,
            actor_usuario_id=_uid(request),
            accion="PROVISION_CONTABLE",
            detalle=f"asiento_provision_id={aid}",
        )
        db.commit()
        return _redirect(
            request,
            "remuneraciones_periodo_detalle",
            msg=f"Provisión contable registrada (asiento n.º {aid}).",
            periodo_id=periodo_id,
        )
    except ValueError as e:
        try:
            db.rollback()
        except Exception:
            pass
        return _redirect(request, "remuneraciones_periodo_detalle", msg=str(e), sev="warning", periodo_id=periodo_id)
    except SQLAlchemyError:
        logger.exception("Provisión contable remuneración")
        try:
            db.rollback()
        except Exception:
            pass
        return _redirect(
            request,
            "remuneraciones_periodo_detalle",
            msg=public_error_message("No se pudo registrar la provisión contable."),
            sev="danger",
            periodo_id=periodo_id,
        )


@router.post("/periodos/{periodo_id:int}/calcular", name="remuneraciones_periodo_calcular")
def periodo_calcular(request: Request, periodo_id: int, db: Session = Depends(get_db)):
    if (redir := guard_remuneraciones_calcular(request)) is not None:
        return redir
    try:
        calcular_periodo(db, periodo_id)
        _registrar_auditoria_si_tabla(
            db,
            periodo_id=periodo_id,
            empleado_id=None,
            actor_usuario_id=_uid(request),
            accion="PERIODO_RECALCULADO",
            detalle=None,
        )
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
        _registrar_auditoria_si_tabla(
            db,
            periodo_id=periodo_id,
            empleado_id=None,
            actor_usuario_id=_uid(request),
            accion="APROBADO_RRHH",
            detalle=None,
        )
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
        _registrar_auditoria_si_tabla(
            db,
            periodo_id=periodo_id,
            empleado_id=None,
            actor_usuario_id=_uid(request),
            accion="APROBADO_FINANZAS",
            detalle=None,
        )
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
        _registrar_auditoria_si_tabla(
            db,
            periodo_id=periodo_id,
            empleado_id=None,
            actor_usuario_id=_uid(request),
            accion="PERIODO_CERRADO",
            detalle=None,
        )
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
        _registrar_auditoria_si_tabla(
            db,
            periodo_id=periodo_id,
            empleado_id=None,
            actor_usuario_id=_uid(request),
            accion="PERIODO_PAGADO",
            detalle=f"asiento_pago_id={getattr(pr, 'asiento_pago_id', None)}",
        )
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
