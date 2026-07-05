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

# Sub-módulos del área comercial (nav granular).
NAV_SUBMODULE_KEYS: tuple[str, ...] = (
    "LEASING_FINANCIERO",
    "LEASING_OPERATIVO",
    "CREDITO_RIESGO",
)

ALL_ASSIGNABLE_KEYS: tuple[str, ...] = ALL_MODULE_KEYS + NAV_SUBMODULE_KEYS

MODULE_LABELS: dict[str, str] = {
    "PRINCIPAL": "Inicio",
    "COMERCIAL": "Comercial y clientes",
    "OPERACIONES": "Operaciones",
    "RRHH": "Recursos humanos",
    "FINANZAS": "Finanzas",
    "CONTABILIDAD": "Contabilidad",
    "ADMINISTRACION": "Administración",
}

SUBMODULE_LABELS: dict[str, str] = {
    "LEASING_FINANCIERO": "Leasing financiero",
    "LEASING_OPERATIVO": "Leasing operativo",
    "CREDITO_RIESGO": "Crédito y riesgo",
}

_COMERCIAL_SUBS = frozenset(NAV_SUBMODULE_KEYS)

ROLE_DEFAULT_VISIBLE_MODULES: dict[str, frozenset[str]] = {
    "ADMIN": frozenset(ALL_ASSIGNABLE_KEYS),
    "OPERACIONES": frozenset({"PRINCIPAL", "COMERCIAL", "OPERACIONES", *_COMERCIAL_SUBS}),
    "FINANZAS": frozenset({"PRINCIPAL", "COMERCIAL", "FINANZAS", "CONTABILIDAD", *_COMERCIAL_SUBS}),
    "RRHH": frozenset({"PRINCIPAL", "RRHH"}),
    "CONSULTA": frozenset(
        {"PRINCIPAL", "COMERCIAL", "OPERACIONES", "FINANZAS", "CONTABILIDAD", *_COMERCIAL_SUBS}
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
    if "PRINCIPAL" not in out and out - {"ADMINISTRACION"}:
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
