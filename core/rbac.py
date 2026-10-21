# core/rbac.py
# -*- coding: utf-8 -*-
"""Comprobaciones simples de roles sobre request.state.auth_user."""
from __future__ import annotations

from typing import Any
from urllib.parse import urlencode

from fastapi import HTTPException, Request, status
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


def _log_deny(request: Request, reason: str) -> None:
    from core.security_log import security_event

    auth = getattr(request, "state", None)
    auth_user = getattr(auth, "auth_user", None) if auth is not None else None
    path = ""
    try:
        path = str(request.url.path)
    except Exception:
        path = ""
    security_event("authz_denied", auth=auth_user if isinstance(auth_user, dict) else None, path=path, reason=reason)


def usuario_tiene_modulo_asignado(auth: dict[str, Any] | None, module_key: str) -> bool:
    """Enforcement server-side de visibleModules (ADMIN siempre pasa)."""
    if usuario_es_admin(auth):
        return True
    from core.module_catalog import NAV_SUBMODULE_KEYS
    from core.nav_visibility import usuario_puede_ver_modulo_nav, usuario_puede_ver_submodulo_nav

    key = (module_key or "").strip().upper()
    if key in NAV_SUBMODULE_KEYS:
        return usuario_puede_ver_submodulo_nav(auth, key)
    return usuario_puede_ver_modulo_nav(auth, key)


def usuario_tiene_algun_modulo(auth: dict[str, Any] | None, *module_keys: str) -> bool:
    if usuario_es_admin(auth):
        return True
    return any(usuario_tiene_modulo_asignado(auth, k) for k in module_keys if k)


def _redir_deny(request: Request, mensaje: str) -> RedirectResponse:
    _log_deny(request, mensaje)
    q = urlencode({"msg": mensaje, "sev": "danger"})
    return RedirectResponse(url=f"/?{q}", status_code=status.HTTP_303_SEE_OTHER)


def usuario_puede_gestionar_correo(auth: dict[str, Any] | None) -> bool:
    """Cuentas SMTP, canales de envío, validación y correos de prueba."""
    return usuario_es_admin(auth)


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
    if usuario_puede_consultar_modulos_finanzas(auth) and usuario_tiene_algun_modulo(
        auth, "FINANZAS", "CONTABILIDAD"
    ):
        return None
    msg = mensaje or (
        "No tiene permiso para ver este módulo financiero "
        "(se requiere rol Finanzas, Administrador o Consulta)."
    )
    return _redir_deny(request, msg)


def guard_finanzas_mutacion(
    request: Request,
    *,
    mensaje: str | None = None,
) -> RedirectResponse | None:
    auth = getattr(request.state, "auth_user", None)
    if usuario_puede_mutar_modulos_finanzas(auth) and usuario_tiene_algun_modulo(
        auth, "FINANZAS", "CONTABILIDAD"
    ):
        return None
    msg = mensaje or (
        "No tiene permiso para realizar esta acción "
        "(se requiere rol Finanzas o Administrador)."
    )
    return _redir_deny(request, msg)


def usuario_puede_ver_tesoreria(auth: dict[str, Any] | None) -> bool:
    """Consulta de libros de compra y venta."""
    return usuario_puede_consultar_modulos_finanzas(auth) and usuario_tiene_modulo_asignado(auth, "TESORERIA")


def usuario_puede_actualizar_sii(auth: dict[str, Any] | None) -> bool:
    """Disparar la descarga SII o guardar la clave tributaria."""
    return usuario_puede_mutar_modulos_finanzas(auth) and usuario_puede_ver_tesoreria(auth)


def guard_operacion_consulta(
    request: Request,
    *,
    mensaje: str | None = None,
) -> RedirectResponse | None:
    auth = getattr(request.state, "auth_user", None)
    if usuario_puede_consultar_modulos_operacion(auth) and usuario_tiene_algun_modulo(
        auth, "OPERACIONES", "COMERCIAL"
    ):
        return None
    msg = mensaje or (
        "No tiene permiso para ver este módulo operativo "
        "(se requiere rol Operaciones, Finanzas, Administrador o Consulta)."
    )
    return _redir_deny(request, msg)


def guard_operacion_mutacion(
    request: Request,
    *,
    mensaje: str | None = None,
) -> RedirectResponse | None:
    auth = getattr(request.state, "auth_user", None)
    if usuario_puede_mutar_modulos_operacion(auth) and usuario_tiene_algun_modulo(
        auth, "OPERACIONES", "COMERCIAL"
    ):
        return None
    msg = mensaje or (
        "No tiene permiso para realizar esta acción "
        "(se requiere rol Operaciones, Finanzas o Administrador)."
    )
    return _redir_deny(request, msg)


