# services/ux/workspace.py
# -*- coding: utf-8 -*-
"""Buscador global y bandeja de inicio. Respeta módulos visibles de la sesión."""
from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date
from typing import Any, Callable

from fastapi import Request
from sqlalchemy import func, or_, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from core.nav_visibility import usuario_puede_ver_modulo_nav, usuario_puede_ver_submodulo_nav
from core.rbac import usuario_es_admin, usuario_tiene_modulo_asignado
from core.validators import rut_para_busqueda

logger = logging.getLogger("evalua.ux")

_MESES = (
    "",
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

_LF_CERRADAS = ("ACTIVADA", "VIGENTE", "ANULADA", "PERDIDA_CLIENTE", "RECHAZADA")
_OT_CERRADAS = ("ENTREGADA", "CERRADA", "ANULADA", "FACTURADA", "CANCELADA")
_CXC_CERRADAS = ("ANULADA", "PAGADA")


@dataclass(frozen=True)
class AccionNav:
    id: str
    label: str
    hint: str
    route_name: str
    icon: str
    keywords: str
    modules: tuple[str, ...] = ()
    admin_only: bool = False


ACCIONES: tuple[AccionNav, ...] = (
    AccionNav("inicio", "Ir al inicio", "Portada y pendientes", "menu_principal", "bi-house-door", "home inicio panel"),
    AccionNav("nueva-venta", "Nueva nota de venta", "Emitir una venta", "nota_venta_form", "bi-shop", "venta pos nota nueva", ("COMERCIAL",)),
    AccionNav("notas", "Notas de venta", "Historial comercial", "nota_venta_lista", "bi-receipt", "notas emitidas ventas", ("COMERCIAL",)),
    AccionNav("clientes", "Clientes", "Maestro de clientes", "clientes_list", "bi-people", "cliente rut cartera", ("COMERCIAL",)),
    AccionNav("nuevo-cliente", "Nuevo cliente", "Alta de cliente", "clientes_form_nuevo", "bi-person-plus", "crear cliente", ("COMERCIAL",)),
    AccionNav("proveedores", "Proveedores", "Maestro de proveedores", "proveedor_lista", "bi-truck", "proveedor rut", ("COMERCIAL",)),
    AccionNav("nuevo-proveedor", "Nuevo proveedor", "Alta de proveedor", "proveedor_nuevo", "bi-truck", "crear proveedor", ("COMERCIAL",)),
    AccionNav("lf", "Leasing financiero", "Cotizaciones", "lf_cotizaciones_list", "bi-currency-dollar", "leasing financiero cotizacion", ("LEASING_FINANCIERO",)),
    AccionNav("lf-nueva", "Nueva cotización leasing", "Leasing financiero", "lf_cotizacion_nueva_form", "bi-plus-lg", "cotizar leasing financiero", ("LEASING_FINANCIERO",)),
    AccionNav("lop", "Leasing operativo", "Simulaciones y contratos", "leasing_operativo_hub", "bi-truck-front", "leasing operativo", ("LEASING_OPERATIVO",)),
    AccionNav("lop-sim", "Simular leasing operativo", "Nueva simulación", "leasing_operativo_simulador", "bi-calculator", "simulador operativo", ("LEASING_OPERATIVO",)),
    AccionNav("cobranza", "Cobranza", "Cartera y pagos", "cobranza_resumen", "bi-cash-stack", "cobrar cxc cartera", ("COBRANZA",)),
    AccionNav("riesgo", "Crédito y riesgo", "Evaluaciones", "credito_riesgo_dashboard", "bi-clipboard-data", "scoring credito riesgo", ("CREDITO_RIESGO",)),
    AccionNav("productos", "Productos", "Inventario", "productos_list", "bi-box-seam", "stock producto inventario", ("OPERACIONES",)),
    AccionNav("nuevo-producto", "Nuevo producto", "Alta de inventario", "producto_form_nuevo", "bi-plus-lg", "crear producto", ("OPERACIONES",)),
    AccionNav("taller", "Órdenes de taller", "Servicio", "taller_ordenes_lista", "bi-wrench-adjustable", "ot orden taller", ("OPERACIONES",)),
    AccionNav("taller-nueva", "Nueva orden de taller", "Recepción", "taller_orden_nueva", "bi-wrench", "nueva ot", ("OPERACIONES",)),
    AccionNav("cxp", "Cuentas por pagar", "Documentos de proveedores", "cxp_lista", "bi-wallet2", "cxp pagar factura", ("FINANZAS",)),
    AccionNav("cxp-nueva", "Nuevo documento por pagar", "Registrar factura", "cxp_nuevo", "bi-plus-lg", "nueva cxp", ("FINANZAS",)),
    AccionNav("periodos", "Cierre mensual", "Periodos contables", "fin_periodos", "bi-calendar-month", "periodo cerrar abrir", ("FINANZAS", "CONTABILIDAD")),
    AccionNav("tesoreria", "Tesorería", "Compras y ventas del SII", "tesoreria_home", "bi-receipt-cutoff", "tesoreria sii factura compra venta", ("TESORERIA", "FINANZAS")),
    AccionNav("asientos", "Asientos contables", "Libro diario", "contabilidad_asientos", "bi-journal-richtext", "asiento diario", ("CONTABILIDAD",)),
    AccionNav("fin-dash", "Dashboard de finanzas", "Indicadores", "fin_dashboard", "bi-bank", "finanzas dashboard", ("FINANZAS",)),
    AccionNav("rrhh", "Remuneraciones", "Nómina", "remuneraciones_rrhh_dashboard", "bi-people-fill", "sueldos rrhh nomina", ("RRHH",)),
    AccionNav("usuarios", "Usuarios y roles", "Administración", "seguridad_usuarios", "bi-shield-lock", "usuario permiso", admin_only=True),
)


def _norm(value: str) -> str:
    import unicodedata

    text = unicodedata.normalize("NFD", (value or "").lower())
    return "".join(ch for ch in text if unicodedata.category(ch) != "Mn").strip()


def _puede(auth: dict[str, Any] | None, key: str) -> bool:
    from core.module_catalog import NAV_SUBMODULE_KEYS

    if key in NAV_SUBMODULE_KEYS:
        return usuario_puede_ver_submodulo_nav(auth, key)
    return usuario_puede_ver_modulo_nav(auth, key) or usuario_tiene_modulo_asignado(auth, key)


def acciones_visibles(auth: dict[str, Any] | None, q: str = "") -> list[AccionNav]:
    needle = _norm(q)
    out: list[AccionNav] = []
    for accion in ACCIONES:
        if accion.admin_only and not usuario_es_admin(auth):
            continue
        if accion.modules and not any(_puede(auth, key) for key in accion.modules):
            continue
        if needle:
            blob = _norm(f"{accion.label} {accion.hint} {accion.keywords}")
            if needle not in blob and not all(part in blob for part in needle.split()):
                continue
        out.append(accion)
    return out


def _href(request: Request, route_name: str, **params: Any) -> str | None:
    try:
        return str(request.url_for(route_name, **params))
    except Exception:
        logger.debug("ruta ux no disponible: %s", route_name, exc_info=True)
        return None


def acciones_json(request: Request, auth: dict[str, Any] | None, q: str = "") -> list[dict[str, str]]:
    items: list[dict[str, str]] = []
    for accion in acciones_visibles(auth, q):
        href = _href(request, accion.route_name)
        if not href:
            continue
        items.append(
            {
                "kind": "accion",
                "id": accion.id,
                "label": accion.label,
                "detail": accion.hint,
                "href": href,
                "icon": accion.icon,
            }
        )
    return items


def _like(q: str) -> str:
    escaped = q.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return f"%{escaped}%"


def _safe(db: Session, loader: Callable[[], list[dict[str, str]]]) -> list[dict[str, str]]:
    try:
        return loader()
    except SQLAlchemyError:
        db.rollback()
        logger.exception("busqueda ux omitida")
        return []


def buscar_entidades(request: Request, db: Session, auth: dict[str, Any] | None, q: str) -> list[dict[str, str]]:
    term = (q or "").strip()
    if len(term) < 2:
        return []
    pat = _like(term)
    rut = rut_para_busqueda(term)
    found: list[dict[str, str]] = []

    if _puede(auth, "COMERCIAL"):
        found.extend(_safe(db, lambda: _clientes(request, db, pat, rut)))
        found.extend(_safe(db, lambda: _proveedores(request, db, pat, rut)))
        found.extend(_safe(db, lambda: _notas(request, db, pat, rut)))
    if _puede(auth, "OPERACIONES"):
        found.extend(_safe(db, lambda: _productos(request, db, pat)))
        found.extend(_safe(db, lambda: _ordenes(request, db, pat)))
    if _puede(auth, "LEASING_FINANCIERO"):
        found.extend(_safe(db, lambda: _cotizaciones_lf(request, db, pat, rut)))
    if _puede(auth, "LEASING_OPERATIVO"):
        found.extend(_safe(db, lambda: _contratos_lop(request, db, pat)))
    if _puede(auth, "FINANZAS"):
        found.extend(_safe(db, lambda: _cxp(request, db, pat)))
    return found[:24]


def _ilike(column: Any, pat: str):
    return column.ilike(pat, escape="\\")


def _clientes(request: Request, db: Session, pat: str, rut: str) -> list[dict[str, str]]:
    from models.maestros.cliente import Cliente

    conds = [
        _ilike(Cliente.razon_social, pat),
        _ilike(Cliente.nombre_fantasia, pat),
        _ilike(Cliente.rut, pat),
    ]
    if rut:
        conds.append(Cliente.rut == rut)
    rows = db.scalars(select(Cliente).where(or_(*conds)).order_by(Cliente.razon_social.asc()).limit(6)).all()
    items = []
    for row in rows:
        href = _href(request, "clientes_form_editar", cliente_id=row.id)
        if not href:
            continue
        items.append(
            {
                "kind": "cliente",
                "label": row.razon_social or "Cliente",
                "detail": row.rut or "",
                "href": href,
                "icon": "bi-people",
            }
        )
    return items


def _proveedores(request: Request, db: Session, pat: str, rut: str) -> list[dict[str, str]]:
    from models.maestros.proveedor import Proveedor

    conds = [_ilike(Proveedor.razon_social, pat), _ilike(Proveedor.rut, pat)]
    if rut:
        conds.append(Proveedor.rut == rut)
    rows = db.scalars(select(Proveedor).where(or_(*conds)).order_by(Proveedor.razon_social.asc()).limit(5)).all()
    items = []
    for row in rows:
        href = _href(request, "proveedor_editar", proveedor_id=row.id)
        if not href:
            continue
        items.append(
            {
                "kind": "proveedor",
                "label": row.razon_social or "Proveedor",
                "detail": row.rut or "",
                "href": href,
                "icon": "bi-truck",
            }
        )
    return items


def _notas(request: Request, db: Session, pat: str, rut: str) -> list[dict[str, str]]:
    from models.comercial.nota_venta import NotaVenta
    from models.maestros.cliente import Cliente

    conds = [_ilike(NotaVenta.numero, pat), _ilike(Cliente.razon_social, pat), _ilike(Cliente.rut, pat)]
    if rut:
        conds.append(Cliente.rut == rut)
    rows = db.execute(
        select(NotaVenta, Cliente.razon_social)
        .join(Cliente, Cliente.id == NotaVenta.cliente_id)
        .where(or_(*conds))
        .order_by(NotaVenta.fecha.desc())
        .limit(5)
    ).all()
    items = []
    for nota, razon in rows:
        href = _href(request, "nota_venta_detalle", nota_id=nota.id)
        if not href:
            continue
        items.append(
            {
                "kind": "nota",
                "label": f"Nota {nota.numero}",
                "detail": f"{razon or ''} · {nota.estado or ''}".strip(" ·"),
                "href": href,
                "icon": "bi-receipt",
            }
        )
    return items


def _productos(request: Request, db: Session, pat: str) -> list[dict[str, str]]:
    from models.inventario.inventario import Producto

    rows = db.scalars(
        select(Producto)
        .where(or_(_ilike(Producto.nombre, pat), _ilike(Producto.codigo, pat), _ilike(Producto.codigo_barra, pat)))
        .order_by(Producto.nombre.asc())
        .limit(5)
    ).all()
    items = []
    for row in rows:
        href = _href(request, "producto_form_editar", producto_id=row.id)
        if not href:
            continue
        items.append(
            {
                "kind": "producto",
                "label": row.nombre or "Producto",
                "detail": row.codigo or "",
                "href": href,
                "icon": "bi-box-seam",
            }
        )
    return items


def _ordenes(request: Request, db: Session, pat: str) -> list[dict[str, str]]:
    from models.comercial.orden_servicio import OrdenServicio

    rows = db.scalars(
        select(OrdenServicio).where(_ilike(OrdenServicio.folio, pat)).order_by(OrdenServicio.id.desc()).limit(4)
    ).all()
    items = []
    for row in rows:
        href = _href(request, "taller_orden_detalle", orden_id=row.id)
        if not href:
            continue
        items.append(
            {
                "kind": "orden",
                "label": f"OT {row.folio or row.id}",
                "detail": row.estado or "",
                "href": href,
                "icon": "bi-wrench-adjustable",
            }
        )
    return items


def _cotizaciones_lf(request: Request, db: Session, pat: str, rut: str) -> list[dict[str, str]]:
    from models.comercial.leasing_financiero_cotizacion import LeasingFinancieroCotizacion
    from models.maestros.cliente import Cliente

    conds = [
        _ilike(LeasingFinancieroCotizacion.numero_operacion, pat),
        _ilike(LeasingFinancieroCotizacion.numero_contrato, pat),
        _ilike(Cliente.razon_social, pat),
        _ilike(Cliente.rut, pat),
    ]
    if rut:
        conds.append(Cliente.rut == rut)
    rows = db.execute(
        select(LeasingFinancieroCotizacion, Cliente.razon_social)
        .join(Cliente, Cliente.id == LeasingFinancieroCotizacion.cliente_id)
        .where(or_(*conds))
        .order_by(LeasingFinancieroCotizacion.id.desc())
        .limit(4)
    ).all()
    items = []
    for cot, razon in rows:
        href = _href(request, "lf_cotizacion_detalle", cotizacion_id=cot.id)
        if not href:
            continue
        numero = cot.numero_operacion or cot.numero_contrato or str(cot.id)
        items.append(
            {
                "kind": "cotizacion",
                "label": f"Cotización {numero}",
                "detail": razon or "",
                "href": href,
                "icon": "bi-currency-dollar",
            }
        )
    return items


def _contratos_lop(request: Request, db: Session, pat: str) -> list[dict[str, str]]:
    from models.leasing_operativo.models import LeasingOpContrato

    rows = db.scalars(
        select(LeasingOpContrato).where(_ilike(LeasingOpContrato.codigo, pat)).order_by(LeasingOpContrato.id.desc()).limit(4)
    ).all()
    items = []
    for row in rows:
        href = _href(request, "leasing_operativo_detail", sim_id=row.simulacion_id)
        if not href:
            continue
        items.append(
            {
                "kind": "contrato",
                "label": f"Contrato {row.codigo}",
                "detail": row.estado or "",
                "href": href,
                "icon": "bi-truck-front",
            }
        )
    return items


def _cxp(request: Request, db: Session, pat: str) -> list[dict[str, str]]:
    from models.finanzas.compras_finanzas import APDocumento
    from models.maestros.proveedor import Proveedor

    rows = db.execute(
        select(APDocumento, Proveedor.razon_social)
        .join(Proveedor, Proveedor.id == APDocumento.proveedor_id)
        .where(or_(_ilike(APDocumento.folio, pat), _ilike(Proveedor.razon_social, pat), _ilike(Proveedor.rut, pat)))
        .order_by(APDocumento.id.desc())
        .limit(4)
    ).all()
    items = []
    for doc, razon in rows:
        href = _href(request, "cxp_detalle", documento_id=doc.id)
        if not href:
            continue
        items.append(
            {
                "kind": "cxp",
                "label": f"CxP {doc.folio}",
                "detail": f"{razon or ''} · {doc.estado or ''}".strip(" ·"),
                "href": href,
                "icon": "bi-wallet2",
            }
        )
    return items


def _count(db: Session, stmt) -> int:
    try:
        return int(db.scalar(stmt) or 0)
    except SQLAlchemyError:
        db.rollback()
        logger.exception("conteo de bandeja omitido")
        return 0


def armar_bandeja(
    request: Request,
    db: Session,
    *,
    auth: dict[str, Any] | None,
    resumen_cxp: dict[str, Any] | None,
    cxp_schema_ok: bool,
    periodo_mes_estado: str | None,
    n_clientes_activos: int,
    n_productos_alerta_stock: int,
    anio: int,
    mes: int,
) -> dict[str, list[dict[str, str]]]:
    items: list[dict[str, str]] = []
    hoy = date.today()

    if _puede(auth, "LEASING_FINANCIERO"):
        from models.comercial.leasing_financiero_cotizacion import LeasingFinancieroCotizacion

        abiertas = _count(
            db,
            select(func.count())
            .select_from(LeasingFinancieroCotizacion)
            .where(LeasingFinancieroCotizacion.estado_db.notin_(_LF_CERRADAS)),
        )
        href = _href(request, "lf_cotizaciones_list")
        if abiertas and href:
            items.append(
                {
                    "titulo": f"{abiertas} cotización{'es' if abiertas != 1 else ''} de leasing por cerrar",
                    "detalle": "Siguen fuera de activo adquirido, rechazo o anulación.",
                    "href": href,
                    "nivel": "MEDIA",
                    "kind": "leasing",
                    "icono": "bi-currency-dollar",
                }
            )

    if _puede(auth, "LEASING_OPERATIVO"):
        from models.leasing_operativo.models import LeasingOpContrato, LeasingOpSimulacion

        borradores = _count(
            db,
            select(func.count()).select_from(LeasingOpSimulacion).where(LeasingOpSimulacion.estado == "BORRADOR"),
        )
        href = _href(request, "leasing_operativo_list")
        if borradores and href:
            items.append(
                {
                    "titulo": f"{borradores} simulación{'es' if borradores != 1 else ''} operativa{'s' if borradores != 1 else ''} en borrador",
                    "detalle": "Retome el pricing antes de llevarlas a contrato.",
                    "href": href,
                    "nivel": "MEDIA",
                    "kind": "leasing",
                    "icono": "bi-truck-front",
                }
            )
        vigentes = _count(
            db,
            select(func.count()).select_from(LeasingOpContrato).where(LeasingOpContrato.estado == "VIGENTE"),
        )
        href_hub = _href(request, "leasing_operativo_hub")
        if vigentes and href_hub:
            items.append(
                {
                    "titulo": f"{vigentes} contrato{'s' if vigentes != 1 else ''} operativo{'s' if vigentes != 1 else ''} vigente{'s' if vigentes != 1 else ''}",
                    "detalle": "Cartera de leasing operativo en curso.",
                    "href": href_hub,
                    "nivel": "INFO",
                    "kind": "contrato",
                    "icono": "bi-file-earmark-text",
                }
            )

    if _puede(auth, "COBRANZA") or _puede(auth, "CREDITO_COBRANZAS"):
        from models.cobranza.cuentas_por_cobrar import CuentaPorCobrar

        vencidas = _count(
            db,
            select(func.count())
            .select_from(CuentaPorCobrar)
            .where(
                CuentaPorCobrar.saldo_pendiente > 0,
                CuentaPorCobrar.fecha_vencimiento < hoy,
                CuentaPorCobrar.estado.notin_(_CXC_CERRADAS),
            ),
        )
        href = _href(request, "cobranza_dashboard")
        if vencidas and href:
            items.append(
                {
                    "titulo": f"{vencidas} documento{'s' if vencidas != 1 else ''} vencido{'s' if vencidas != 1 else ''} por cobrar",
                    "detalle": "Tienen saldo y la fecha de vencimiento ya pasó.",
                    "href": href,
                    "nivel": "ALTA",
                    "kind": "cobranza",
                    "icono": "bi-hourglass-split",
                }
            )

    if _puede(auth, "FINANZAS") and cxp_schema_ok and resumen_cxp:
        docs = int(resumen_cxp.get("docs_vencidos") or 0)
        href = _href(request, "cxp_lista")
        if docs and href:
            items.append(
                {
                    "titulo": f"{docs} cuenta{'s' if docs != 1 else ''} por pagar vencida{'s' if docs != 1 else ''}",
                    "detalle": "Documentos de proveedores con saldo vencido.",
                    "href": href,
                    "nivel": "ALTA",
                    "kind": "cxp",
                    "icono": "bi-wallet2",
                }
            )

    if _puede(auth, "OPERACIONES"):
        from models.comercial.orden_servicio import OrdenServicio

        abiertas = _count(
            db,
            select(func.count()).select_from(OrdenServicio).where(OrdenServicio.estado.notin_(_OT_CERRADAS)),
        )
        href = _href(request, "taller_ordenes_lista")
        if abiertas and href:
            items.append(
                {
                    "titulo": f"{abiertas} {'orden' if abiertas == 1 else 'órdenes'} de taller abierta{'s' if abiertas != 1 else ''}",
                    "detalle": "Recepciones que aún no figuran como entregadas o anuladas.",
                    "href": href,
                    "nivel": "MEDIA",
                    "kind": "taller",
                    "icono": "bi-wrench-adjustable",
                }
            )
        if n_productos_alerta_stock > 0:
            href_prod = _href(request, "productos_list")
            if href_prod:
                items.append(
                    {
                        "titulo": f"{n_productos_alerta_stock} producto{'s' if n_productos_alerta_stock != 1 else ''} bajo el mínimo",
                        "detalle": "El stock actual está en el mínimo o por debajo.",
                        "href": href_prod,
                        "nivel": "MEDIA",
                        "kind": "stock",
                        "icono": "bi-box-seam",
                    }
                )

    if _puede(auth, "FINANZAS") or _puede(auth, "CONTABILIDAD"):
        href = _href(request, "fin_periodos")
        mes_nombre = _MESES[mes] if 1 <= mes <= 12 else str(mes)
        estado = (periodo_mes_estado or "").upper()
        if href and not estado:
            items.append(
                {
                    "titulo": f"Sin periodo contable de {mes_nombre} {anio}",
                    "detalle": "Créelo antes de registrar asientos de este mes.",
                    "href": href,
                    "nivel": "MEDIA",
                    "kind": "periodo",
                    "icono": "bi-calendar-month",
                }
            )
        elif href and estado == "ABIERTO":
            items.append(
                {
                    "titulo": f"Periodo de {mes_nombre} {anio} abierto",
                    "detalle": "Puede contabilizar. El cierre se hace desde esta pantalla.",
                    "href": href,
                    "nivel": "INFO",
                    "kind": "periodo",
                    "icono": "bi-calendar-month",
                }
            )

    puesta: list[dict[str, str]] = []
    if n_clientes_activos == 0 and _puede(auth, "COMERCIAL"):
        pasos = [
            (
                "1",
                "Cree el primer cliente",
                "La venta, la cobranza y el leasing parten de un RUT en el maestro.",
                "clientes_form_nuevo",
            ),
        ]
        if _puede(auth, "OPERACIONES"):
            from models.inventario.inventario import Producto

            n_prod = _count(db, select(func.count()).select_from(Producto))
            if n_prod == 0:
                pasos.append(
                    (
                        "2",
                        "Cargue un producto",
                        "Así la nota de venta puede mover stock y precio.",
                        "producto_form_nuevo",
                    )
                )
        pasos.append(
            (
                str(len(pasos) + 1),
                "Emita la primera nota de venta",
                "Con cliente y producto, el documento deja caja o cuenta por cobrar.",
                "nota_venta_form",
            )
        )
        for paso, titulo, detalle, route_name in pasos:
            href = _href(request, route_name)
            if href:
                puesta.append({"paso": paso, "titulo": titulo, "detalle": detalle, "href": href})

    return {"items": items, "puesta_en_marcha": puesta}
