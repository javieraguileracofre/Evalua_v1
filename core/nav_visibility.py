# core/nav_visibility.py
# -*- coding: utf-8 -*-
"""Visibilidad de secciones del sidebar según módulos asignados al usuario."""
from __future__ import annotations

from typing import Any

from core.module_catalog import (
    ALL_ASSIGNABLE_KEYS,
    ALL_MODULE_KEYS,
    NAV_CREDITO_COBRANZAS_SUBMODULE_KEYS,
    NAV_SUBMODULE_KEYS,
    SUBMODULE_PARENT,
    default_visible_modules_for_roles,
    siblings_of_submodule,
)
from core.rbac import auth_roles, usuario_es_admin


def modulos_visibles_en_sesion(auth: dict[str, Any] | None) -> frozenset[str]:
    """Módulos efectivos para filtrar el menú (sesión o defaults por rol)."""
    if not isinstance(auth, dict):
        return frozenset()
    if usuario_es_admin(auth):
        return frozenset(ALL_ASSIGNABLE_KEYS)
    raw = auth.get("visibleModules")
    if isinstance(raw, list) and raw:
        return frozenset(str(k).strip().upper() for k in raw if k)
    return default_visible_modules_for_roles(auth_roles(auth))


def usuario_puede_ver_submodulo_nav(auth: dict[str, Any] | None, submodule_key: str) -> bool:
    """
    Visibilidad de submódulos (leasing bajo Comercial; crédito/cobranza bajo Crédito y cobranzas).
    Si el usuario tiene el padre pero ningún hijo explícito de ese padre, ve todos (retrocompat).
    """
    key = str(submodule_key or "").strip().upper()
    if not key or key not in NAV_SUBMODULE_KEYS:
        return False
    if usuario_es_admin(auth):
        return True
    visible = modulos_visibles_en_sesion(auth)
    if key in visible:
        return True
    parent = SUBMODULE_PARENT.get(key)
    if not parent:
        return False
    siblings = siblings_of_submodule(key)
    if parent in visible and not (visible & siblings):
        return True
    return False


def usuario_puede_ver_modulo_nav(auth: dict[str, Any] | None, module_key: str) -> bool:
    key = str(module_key or "").strip().upper()
    if not key:
        return False
    if usuario_es_admin(auth):
        return key in ALL_ASSIGNABLE_KEYS or key in ALL_MODULE_KEYS
    visible = modulos_visibles_en_sesion(auth)
    if key in visible:
        return True
    # Sección visible si solo hay hijos asignados (usuarios legacy con CREDITO_RIESGO / COBRANZA).
    if key == "CREDITO_COBRANZAS":
        return bool(visible & frozenset(NAV_CREDITO_COBRANZAS_SUBMODULE_KEYS))
    return False