def usuario_puede_aprobar_leasing_financiero(auth: dict[str, Any] | None) -> bool:
    """Activación contable, aprobación formal y anulación de operaciones LF."""
    return usuario_es_admin(auth) or usuario_tiene_rol(auth, "FINANZAS")


def _usuario_puede_acceder_leasing_fin(auth: dict[str, Any] | None) -> bool:
    from core.nav_visibility import usuario_puede_ver_submodulo_nav

    if usuario_es_admin(auth):
        return True
    return usuario_puede_ver_submodulo_nav(auth, "LEASING_FINANCIERO")


def guard_leasing_fin_consulta(
    request: Request,
    *,
    mensaje: str | None = None,
) -> RedirectResponse | None:
    auth = getattr(request.state, "auth_user", None)
    if usuario_es_admin(auth):
        return None
    if not _usuario_puede_acceder_leasing_fin(auth) or not usuario_puede_consultar_modulos_operacion(auth):
        msg = mensaje or "No tiene permiso para acceder al módulo Leasing financiero."
        return _redir_deny(request, msg)
    return None


def guard_leasing_fin_mutacion(
    request: Request,
    *,
    mensaje: str | None = None,
) -> RedirectResponse | None:
    auth = getattr(request.state, "auth_user", None)
    if usuario_es_admin(auth):
        return None
    if not _usuario_puede_acceder_leasing_fin(auth) or not usuario_puede_mutar_modulos_operacion(auth):
        msg = mensaje or "No tiene permiso para modificar Leasing financiero."
        return _redir_deny(request, msg)
    return None


def guard_leasing_fin_aprobar(
    request: Request,
    *,
    mensaje: str | None = None,
) -> RedirectResponse | None:
    auth = getattr(request.state, "auth_user", None)
    if usuario_puede_aprobar_leasing_financiero(auth):
        return None
    msg = mensaje or (
        "No tiene permiso para aprobar o activar operaciones de leasing "
        "(se requiere rol Finanzas o Administrador)."
    )
    return _redir_deny(request, msg)


def _usuario_puede_acceder_credito_riesgo(auth: dict[str, Any] | None) -> bool:
    """Crédito y riesgo: submódulo (padre sin hijos ⇒ todos, vía nav_visibility)."""
    return usuario_tiene_modulo_asignado(auth, "CREDITO_RIESGO")


def _usuario_puede_acceder_cobranza(auth: dict[str, Any] | None) -> bool:
    """Cobranza: submódulo o Finanzas/Contabilidad si aún no tiene el área nueva."""
    if usuario_tiene_modulo_asignado(auth, "COBRANZA"):
        return True
    from core.module_catalog import NAV_CREDITO_COBRANZAS_SUBMODULE_KEYS
    from core.nav_visibility import modulos_visibles_en_sesion

    visible = modulos_visibles_en_sesion(auth)
    if visible & frozenset(("CREDITO_COBRANZAS", *NAV_CREDITO_COBRANZAS_SUBMODULE_KEYS)):
        return False
    return usuario_tiene_algun_modulo(auth, "FINANZAS", "CONTABILIDAD")


def guard_credito_riesgo_consulta(
    request: Request,
    *,
    mensaje: str | None = None,
) -> RedirectResponse | None:
    auth = getattr(request.state, "auth_user", None)
    if usuario_puede_consultar_modulos_operacion(auth) and _usuario_puede_acceder_credito_riesgo(auth):
        return None
    return _redir_deny(
        request,
        mensaje or "No tiene permiso para consultar Crédito y riesgo.",
    )


def guard_credito_riesgo_mutacion(
    request: Request,
    *,
    mensaje: str | None = None,
) -> RedirectResponse | None:
    auth = getattr(request.state, "auth_user", None)
    if usuario_puede_mutar_modulos_operacion(auth) and _usuario_puede_acceder_credito_riesgo(auth):
        return None
    return _redir_deny(
        request,
        mensaje or "No tiene permiso para modificar Crédito y riesgo.",
    )


def guard_credito_riesgo_aprobar(
    request: Request,
    *,
    mensaje: str | None = None,
) -> RedirectResponse | None:
    auth = getattr(request.state, "auth_user", None)
    if usuario_puede_aprobar_leasing_financiero(auth) and _usuario_puede_acceder_credito_riesgo(auth):
        return None
    return _redir_deny(
        request,
        mensaje or "No tiene permiso para aprobar o rechazar crédito (Finanzas o Administrador).",
    )


