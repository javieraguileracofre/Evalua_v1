# core/public_errors.py
# -*- coding: utf-8 -*-
"""Mensajes de error seguros para el navegador (evita filtrar trazas SQL, rutas o stack)."""
from __future__ import annotations

import logging
import uuid
from typing import Any

logger = logging.getLogger("evalua.public_errors")

# Errores de dominio / validación pensados para mostrarse al usuario final.
_SAFE_MESSAGE_TYPES: tuple[type[BaseException], ...] = (ValueError, PermissionError)


def public_error_message(
    exc: BaseException,
    *,
    default: str | None = None,
) -> str:
    """
    Devuelve un texto apto para query params, flashes o plantillas.

    - En producción solo se expone el mensaje de excepciones de validación explícitas
      (p. ej. ValueError, PermissionError).
    - Cualquier otro error devuelve un mensaje genérico; el detalle debe ir al log.
    - En APP_ENV=development/local se añade tipo y mensaje breve para depuración.
    """
    from core.config import settings

    fallback = default or (
        "No se pudo completar la operación. Si persiste, contacte al administrador "
        "con la hora aproximada del intento."
    )
    if isinstance(exc, _SAFE_MESSAGE_TYPES):
        s = str(exc).strip()
        if not s:
            return fallback
        if len(s) > 500:
            return s[:497] + "..."
        return s
    if settings.is_dev:
        s = f"{type(exc).__name__}: {exc}".strip()
        if len(s) > 900:
            return s[:897] + "..."
        return s or fallback
    return fallback


def log_unhandled(
    context: str,
    exc: BaseException,
    *,
    extra: dict[str, Any] | None = None,
) -> str:
    """
    Registra el fallo con un id corto para correlación soporte ↔ logs.
    Devuelve el mismo id (para mostrarlo en HTML genérico 500).
    """
    err_id = uuid.uuid4().hex[:12]
    suffix = f" {extra!r}" if extra else ""
    logger.exception("%s [error_id=%s]%s", context, err_id, suffix, exc_info=exc)
    return err_id
