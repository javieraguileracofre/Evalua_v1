# core/session_revalidate.py
# -*- coding: utf-8 -*-
from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from crud.auth.usuarios import get_usuario_por_id, serializar_sesion_usuario


def revalidar_auth_payload(db: Session, auth: dict[str, Any]) -> dict[str, Any] | None:
    """None = sesión inválida (usuario inexistente, inactivo o versión vieja)."""
    try:
        uid = int(auth.get("uid"))
    except (TypeError, ValueError):
        return None
    usuario = get_usuario_por_id(db, uid)
    if usuario is None or not usuario.activo:
        return None
    cookie_sv = auth.get("sv")
    try:
        cookie_sv_i = int(cookie_sv) if cookie_sv is not None else 1
    except (TypeError, ValueError):
        cookie_sv_i = 0
    db_sv = int(getattr(usuario, "session_version", 1) or 1)
    if cookie_sv_i != db_sv:
        return None
    visible = auth.get("visibleModules")
    if not isinstance(visible, list):
        visible = None
    from crud.auth import modulos_visibles as crud_modulos

    if visible is None:
        visible = crud_modulos.user_visible_modules_list(usuario, db)
    refreshed = serializar_sesion_usuario(usuario, visible_modules=list(visible))
    if "tenant_code" in auth:
        refreshed["tenant_code"] = auth.get("tenant_code")
    # Roles siempre desde BD (no desde cookie).
    return refreshed
