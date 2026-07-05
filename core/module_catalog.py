# core/module_catalog.py
# -*- coding: utf-8 -*-
"""Catálogo de módulos del menú lateral y defaults por rol."""
from __future__ import annotations

ALL_MODULE_KEYS: tuple[str, ...] = (
    "PRINCIPAL",
    "COMERCIAL",
    "OPERACIONES",
    "RRHH",
    "FINANZAS",
    "CONTABILIDAD",
    "ADMINISTRACION",
)

MODULE_LABELS: dict[str, str] = {
    "PRINCIPAL": "Inicio",
    "COMERCIAL": "Comercial y clientes",
    "OPERACIONES": "Operaciones",
    "RRHH": "Recursos humanos",
    "FINANZAS": "Finanzas",
    "CONTABILIDAD": "Contabilidad",
    "ADMINISTRACION": "Administración",
}

ROLE_DEFAULT_VISIBLE_MODULES: dict[str, frozenset[str]] = {
    "ADMIN": frozenset(ALL_MODULE_KEYS),
    "OPERACIONES": frozenset({"PRINCIPAL", "COMERCIAL", "OPERACIONES"}),
    "FINANZAS": frozenset({"PRINCIPAL", "COMERCIAL", "FINANZAS", "CONTABILIDAD"}),
    "RRHH": frozenset({"PRINCIPAL", "RRHH"}),
    "CONSULTA": frozenset({"PRINCIPAL", "COMERCIAL", "OPERACIONES", "FINANZAS", "CONTABILIDAD"}),
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
    if "PRINCIPAL" not in out and out - {"ADMINISTRACION"}:
        out.add("PRINCIPAL")
    return frozenset(out)


def normalize_module_keys(keys: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    valid = set(ALL_MODULE_KEYS)
    for raw in keys:
        key = str(raw or "").strip().upper()
        if not key or key in seen or key not in valid:
            continue
        seen.add(key)
        out.append(key)
    return out
