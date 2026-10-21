# modules/contabilidad/manual_entries.py
# -*- coding: utf-8 -*-
"""Casos de uso de asientos manuales (UI contabilidad)."""
from __future__ import annotations

from datetime import date, datetime
from typing import Any, Sequence

from sqlalchemy.orm import Session

from modules.contabilidad.accounting_service import accounting_service


def registrar_asiento_manual(
    db: Session,
    *,
    fecha: datetime | date | None,
    glosa: str,
    detalles: Sequence[dict[str, Any]],
    usuario: str | None = None,
    es_apertura: bool = False,
    do_commit: bool = True,
) -> int:
    """Registra MANUAL_APERTURA o MANUAL_AJUSTE.

    origen_id queda en 0 a propósito: varios asientos manuales conviven.
    La idempotencia de la API vive en fin.api_idempotencia, no en ese origen.
    """
    origen = "MANUAL_APERTURA" if es_apertura else "MANUAL_AJUSTE"
    return accounting_service.post_entry(
        db,
        fecha=fecha,
        origen_tipo=origen,
        origen_id=0,
        glosa=(glosa or "").strip()[:255],
        detalles=detalles,
        usuario=usuario,
        idempotent=False,
        do_commit=do_commit,
    )


def revertir_asiento_manual(
    db: Session,
    *,
    asiento_original_id: int,
    glosa: str | None = None,
    usuario: str | None = None,
) -> int:
    return accounting_service.reverse_manual_entry(
        db,
        asiento_original_id=asiento_original_id,
        glosa=glosa,
        usuario=usuario,
    )


__all__ = ["registrar_asiento_manual", "revertir_asiento_manual"]