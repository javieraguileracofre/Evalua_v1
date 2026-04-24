# core/auth_paths.py
# -*- coding: utf-8 -*-
"""Rutas que no requieren sesión autenticada."""
from __future__ import annotations

from core.config import Settings


def is_public_path(path: str, settings: Settings) -> bool:
    """True si el middleware no debe exigir login."""
    # "/" la resuelve `menu_principal`: invitados ven login; usuarios autenticados, el panel.
    if path in ("/health", "/favicon.ico", "/"):
        return True
    if path.startswith("/static/"):
        return True
    if path == "/login" or path.startswith("/login/"):
        return True
    if settings.is_dev:
        if path in ("/docs", "/redoc", "/openapi.json"):
            return True
        if path.startswith("/docs") or path.startswith("/redoc"):
            return True
    else:
        # En producción la documentación OpenAPI suele estar desactivada: dejar que la app responda 404 sin login.
        if path in ("/docs", "/redoc", "/openapi.json"):
            return True
    return False
