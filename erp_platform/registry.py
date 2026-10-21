# platform/registry.py
# -*- coding: utf-8 -*-
"""
Registro declarativo de módulos ERP (catálogo + navegación + ownership).

Fuente de verdad de bounded contexts y `nav_module_key`.
`core.module_catalog` adapta esas claves al menú Jinja/RBAC; no debe
introducir claves huérfanas (ver tests/test_architecture_boundaries.py).
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class ErpModule:
    code: str
    name: str
    domain: str  # platform | comercial | financiero | operaciones | rrhh | analytics
    icon: str = "bi-grid"
    route_name: str | None = None
    nav_module_key: str | None = None  # clave visibleModules
    permissions: tuple[str, ...] = ()
    depends_on: tuple[str, ...] = ()
    owns_schemas: tuple[str, ...] = ()  # ownership lógico de datos
    description: str = ""


ERP_MODULES: tuple[ErpModule, ...] = (
    ErpModule(
        code="PLATFORM",
        name="Plataforma",
        domain="platform",
        icon="bi-shield-lock",
        nav_module_key="ADMINISTRACION",
        permissions=("ADMIN.USERS", "ADMIN.BACKUPS", "ADMIN.AUDIT"),
        owns_schemas=("auth", "identity", "mail", "ops"),
        description="Identity, tenancy, RBAC, auditoría, correo, respaldos.",
    ),
    ErpModule(
        code="EMPRESAS",
        name="Empresas",
        domain="platform",
        icon="bi-buildings",
        route_name="plataforma_empresas",
        nav_module_key="EMPRESAS",
        permissions=("ADMIN.USERS",),
        depends_on=("PLATFORM",),
        owns_schemas=("identity",),
        description="Gestión multiempresa (solo modo database_per_company).",
    ),
    ErpModule(
        code="COMERCIAL",
        name="Comercial",
        domain="comercial",
        icon="bi-briefcase",
        route_name="comercial_hub",
        nav_module_key="COMERCIAL",
        depends_on=("PLATFORM",),
        owns_schemas=("clientes", "nota_venta", "postventa"),
    ),
    ErpModule(
        code="LEASING_FINANCIERO",
        name="Leasing financiero",
        domain="financiero",
        icon="bi-currency-dollar",
        route_name="leasing_financiero_hub",
        nav_module_key="LEASING_FINANCIERO",
        permissions=("LEASING.VIEW", "LEASING.CREATE", "LEASING.APPROVE"),
        depends_on=("COMERCIAL", "CREDITO", "CONTABILIDAD"),
        owns_schemas=("leasing_financiero",),
    ),
    ErpModule(
        code="LEASING_OPERATIVO",
        name="Leasing operativo",
        domain="financiero",
        icon="bi-truck-front",
        route_name="leasing_operativo_hub",
        nav_module_key="LEASING_OPERATIVO",
        permissions=("LEASING.VIEW", "LEASING.CREATE"),
        depends_on=("COMERCIAL", "CONTABILIDAD"),
        owns_schemas=("leasing_operativo",),
    ),
    ErpModule(
        code="CREDITO_COBRANZAS",
        name="Crédito y cobranzas",
        domain="financiero",
        icon="bi-shield-check",
        route_name="credito_cobranzas_hub",
        nav_module_key="CREDITO_COBRANZAS",
        permissions=("CREDITO.VIEW", "COBRANZA.VIEW", "COBRANZA.COLLECT"),
        depends_on=("COMERCIAL", "CONTABILIDAD"),
        owns_schemas=("credito_riesgo", "cuentas_por_cobrar"),
        description="Ciclo crédito → recuperación: riesgo, límites, CxC y cobranza.",
    ),
    ErpModule(
        code="CREDITO",
        name="Crédito y riesgo",
        domain="financiero",
        icon="bi-clipboard-data",
        route_name="credito_riesgo_dashboard",
        nav_module_key="CREDITO_RIESGO",
        depends_on=("COMERCIAL", "CREDITO_COBRANZAS"),
        owns_schemas=("credito_riesgo",),
    ),
    ErpModule(
        code="COBRANZA",
        name="Cobranza",
        domain="financiero",
        icon="bi-cash-stack",
        route_name="cobranza_resumen",
        nav_module_key="COBRANZA",
        permissions=("COBRANZA.VIEW", "COBRANZA.COLLECT"),
        depends_on=("COMERCIAL", "CONTABILIDAD", "CREDITO_COBRANZAS"),
        owns_schemas=("cuentas_por_cobrar",),
    ),
    ErpModule(
        code="CXP",
        name="Cuentas por pagar",
        domain="financiero",
        icon="bi-wallet2",
        route_name="cxp_lista",
        nav_module_key="FINANZAS",
        depends_on=("CONTABILIDAD",),
        owns_schemas=("fin.ap",),
    ),
    ErpModule(
        code="TESORERIA",
        name="Tesorería",
        domain="financiero",
        icon="bi-receipt-cutoff",
        route_name="tesoreria_home",
        nav_module_key="TESORERIA",
        permissions=("TESORERIA.VIEW", "TESORERIA.SII"),
        depends_on=("CONTABILIDAD",),
        owns_schemas=("fin.documento_tributario", "fin.sii_credencial", "fin.sii_ejecucion"),
        description="Libros de compra y venta. La actualización SII no contabiliza.",
    ),
    ErpModule(
        code="CONTABILIDAD",
        name="Contabilidad",
        domain="financiero",
        icon="bi-journal-richtext",
        route_name="contabilidad_plan_cuentas",
        nav_module_key="CONTABILIDAD",
        permissions=("CONTABILIDAD.VIEW", "CONTABILIDAD.POST", "CONTABILIDAD.CLOSE"),
        depends_on=("PLATFORM",),
        owns_schemas=("asientos_contables", "fin.plan_cuenta"),
        description="Único dueño de asientos. Otros módulos usan AccountingService.",
    ),
    ErpModule(
        code="INVENTARIO",
        name="Inventario",
        domain="operaciones",
        icon="bi-box-seam",
        route_name="productos_list",
        nav_module_key="OPERACIONES",
        permissions=("INVENTARIO.VIEW", "INVENTARIO.ADJUST"),
        depends_on=("PLATFORM",),
        owns_schemas=("productos", "inventario_movimientos"),
    ),
    ErpModule(
        code="TALLER",
        name="Taller",
        domain="operaciones",
        icon="bi-wrench-adjustable",
        route_name="taller_hub",
        nav_module_key="OPERACIONES",
        permissions=("TALLER.VIEW", "TALLER.CLOSE"),
        depends_on=("INVENTARIO",),
        owns_schemas=("orden_servicio",),
    ),
    ErpModule(
        code="TRANSPORTE",
        name="Transporte",
        domain="operaciones",
        icon="bi-signpost-split-fill",
        route_name="transporte_hub",
        nav_module_key="OPERACIONES",
        depends_on=("PLATFORM",),
        owns_schemas=("transporte_viaje",),
    ),
    ErpModule(
        code="RRHH",
        name="Recursos humanos",
        domain="rrhh",
        icon="bi-people-fill",
        route_name="remuneraciones_rrhh_dashboard",
        nav_module_key="RRHH",
        permissions=("RRHH.VIEW", "RRHH.PAYROLL", "RRHH.APPROVE"),
        depends_on=("CONTABILIDAD",),
        owns_schemas=("empleados", "remuneraciones"),
    ),
    ErpModule(
        code="ANALYTICS",
        name="Analytics",
        domain="analytics",
        icon="bi-graph-up",
        route_name="menu_principal",
        nav_module_key="PRINCIPAL",
        depends_on=("PLATFORM",),
        owns_schemas=("read_models",),
        description="Dashboards y reportes; no debe mutar tablas operacionales.",
    ),
)


def get_module(code: str) -> ErpModule | None:
    key = (code or "").strip().upper()
    for mod in ERP_MODULES:
        if mod.code == key:
            return mod
    return None


def modules_by_domain() -> dict[str, list[ErpModule]]:
    out: dict[str, list[ErpModule]] = {}
    for mod in ERP_MODULES:
        out.setdefault(mod.domain, []).append(mod)
    return out


def allowed_dependency(from_code: str, to_code: str) -> bool:
    """True si `from` puede depender de `to` según el registro (o to es PLATFORM)."""
    src = get_module(from_code)
    dst = get_module(to_code)
    if src is None or dst is None:
        return False
    if dst.code == "PLATFORM":
        return True
    if dst.code == src.code:
        return True
    return dst.code in src.depends_on
