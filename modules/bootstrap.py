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


def _on_contrato_activado(event) -> None:
    payload = event.payload or {}
    logger.info(
        "event=%s producto=%s cotizacion_id=%s contrato_id=%s asiento_id=%s",
        event.name,
        payload.get("producto"),
        payload.get("cotizacion_id"),
        payload.get("contrato_id"),
        payload.get("asiento_id"),
    )


def _audit_handler(event, action: str, module: str, entity: str, entity_key: str) -> None:
    from erp_platform.events.outbox import get_dispatch_session
    from services.audit.financial import audit_financial_fact

    db = get_dispatch_session()
    payload = event.payload or {}
    if db is None:
        logger.info("event=%s sin sesión de despacho", event.name)
        return
    audit_financial_fact(
        db,
        action=action,
        module=module,
        entity=entity,
        entity_id=payload.get(entity_key),
        actor_id=getattr(event, "actor_id", None),
        company_id=getattr(event, "company_id", None),
        detail={"event": event.name},
    )


def _on_pago_realizado(event) -> None:
    """Efecto: sincroniza la cuota LOP si el pago saldó una CxC de leasing."""
    payload = event.payload or {}
    cxc_id = payload.get("cuenta_cobrar_id")
    from erp_platform.events.outbox import get_dispatch_session

    db = get_dispatch_session()
    if db is not None and cxc_id:
        from services.leasing_operativo_contabilidad import sincronizar_cobranza_lop

        sincronizar_cobranza_lop(db, int(cxc_id), usuario="outbox")
    _audit_handler(event, "PAGO_REALIZADO", "cobranza", "pago", "pago_id")


def _on_cuota_pagada(event) -> None:
    _audit_handler(event, "CUOTA_PAGADA", "leasing", "cuota", "cuota_id")


def _on_liquidacion(event) -> None:
    _audit_handler(event, "LIQUIDACION_GENERADA", "finanzas", "liquidacion", "asiento_id")


def _on_orden_cerrada(event) -> None:
    _audit_handler(event, "ORDEN_TRABAJO_CERRADA", "taller", "orden", "orden_id")


def _on_documento_ap(event) -> None:
    _audit_handler(event, "DOCUMENTO_AP", "finanzas", "ap_documento", "documento_id")


def _on_pago_ap(event) -> None:
    _audit_handler(event, "PAGO_AP", "finanzas", "ap_pago", "pago_id")


def register_domain_handlers() -> None:
    global _REGISTERED
    if _REGISTERED:
        return
    subscribe(event_types.VENTA_CONFIRMADA, _on_venta_confirmada)
    subscribe(event_types.VENTA_ANULADA, _on_venta_anulada)
    subscribe(event_types.CONTRATO_LEASING_ACTIVADO, _on_contrato_activado)
    subscribe(event_types.PAGO_REALIZADO, _on_pago_realizado)
    subscribe(event_types.CUOTA_PAGADA, _on_cuota_pagada)
    subscribe(event_types.LIQUIDACION_GENERADA, _on_liquidacion)
    subscribe(event_types.ORDEN_TRABAJO_CERRADA, _on_orden_cerrada)
    subscribe(event_types.DOCUMENTO_AP_REGISTRADO, _on_documento_ap)
    subscribe(event_types.PAGO_AP_REGISTRADO, _on_pago_ap)
    _REGISTERED = True
    logger.info("Handlers de dominio ERP registrados.")
