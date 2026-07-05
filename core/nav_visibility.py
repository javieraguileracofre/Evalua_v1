# core/nav_visibility.py
# -*- coding: utf-8 -*-
"""Visibilidad de secciones del sidebar según módulos asignados al usuario."""
from __future__ import annotations

from typing import Any

from core.module_catalog import ALL_MODULE_KEYS, default_visible_modules_for_roles
from core.rbac import auth_roles, usuario_es_admin


def modulos_visibles_en_sesion(auth: dict[str, Any] | None) -> frozenset[str]:
    """Módulos efectivos para filtrar el menú (sesión o defaults por rol)."""
    if not isinstance(auth, dict):
        return frozenset()
    if usuario_es_admin(auth):
        return frozenset(ALL_MODULE_KEYS)
    raw = auth.get("visibleModules")
    if isinstance(raw, list) and raw:
        return frozenset(str(k).strip().upper() for k in raw if k)
    return default_visible_modules_for_roles(auth_roles(auth))


def usuario_puede_ver_modulo_nav(auth: dict[str, Any] | None, module_key: str) -> bool:
    key = str(module_key or "").strip().upper()
    if not key:
        return False
    return key in modulos_visibles_en_sesion(auth)
