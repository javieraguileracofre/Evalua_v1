# core/nav_visibility.py
# -*- coding: utf-8 -*-
"""Visibilidad de secciones del sidebar según módulos asignados al usuario."""
from __future__ import annotations

from typing import Any

from core.module_catalog import (
    ALL_ASSIGNABLE_KEYS,
    ALL_MODULE_KEYS,
    NAV_SUBMODULE_KEYS,
    default_visible_modules_for_roles,
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


def _submodulos_comercial_asignados(visible: frozenset[str]) -> frozenset[str]:
    return visible & frozenset(NAV_SUBMODULE_KEYS)


def usuario_puede_ver_submodulo_nav(auth: dict[str, Any] | None, submodule_key: str) -> bool:
    """
    Visibilidad de ítems bajo Comercial (leasing, crédito).
    Si el usuario tiene COMERCIAL pero ningún sub-módulo explícito, ve todos (retrocompat).
    """
    key = str(submodule_key or "").strip().upper()
    if not key:
        return False
    if usuario_es_admin(auth):
        return True
    visible = modulos_visibles_en_sesion(auth)
    if key in visible:
        return True
    subs = _submodulos_comercial_asignados(visible)
    if "COMERCIAL" in visible and not subs:
        return True
    return False


def usuario_puede_ver_modulo_nav(auth: dict[str, Any] | None, module_key: str) -> bool:
    key = str(module_key or "").strip().upper()
    if not key:
        return False
    return key in modulos_visibles_en_sesion(auth)
