# core/module_catalog.py
# -*- coding: utf-8 -*-
"""Catálogo de módulos del menú lateral y defaults por rol.

La fuente declarativa de bounded contexts vive en `erp_platform.registry`.
Este módulo conserva las claves de navegación usadas por Jinja/RBAC.
"""
from __future__ import annotations


ALL_MODULE_KEYS: tuple[str, ...] = (
    "PRINCIPAL",
    "COMERCIAL",
    "OPERACIONES",
    "RRHH",
    "CREDITO_COBRANZAS",
    "FINANZAS",
    "TESORERIA",
    "CONTABILIDAD",
    "ADMINISTRACION",
    "EMPRESAS",
)

# Sub-módulos con padre explícito (visibilidad granular en el sidebar).
NAV_COMERCIAL_SUBMODULE_KEYS: tuple[str, ...] = (
    "LEASING_FINANCIERO",
    "LEASING_OPERATIVO",
)

NAV_CREDITO_COBRANZAS_SUBMODULE_KEYS: tuple[str, ...] = (
    "CREDITO_RIESGO",
    "COBRANZA",
)

NAV_SUBMODULE_KEYS: tuple[str, ...] = (
    NAV_COMERCIAL_SUBMODULE_KEYS + NAV_CREDITO_COBRANZAS_SUBMODULE_KEYS
)

# Padre de cada submódulo (retrocompat: padre sin hijos explícitos ⇒ ve todos).
SUBMODULE_PARENT: dict[str, str] = {
    "LEASING_FINANCIERO": "COMERCIAL",
    "LEASING_OPERATIVO": "COMERCIAL",
    "CREDITO_RIESGO": "CREDITO_COBRANZAS",
    "COBRANZA": "CREDITO_COBRANZAS",
}

ALL_ASSIGNABLE_KEYS: tuple[str, ...] = ALL_MODULE_KEYS + NAV_SUBMODULE_KEYS

MODULE_LABELS: dict[str, str] = {
    "PRINCIPAL": "Inicio",
    "COMERCIAL": "Comercial y clientes",
    "OPERACIONES": "Operaciones",
    "RRHH": "Recursos humanos",
    "CREDITO_COBRANZAS": "Crédito y cobranzas",
    "FINANZAS": "Finanzas",
    "TESORERIA": "Tesorería",
    "CONTABILIDAD": "Contabilidad",
    "ADMINISTRACION": "Administración",
    "EMPRESAS": "Empresas",
}

SUBMODULE_LABELS: dict[str, str] = {
    "LEASING_FINANCIERO": "Leasing financiero",
    "LEASING_OPERATIVO": "Leasing operativo",
    "CREDITO_RIESGO": "Crédito y riesgo",
    "COBRANZA": "Cobranza",
}

_COMERCIAL_SUBS = frozenset(NAV_COMERCIAL_SUBMODULE_KEYS)
_CREDITO_COBRANZAS_SUBS = frozenset(NAV_CREDITO_COBRANZAS_SUBMODULE_KEYS)

ROLE_DEFAULT_VISIBLE_MODULES: dict[str, frozenset[str]] = {
    "ADMIN": frozenset(ALL_ASSIGNABLE_KEYS),
    "OPERACIONES": frozenset(
        {
            "PRINCIPAL",
            "COMERCIAL",
            "OPERACIONES",
            "CREDITO_COBRANZAS",
            *_COMERCIAL_SUBS,
            *_CREDITO_COBRANZAS_SUBS,
        }
    ),
    "FINANZAS": frozenset(
        {
            "PRINCIPAL",
            "COMERCIAL",
            "CREDITO_COBRANZAS",
            "FINANZAS",
            "TESORERIA",
            "CONTABILIDAD",
            *_COMERCIAL_SUBS,
            *_CREDITO_COBRANZAS_SUBS,
        }
    ),
    "RRHH": frozenset({"PRINCIPAL", "RRHH"}),
    "CONSULTA": frozenset(
        {
            "PRINCIPAL",
            "COMERCIAL",
            "OPERACIONES",
            "CREDITO_COBRANZAS",
            "FINANZAS",
            "TESORERIA",
            "CONTABILIDAD",
            *_COMERCIAL_SUBS,
            *_CREDITO_COBRANZAS_SUBS,
        }
    ),
}


def default_visible_modules_for_roles(role_codes: list[str] | set[str]) -> frozenset[str]:
    """Unión de módulos sugeridos según los roles del usuario."""
    out: set[str] = set()
    for raw in role_codes:
        code = str(raw or "").strip().upper()
        if not code:
            continue
        out |= ROLE_DEFAULT_VISIBLE_MODULES.get(code, frozenset())
    if not out:
        return frozenset({"PRINCIPAL"})
    if "PRINCIPAL" not in out and out - {"ADMINISTRACION", "EMPRESAS"}:
        out.add("PRINCIPAL")
    return frozenset(out)


def normalize_module_keys(keys: list[str]) -> list[str]:
    return normalize_assignable_module_keys(keys)


def normalize_assignable_module_keys(keys: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    valid = set(ALL_ASSIGNABLE_KEYS)
    for raw in keys:
        key = str(raw or "").strip().upper()
        if not key or key in seen or key not in valid:
            continue
        seen.add(key)
        out.append(key)
    return out


def module_label(key: str) -> str:
    k = str(key or "").strip().upper()
    return SUBMODULE_LABELS.get(k) or MODULE_LABELS.get(k) or k


def siblings_of_submodule(submodule_key: str) -> frozenset[str]:
    parent = SUBMODULE_PARENT.get(str(submodule_key or "").strip().upper())
    if not parent:
        return frozenset()
    return frozenset(k for k, p in SUBMODULE_PARENT.items() if p == parent)
