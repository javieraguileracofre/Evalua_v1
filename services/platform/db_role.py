# services/platform/db_role.py
# -*- coding: utf-8 -*-
"""Criterio de separación entre rol de aplicación y rol migrador."""
from __future__ import annotations


def app_role_is_safe(*, can_create: bool, can_insert: bool) -> tuple[bool, str]:
    """
    El rol de runtime puede escribir filas y no puede crear objetos.

    `can_create` corresponde a CREATE sobre el schema public.
    `can_insert` corresponde a INSERT sobre una tabla operativa.
    """
    if can_create:
        return False, "El rol de aplicación no debe tener CREATE sobre el schema public."
    if not can_insert:
        return False, "El rol de aplicación debe poder INSERT en tablas operativas."
    return True, "Rol de aplicación sin DDL y con DML."
