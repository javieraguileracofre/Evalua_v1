# platform/permissions.py
# -*- coding: utf-8 -*-
"""
Permisos progresivos module.action (compatibles con roles actuales).

Migración: los guards existentes por rol siguen vigentes.
Los códigos PERMISSION_* permiten evolución sin romper ADMIN/OPERACIONES/etc.
"""
from __future__ import annotations

from typing import Any

from core.rbac import auth_roles, usuario_es_admin, usuario_tiene_rol

# Catálogo canónico (no implica que todos estén enforced aún).
LEASING_VIEW = "LEASING.VIEW"
LEASING_CREATE = "LEASING.CREATE"
LEASING_APPROVE = "LEASING.APPROVE"
CONTABILIDAD_VIEW = "CONTABILIDAD.VIEW"
CONTABILIDAD_POST = "CONTABILIDAD.POST"
CONTABILIDAD_CLOSE = "CONTABILIDAD.CLOSE"
RRHH_VIEW = "RRHH.VIEW"
RRHH_PAYROLL = "RRHH.PAYROLL"
RRHH_APPROVE = "RRHH.APPROVE"
COBRANZA_VIEW = "COBRANZA.VIEW"
COBRANZA_COLLECT = "COBRANZA.COLLECT"
INVENTARIO_VIEW = "INVENTARIO.VIEW"
INVENTARIO_ADJUST = "INVENTARIO.ADJUST"
TALLER_VIEW = "TALLER.VIEW"
TALLER_CLOSE = "TALLER.CLOSE"
ADMIN_USERS = "ADMIN.USERS"
ADMIN_BACKUPS = "ADMIN.BACKUPS"
ADMIN_AUDIT = "ADMIN.AUDIT"

# Mapeo progresivo rol → permisos (unión si el usuario tiene varios roles).
ROLE_PERMISSIONS: dict[str, frozenset[str]] = {
    "ADMIN": frozenset(
        {
            LEASING_VIEW,
            LEASING_CREATE,
            LEASING_APPROVE,
            CONTABILIDAD_VIEW,
            CONTABILIDAD_POST,
            CONTABILIDAD_CLOSE,
            RRHH_VIEW,
            RRHH_PAYROLL,
            RRHH_APPROVE,
            COBRANZA_VIEW,
            COBRANZA_COLLECT,
            INVENTARIO_VIEW,
            INVENTARIO_ADJUST,
            TALLER_VIEW,
            TALLER_CLOSE,
            ADMIN_USERS,
            ADMIN_BACKUPS,
            ADMIN_AUDIT,
        }
    ),
    "OPERACIONES": frozenset(
        {LEASING_VIEW, LEASING_CREATE, INVENTARIO_VIEW, INVENTARIO_ADJUST, TALLER_VIEW, TALLER_CLOSE}
    ),
    "FINANZAS": frozenset(
        {
            LEASING_VIEW,
            LEASING_APPROVE,
            CONTABILIDAD_VIEW,
            CONTABILIDAD_POST,
            CONTABILIDAD_CLOSE,
            COBRANZA_VIEW,
            COBRANZA_COLLECT,
            RRHH_APPROVE,
        }
    ),
    "RRHH": frozenset({RRHH_VIEW, RRHH_PAYROLL, RRHH_APPROVE}),
    "CONSULTA": frozenset(
        {LEASING_VIEW, CONTABILIDAD_VIEW, COBRANZA_VIEW, INVENTARIO_VIEW, TALLER_VIEW, RRHH_VIEW}
    ),
}


def permissions_for_auth(auth: dict[str, Any] | None) -> frozenset[str]:
    if usuario_es_admin(auth):
        return ROLE_PERMISSIONS["ADMIN"]
    out: set[str] = set()
    for role in auth_roles(auth):
        out |= ROLE_PERMISSIONS.get(str(role).upper(), frozenset())
    return frozenset(out)


def usuario_tiene_permiso(auth: dict[str, Any] | None, permission: str) -> bool:
    code = (permission or "").strip().upper()
    if not code:
        return False
    if usuario_es_admin(auth):
        return True
    return code in permissions_for_auth(auth)


def usuario_puede_modulo_accion(
    auth: dict[str, Any] | None,
    *,
    module_key: str,
    action: str,
) -> bool:
    """Compat: combina permiso canónico + rol legado cuando no hay mapping fino."""
    perm = f"{(module_key or '').strip().upper()}.{(action or '').strip().upper()}"
    if usuario_tiene_permiso(auth, perm):
        return True
    # Fallback legado mínimo
    if action.upper() == "VIEW" and usuario_tiene_rol(auth, "CONSULTA"):
        return True
    return False
