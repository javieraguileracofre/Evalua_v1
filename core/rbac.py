# core/rbac.py
# -*- coding: utf-8 -*-
"""Comprobaciones simples de roles sobre request.state.auth_user."""
from __future__ import annotations

from typing import Any
from urllib.parse import urlencode

from fastapi import Request, status
from fastapi.responses import RedirectResponse


def auth_roles(auth: dict[str, Any] | None) -> list[str]:
    if not isinstance(auth, dict):
        return []
    raw = auth.get("roles")
    if not isinstance(raw, list):
        return []
    return [str(x) for x in raw if x is not None and str(x).strip()]


def usuario_tiene_rol(auth: dict[str, Any] | None, codigo: str) -> bool:
    c = (codigo or "").strip()
    if not c:
        return False
    return c in auth_roles(auth)


def usuario_es_admin(auth: dict[str, Any] | None) -> bool:
    return usuario_tiene_rol(auth, "ADMIN")


def usuario_puede_consultar_modulos_finanzas(auth: dict[str, Any] | None) -> bool:
    """Listados, detalle e informes (incluye rol CONSULTA del seed)."""
    return usuario_es_admin(auth) or usuario_tiene_rol(auth, "FINANZAS") or usuario_tiene_rol(auth, "CONSULTA")


def usuario_puede_mutar_modulos_finanzas(auth: dict[str, Any] | None) -> bool:
    """Alta, edición, pagos, asientos y demás POST en módulos financieros."""
    return usuario_es_admin(auth) or usuario_tiene_rol(auth, "FINANZAS")


def guard_finanzas_consulta(
    request: Request,
    *,
    mensaje: str | None = None,
) -> RedirectResponse | None:
    auth = getattr(request.state, "auth_user", None)
    if usuario_puede_consultar_modulos_finanzas(auth):
        return None
    msg = mensaje or (
        "No tiene permiso para ver este módulo financiero "
        "(se requiere rol Finanzas, Administrador o Consulta)."
    )
    q = urlencode({"msg": msg, "sev": "danger"})
    return RedirectResponse(url=f"/?{q}", status_code=status.HTTP_303_SEE_OTHER)


def guard_finanzas_mutacion(
    request: Request,
    *,
    mensaje: str | None = None,
) -> RedirectResponse | None:
    auth = getattr(request.state, "auth_user", None)
    if usuario_puede_mutar_modulos_finanzas(auth):
        return None
    msg = mensaje or (
        "No tiene permiso para realizar esta acción "
        "(se requiere rol Finanzas o Administrador)."
    )
    q = urlencode({"msg": msg, "sev": "danger"})
    return RedirectResponse(url=f"/?{q}", status_code=status.HTTP_303_SEE_OTHER)
