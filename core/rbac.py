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


def usuario_puede_consultar_modulos_operacion(auth: dict[str, Any] | None) -> bool:
    """Consulta de módulos comerciales/operativos."""
    return (
        usuario_es_admin(auth)
        or usuario_tiene_rol(auth, "OPERACIONES")
        or usuario_tiene_rol(auth, "FINANZAS")
        or usuario_tiene_rol(auth, "CONSULTA")
    )


def usuario_puede_mutar_modulos_operacion(auth: dict[str, Any] | None) -> bool:
    """Mutaciones en ventas, inventario y módulos operativos."""
    return (
        usuario_es_admin(auth)
        or usuario_tiene_rol(auth, "OPERACIONES")
        or usuario_tiene_rol(auth, "FINANZAS")
    )


def usuario_puede_consultar_remuneraciones(auth: dict[str, Any] | None) -> bool:
    return (
        usuario_es_admin(auth)
        or usuario_tiene_rol(auth, "RRHH")
        or usuario_tiene_rol(auth, "FINANZAS")
        or usuario_tiene_rol(auth, "CONSULTA")
    )


def usuario_puede_calcular_remuneraciones(auth: dict[str, Any] | None) -> bool:
    return usuario_es_admin(auth) or usuario_tiene_rol(auth, "RRHH")


def usuario_puede_gestionar_contratos_laborales(auth: dict[str, Any] | None) -> bool:
    return usuario_es_admin(auth) or usuario_tiene_rol(auth, "RRHH")


def usuario_puede_aprobar_remuneraciones_rrhh(auth: dict[str, Any] | None) -> bool:
    return usuario_es_admin(auth) or usuario_tiene_rol(auth, "RRHH")


def usuario_puede_aprobar_remuneraciones_finanzas(auth: dict[str, Any] | None) -> bool:
    return usuario_es_admin(auth) or usuario_tiene_rol(auth, "FINANZAS")


def usuario_puede_cerrar_o_pagar_remuneraciones(auth: dict[str, Any] | None) -> bool:
    return usuario_es_admin(auth) or usuario_tiene_rol(auth, "FINANZAS")


def usuario_puede_anular_remuneraciones(auth: dict[str, Any] | None) -> bool:
    return usuario_es_admin(auth) or usuario_tiene_rol(auth, "RRHH") or usuario_tiene_rol(auth, "FINANZAS")


def guard_remuneraciones_consulta(
    request: Request,
    *,
    mensaje: str | None = None,
) -> RedirectResponse | None:
    auth = getattr(request.state, "auth_user", None)
    if usuario_puede_consultar_remuneraciones(auth):
        return None
    msg = mensaje or (
        "No tiene permiso para ver remuneraciones "
        "(se requiere rol Administrador, RRHH, Finanzas o Consulta)."
    )
    q = urlencode({"msg": msg, "sev": "danger"})
    return RedirectResponse(url=f"/?{q}", status_code=status.HTTP_303_SEE_OTHER)


def guard_remuneraciones_calcular(
    request: Request,
    *,
    mensaje: str | None = None,
) -> RedirectResponse | None:
    auth = getattr(request.state, "auth_user", None)
    if usuario_puede_calcular_remuneraciones(auth):
        return None
    msg = mensaje or "No tiene permiso para calcular remuneraciones (Administrador o RRHH)."
    q = urlencode({"msg": msg, "sev": "danger"})
    return RedirectResponse(url=f"/?{q}", status_code=status.HTTP_303_SEE_OTHER)


def guard_remuneraciones_aprobacion_rrhh(
    request: Request,
    *,
    mensaje: str | None = None,
) -> RedirectResponse | None:
    auth = getattr(request.state, "auth_user", None)
    if usuario_puede_aprobar_remuneraciones_rrhh(auth):
        return None
    msg = mensaje or "No tiene permiso para aprobar como RRHH."
    q = urlencode({"msg": msg, "sev": "danger"})
    return RedirectResponse(url=f"/?{q}", status_code=status.HTTP_303_SEE_OTHER)


def guard_remuneraciones_aprobacion_finanzas(
    request: Request,
    *,
    mensaje: str | None = None,
) -> RedirectResponse | None:
    auth = getattr(request.state, "auth_user", None)
    if usuario_puede_aprobar_remuneraciones_finanzas(auth):
        return None
    msg = mensaje or "No tiene permiso para aprobar como Finanzas."
    q = urlencode({"msg": msg, "sev": "danger"})
    return RedirectResponse(url=f"/?{q}", status_code=status.HTTP_303_SEE_OTHER)


def guard_remuneraciones_cerrar_pagar(
    request: Request,
    *,
    mensaje: str | None = None,
) -> RedirectResponse | None:
    auth = getattr(request.state, "auth_user", None)
    if usuario_puede_cerrar_o_pagar_remuneraciones(auth):
        return None
    msg = mensaje or "No tiene permiso para cerrar o marcar pagada la nómina (Administrador o Finanzas)."
    q = urlencode({"msg": msg, "sev": "danger"})
    return RedirectResponse(url=f"/?{q}", status_code=status.HTTP_303_SEE_OTHER)


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


def guard_operacion_consulta(
    request: Request,
    *,
    mensaje: str | None = None,
) -> RedirectResponse | None:
    auth = getattr(request.state, "auth_user", None)
    if usuario_puede_consultar_modulos_operacion(auth):
        return None
    msg = mensaje or (
        "No tiene permiso para ver este módulo operativo "
        "(se requiere rol Operaciones, Finanzas, Administrador o Consulta)."
    )
    q = urlencode({"msg": msg, "sev": "danger"})
    return RedirectResponse(url=f"/?{q}", status_code=status.HTTP_303_SEE_OTHER)


def guard_operacion_mutacion(
    request: Request,
    *,
    mensaje: str | None = None,
) -> RedirectResponse | None:
    auth = getattr(request.state, "auth_user", None)
    if usuario_puede_mutar_modulos_operacion(auth):
        return None
    msg = mensaje or (
        "No tiene permiso para realizar esta acción "
        "(se requiere rol Operaciones, Finanzas o Administrador)."
    )
    q = urlencode({"msg": msg, "sev": "danger"})
    return RedirectResponse(url=f"/?{q}", status_code=status.HTTP_303_SEE_OTHER)
