# routes/ui/inicio.py
# -*- coding: utf-8 -*-
from __future__ import annotations

import html
import logging
from collections.abc import Generator
from datetime import date
from decimal import Decimal

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import case, extract, func, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from core.config import settings
from core.paths import TEMPLATES_DIR
from core.public_errors import log_unhandled
from crud.cobranza import cobranza as crud_cobranza
from crud.finanzas.cuentas_por_pagar import cuentas_por_pagar as crud_cxp
from db.session import get_session_local
from models import Cliente, NotaVenta, PagoCliente, Producto, Proveedor
from models.finanzas.compras_finanzas import Periodo
from routes.ui.auth import render_login_form

router = APIRouter(tags=["Inicio"])

templates = Jinja2Templates(directory=str(TEMPLATES_DIR))

logger = logging.getLogger(__name__)

_CXP_RESUMEN_FALLBACK: dict[str, Decimal | int] = {
    "documentos": 0,
    "total_documentado": Decimal("0"),
    "saldo_pendiente": Decimal("0"),
    "saldo_vencido": Decimal("0"),
    "saldo_por_vencer": Decimal("0"),
    "facturacion_liquidada": Decimal("0"),
    "total_aplicado_hist": Decimal("0"),
    "docs_vencidos": 0,
    "docs_por_vencer": 0,
}

_MESES_ES = (
    "enero",
    "febrero",
    "marzo",
    "abril",
    "mayo",
    "junio",
    "julio",
    "agosto",
    "septiembre",
    "octubre",
    "noviembre",
    "diciembre",
)
_DIAS_ES = (
    "lunes",
    "martes",
    "miércoles",
    "jueves",
    "viernes",
    "sábado",
    "domingo",
)


def _fecha_larga_es(d: date) -> str:
    return f"{_DIAS_ES[d.weekday()]}, {d.day} de {_MESES_ES[d.month - 1]} de {d.year}"


def get_db_for_menu_principal(request: Request) -> Generator[Session | None, None, None]:
    """Sin sesión no abre BD: la portada muestra el login en `/`."""
    if getattr(request.state, "auth_user", None) is None:
        yield None
        return
    SessionLocal = get_session_local()
    db: Session = SessionLocal()
    try:
        yield db
    except SQLAlchemyError:
        db.rollback()
        raise
    finally:
        db.close()


