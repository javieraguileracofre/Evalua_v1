# routes/api/v1/deps.py
# -*- coding: utf-8 -*-
"""Dependencias compartidas del contrato HTTP /api/v1."""
from __future__ import annotations

from typing import Any, Callable

from fastapi import Depends, HTTPException, Request

from erp_platform.permissions import usuario_tiene_permiso


def require_authenticated(request: Request) -> dict[str, Any]:
    auth = getattr(request.state, "auth_user", None)
    if not auth:
        raise HTTPException(status_code=401, detail="Autenticación requerida.")
    if isinstance(auth, dict):
        return auth
    return {"id": getattr(auth, "id", None)}


def require_permission(permission: str) -> Callable[[dict[str, Any]], dict[str, Any]]:
    """Factory: exige autenticación + permiso canónico (p. ej. CONTABILIDAD.VIEW)."""

    def _dep(auth: dict[str, Any] = Depends(require_authenticated)) -> dict[str, Any]:
        if not usuario_tiene_permiso(auth, permission):
            raise HTTPException(status_code=403, detail="Permiso insuficiente.")
        return auth

    return _dep
