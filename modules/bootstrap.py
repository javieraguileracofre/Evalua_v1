# modules/bootstrap.py
# -*- coding: utf-8 -*-
"""Registra handlers de eventos entre módulos. Idempotente."""
from __future__ import annotations

import logging

from erp_platform.events import subscribe
from erp_platform.events import types as event_types

logger = logging.getLogger("evalua.modules.bootstrap")
_REGISTERED = False


def _on_venta_confirmada(event) -> None:
    """Punto de extensión: inventario/CxC/analytics pueden suscribirse aquí."""
    logger.info(
        "event=%s nota=%s",
        event.name,
        (event.payload or {}).get("nota_venta_id"),
    )


def _on_venta_anulada(event) -> None:
    logger.info(
        "event=%s nota=%s",
        event.name,
        (event.payload or {}).get("nota_venta_id"),
    )


def register_domain_handlers() -> None:
    global _REGISTERED
    if _REGISTERED:
        return
    subscribe(event_types.VENTA_CONFIRMADA, _on_venta_confirmada)
    subscribe(event_types.VENTA_ANULADA, _on_venta_anulada)
    _REGISTERED = True
    logger.info("Handlers de dominio ERP registrados.")