def guard_cobranza_consulta(
    request: Request,
    *,
    mensaje: str | None = None,
) -> RedirectResponse | None:
    auth = getattr(request.state, "auth_user", None)
    if usuario_puede_consultar_modulos_finanzas(auth) and _usuario_puede_acceder_cobranza(auth):
        return None
    msg = mensaje or (
        "No tiene permiso para consultar Cobranza "
        "(se requiere rol Finanzas, Administrador o Consulta)."
    )
    return _redir_deny(request, msg)


def guard_cobranza_mutacion(
    request: Request,
    *,
    mensaje: str | None = None,
) -> RedirectResponse | None:
    auth = getattr(request.state, "auth_user", None)
    if usuario_puede_mutar_modulos_finanzas(auth) and _usuario_puede_acceder_cobranza(auth):
        return None
    msg = mensaje or (
        "No tiene permiso para gestionar Cobranza "
        "(se requiere rol Finanzas o Administrador)."
    )
    return _redir_deny(request, msg)


def guard_credito_cobranzas_hub(
    request: Request,
    *,
    mensaje: str | None = None,
) -> RedirectResponse | None:
    """Hub del módulo: basta con ver crédito, cobranza o el área padre."""
    auth = getattr(request.state, "auth_user", None)
    if usuario_es_admin(auth):
        return None
    puede_area = usuario_tiene_algun_modulo(auth, "CREDITO_COBRANZAS") or _usuario_puede_acceder_credito_riesgo(
        auth
    ) or _usuario_puede_acceder_cobranza(auth)
    if puede_area and (
        usuario_puede_consultar_modulos_operacion(auth) or usuario_puede_consultar_modulos_finanzas(auth)
    ):
        return None
    return _redir_deny(
        request,
        mensaje or "No tiene permiso para acceder a Crédito y cobranzas.",
    )


def guard_transporte_consulta(
    request: Request,
    *,
    mensaje: str | None = None,
) -> RedirectResponse | None:
    auth = getattr(request.state, "auth_user", None)
    if usuario_puede_consultar_modulos_operacion(auth) and usuario_tiene_algun_modulo(
        auth, "OPERACIONES", "COMERCIAL"
    ):
        return None
    return _redir_deny(request, mensaje or "No tiene permiso para consultar Transporte.")


def guard_transporte_mutacion(
    request: Request,
    *,
    mensaje: str | None = None,
) -> RedirectResponse | None:
    auth = getattr(request.state, "auth_user", None)
    if usuario_puede_mutar_modulos_operacion(auth) and usuario_tiene_algun_modulo(auth, "OPERACIONES", "COMERCIAL"):
        return None
    return _redir_deny(request, mensaje or "No tiene permiso para modificar Transporte.")


def guard_leasing_op_consulta(
    request: Request,
    *,
    mensaje: str | None = None,
) -> RedirectResponse | None:
    auth = getattr(request.state, "auth_user", None)
    from core.nav_visibility import usuario_puede_ver_submodulo_nav

    if usuario_es_admin(auth) or (
        usuario_puede_consultar_modulos_operacion(auth) and usuario_puede_ver_submodulo_nav(auth, "LEASING_OPERATIVO")
    ):
        return None
    return _redir_deny(request, mensaje or "No tiene permiso para consultar Leasing operativo.")


def guard_leasing_op_mutacion(
    request: Request,
    *,
    mensaje: str | None = None,
) -> RedirectResponse | None:
    """Alta, edición y eliminación de cotizaciones/operaciones LOP."""
    auth = getattr(request.state, "auth_user", None)
    from core.nav_visibility import usuario_puede_ver_submodulo_nav

    if usuario_es_admin(auth):
        return None
    if usuario_puede_mutar_modulos_operacion(auth) and usuario_puede_ver_submodulo_nav(auth, "LEASING_OPERATIVO"):
        return None
    return _redir_deny(
        request,
        mensaje or "No tiene permiso para modificar cotizaciones de leasing operativo.",
    )


def require_leasing_fin_consulta_api(request: Request) -> None:
    redir = guard_leasing_fin_consulta(request)
    if redir is not None:
        _log_deny(request, "lf_api_consulta")
        raise HTTPException(status_code=403, detail="Sin permiso para consultar leasing financiero.")


def require_leasing_fin_mutacion_api(request: Request) -> None:
    redir = guard_leasing_fin_mutacion(request)
    if redir is not None:
        _log_deny(request, "lf_api_mutacion")
        raise HTTPException(status_code=403, detail="Sin permiso para modificar leasing financiero.")


def usuario_puede_ver_kpis_financieros(auth: dict[str, Any] | None) -> bool:
    """Portada: cifras de ventas/CxP solo Finanzas o Admin."""
    return usuario_es_admin(auth) or usuario_tiene_rol(auth, "FINANZAS")