def _menu_principal_impl(request: Request, db: Session) -> HTMLResponse:
    hoy = date.today()
    anio = hoy.year
    mes = hoy.month

    row_ventas_mes = (
        db.execute(
            select(
                func.coalesce(func.sum(NotaVenta.total_total), 0).label("total_ventas"),
                func.count(NotaVenta.id).label("documentos"),
            ).where(
                extract("year", NotaVenta.fecha) == anio,
                extract("month", NotaVenta.fecha) == mes,
                NotaVenta.estado != "ANULADA",
            )
        )
        .mappings()
        .first()
    ) or {"total_ventas": 0, "documentos": 0}

    row_ventas_anual = (
        db.execute(
            select(
                func.coalesce(func.sum(NotaVenta.total_total), 0).label("total_ventas"),
                func.count(NotaVenta.id).label("documentos"),
            ).where(
                extract("year", NotaVenta.fecha) == anio,
                NotaVenta.estado != "ANULADA",
            )
        )
        .mappings()
        .first()
    ) or {"total_ventas": 0, "documentos": 0}

    row_cobranza_mes = (
        db.execute(
            select(
                func.coalesce(func.sum(PagoCliente.monto_pago), 0).label("total_cobrado"),
                func.count(PagoCliente.id).label("documentos"),
            ).where(
                extract("year", PagoCliente.fecha_pago) == anio,
                extract("month", PagoCliente.fecha_pago) == mes,
            )
        )
        .mappings()
        .first()
    ) or {"total_cobrado": 0, "documentos": 0}

    row_cobranza_anual = (
        db.execute(
            select(
                func.coalesce(func.sum(PagoCliente.monto_pago), 0).label("total_cobrado"),
                func.count(PagoCliente.id).label("documentos"),
            ).where(
                extract("year", PagoCliente.fecha_pago) == anio,
            )
        )
        .mappings()
        .first()
    ) or {"total_cobrado": 0, "documentos": 0}

    productos_stock = list(
        db.scalars(
            select(Producto)
            .order_by(
                case(
                    (Producto.stock_actual <= func.coalesce(Producto.stock_minimo, 0), 0),
                    else_=1,
                ),
                Producto.nombre.asc(),
            )
            .limit(50)
        )
    )

    n_clientes_activos = int(
        db.scalar(select(func.count()).select_from(Cliente).where(Cliente.activo.is_(True)))
        or 0
    )
    n_proveedores_activos = int(
        db.scalar(select(func.count()).select_from(Proveedor).where(Proveedor.activo.is_(True)))
        or 0
    )
    n_productos_alerta_stock = int(
        db.scalar(
            select(func.count())
            .select_from(Producto)
            .where(Producto.stock_actual <= func.coalesce(Producto.stock_minimo, 0))
        )
        or 0
    )

    periodo_mes_estado: str | None = None
    try:
        periodo_row = db.scalars(
            select(Periodo).where(Periodo.anio == anio, Periodo.mes == mes)
        ).first()
        if periodo_row is not None:
            periodo_mes_estado = str(periodo_row.estado)
    except Exception:
        periodo_mes_estado = None

    try:
        resumen_cxp = crud_cxp.get_resumen(db)
        cxp_schema_ok = crud_cxp.ap_tablas_operativas(db)
    except Exception:
        logger.exception(
            "Inicio: falló el resumen CxP (tablas AP o SQL); se muestran cerros y KPI AP desactivado."
        )
        resumen_cxp = dict(_CXP_RESUMEN_FALLBACK)
        cxp_schema_ok = False

    try:
        resumen_cobranza_global = crud_cobranza.resumen_cobranza_general(db)
    except Exception:
        logger.exception("Inicio: falló resumen_cobranza_general; usando ceros.")
        resumen_cobranza_global = {
            "total_documentos": 0,
            "total_monto": 0,
            "total_saldo": 0,
        }

    ventas_mes_total = Decimal(str(row_ventas_mes["total_ventas"] or 0))
    cobranza_mes_total = Decimal(str(row_cobranza_mes["total_cobrado"] or 0))
    por_cobrar_total = Decimal(str(resumen_cobranza_global.get("total_saldo") or 0))
    cxp_vencido = Decimal(str(resumen_cxp.get("saldo_vencido") if resumen_cxp else 0))
    cxp_pendiente = Decimal(str(resumen_cxp.get("saldo_pendiente") if resumen_cxp else 0))

    tasa_cobranza_mes = Decimal("0")
    if ventas_mes_total > 0:
        tasa_cobranza_mes = ((cobranza_mes_total / ventas_mes_total) * Decimal("100")).quantize(
            Decimal("0.01")
        )

    run_rate_mensual = ventas_mes_total
    proy_30 = run_rate_mensual
    proy_60 = run_rate_mensual * Decimal("2")
    proy_90 = run_rate_mensual * Decimal("3")

    alertas_criticas: list[dict[str, str]] = []
    if por_cobrar_total > Decimal("0"):
        alertas_criticas.append(
            {
                "nivel": "ALTA" if por_cobrar_total > ventas_mes_total else "MEDIA",
                "titulo": "Cartera por cobrar relevante",
                "detalle": f"Saldo por cobrar vigente: {float(por_cobrar_total):,.0f}",
                "ruta": "cobranza_dashboard",
            }
        )
    if cxp_vencido > 0:
        alertas_criticas.append(
            {
                "nivel": "ALTA",
                "titulo": "Compromisos vencidos con proveedores",
                "detalle": f"Saldo vencido CxP: {float(cxp_vencido):,.0f}",
                "ruta": "cxp_lista",
            }
        )
    if (n_productos_alerta_stock or 0) > 0:
        alertas_criticas.append(
            {
                "nivel": "ALTA" if (n_productos_alerta_stock or 0) >= 10 else "MEDIA",
                "titulo": "Riesgo de quiebre de stock",
                "detalle": f"Productos en alerta: {int(n_productos_alerta_stock or 0)}",
                "ruta": "productos_list",
            }
        )
    if periodo_mes_estado == "CERRADO":
        alertas_criticas.append(
            {
                "nivel": "MEDIA",
                "titulo": "Periodo contable cerrado",
                "detalle": "Revise apertura para evitar bloqueo operativo.",
                "ruta": "fin_periodos",
            }
        )

    semaforo_operacion = "VERDE"
    if any(a["nivel"] == "ALTA" for a in alertas_criticas):
        semaforo_operacion = "ROJO"
    elif alertas_criticas:
        semaforo_operacion = "AMARILLO"

    acciones_sugeridas = [
        {
            "titulo": "Acelerar cobranza de alto saldo",
            "detalle": "Priorizar documentos con mayor saldo para mejorar caja de corto plazo.",
            "impacto": "Alto",
            "ruta": "cobranza_dashboard",
        },
        {
            "titulo": "Corregir quiebres de inventario",
            "detalle": "Ejecutar compras/reabastecimiento para proteger continuidad de ventas.",
            "impacto": "Alto",
            "ruta": "productos_list",
        },
        {
            "titulo": "Ajustar políticas de crédito",
            "detalle": "Revisar umbrales de aprobación para controlar riesgo y morosidad esperada.",
            "impacto": "Medio",
            "ruta": "credito_riesgo_dashboard",
        },
    ]

    salud_modulos = [
        {"modulo": "Comercial", "estado": "VERDE" if ventas_mes_total > 0 else "AMARILLO"},
        {"modulo": "Cobranza", "estado": "ROJO" if tasa_cobranza_mes < 55 else ("AMARILLO" if tasa_cobranza_mes < 75 else "VERDE")},
        {"modulo": "Abastecimiento", "estado": "ROJO" if (n_productos_alerta_stock or 0) >= 10 else ("AMARILLO" if (n_productos_alerta_stock or 0) > 0 else "VERDE")},
        {"modulo": "Cuentas por pagar", "estado": "ROJO" if cxp_vencido > 0 else ("AMARILLO" if cxp_pendiente > 0 else "VERDE")},
        {"modulo": "Riesgo crédito", "estado": "VERDE"},
    ]

    return templates.TemplateResponse(
        "inicio/bienvenida.html",
        {
            "request": request,
            "active_menu": "inicio",
            "hoy": hoy,
            "fecha_hoy_largo": _fecha_larga_es(hoy),
            "anio_actual": anio,
            "mes_actual": mes,
            "resumen_ventas_mes": {
                "total_ventas": float(row_ventas_mes["total_ventas"] or 0),
                "documentos": int(row_ventas_mes["documentos"] or 0),
            },
            "resumen_ventas_anual": {
                "total_ventas": float(row_ventas_anual["total_ventas"] or 0),
                "documentos": int(row_ventas_anual["documentos"] or 0),
            },
            "resumen_cobranza_mes": {
                "total_cobrado": float(row_cobranza_mes["total_cobrado"] or 0),
                "documentos": int(row_cobranza_mes["documentos"] or 0),
            },
            "resumen_cobranza_anual": {
                "total_cobrado": float(row_cobranza_anual["total_cobrado"] or 0),
                "documentos": int(row_cobranza_anual["documentos"] or 0),
            },
            "resumen_cobranza_global": resumen_cobranza_global,
            "resumen_cxp": resumen_cxp,
            "cxp_schema_ok": cxp_schema_ok,
            "n_clientes_activos": n_clientes_activos,
            "n_proveedores_activos": n_proveedores_activos,
            "n_productos_alerta_stock": n_productos_alerta_stock,
            "periodo_mes_estado": periodo_mes_estado,
            "productos_stock": productos_stock,
            "semaforo_operacion": semaforo_operacion,
            "tasa_cobranza_mes": float(tasa_cobranza_mes),
            "proyeccion_30": float(proy_30),
            "proyeccion_60": float(proy_60),
            "proyeccion_90": float(proy_90),
            "alertas_criticas": alertas_criticas,
            "acciones_sugeridas": acciones_sugeridas,
            "salud_modulos": salud_modulos,
        },
    )


@router.get("/", response_class=HTMLResponse, name="menu_principal")
def menu_principal(
    request: Request,
    db: Session | None = Depends(get_db_for_menu_principal),
):
    """Portada: ante cualquier fallo (BD incompleta, plantilla, etc.) no devolver 500 opaco."""
    try:
        if db is None:
            return render_login_form(
                request,
                next_url=(request.query_params.get("next") or "").strip(),
                msg=request.query_params.get("msg"),
                sev=(request.query_params.get("sev") or "danger"),
            )
        return _menu_principal_impl(request, db)
    except Exception as exc:
        err_id = log_unhandled("Error al renderizar la portada (/)", exc)
        detalle = ""
        if settings.is_dev:
            detalle = f"<pre class=\"mt-3 small text-danger text-start\">{html.escape(repr(exc))}</pre>"
        else:
            detalle = (
                "<p class=\"small text-muted\">Identificador de informe: "
                f"<code class=\"user-select-all\">{html.escape(err_id)}</code></p>"
            )
        body = (
            "<!DOCTYPE html><html lang=\"es\"><head><meta charset=\"utf-8\"/>"
            "<meta name=\"viewport\" content=\"width=device-width, initial-scale=1\"/>"
            "<title>Inicio no disponible · Evalua ERP</title>"
            "<link href=\"https://cdn.jsdelivr.net/npm/bootstrap@5.3.2/dist/css/bootstrap.min.css\" rel=\"stylesheet\">"
            "</head><body class=\"p-4 bg-light\">"
            "<div class=\"mx-auto\" style=\"max-width:560px\">"
            "<h1 class=\"h4\">No se pudo cargar el panel de inicio</h1>"
            "<p class=\"text-muted\">Su sesión puede seguir activa. Puede reintentar o cerrar sesión.</p>"
            "<div class=\"d-flex gap-2 flex-wrap mt-3\">"
            "<a class=\"btn btn-primary\" href=\"/\">Reintentar</a>"
            "<form method=\"post\" action=\"/logout\">"
            "<button type=\"submit\" class=\"btn btn-outline-danger\">Cerrar sesión</button>"
            "</form></div>"
            f"{detalle}"
            "<p class=\"small text-muted mt-4\">Si es administrador, revise el log de Uvicorn y el esquema de la base "
            "(tablas de ventas, cobranza, productos, etc.).</p>"
            "</div></body></html>"
        )
        return HTMLResponse(content=body, status_code=503)