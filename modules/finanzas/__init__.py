# modules/finanzas — contrato público CxP / finanzas operativas.
# -*- coding: utf-8 -*-
from __future__ import annotations

from sqlalchemy.orm import Session

from crud.finanzas.cuentas_por_pagar import CuentasPorPagarCRUD
from schemas.finanzas.cuentas_por_pagar import DocumentoCreate, PagoCreate

_cxp = CuentasPorPagarCRUD()


def registrar_documento_ap(
    db: Session,
    payload: DocumentoCreate,
    *,
    user_email: str | None = None,
):
    """Caso de uso: alta de documento AP (incluye asiento vía AccountingService)."""
    return _cxp.create_documento(db, payload, user_email=user_email)


def anular_documento_ap(
    db: Session,
    documento_id: int,
    *,
    user_email: str | None = None,
    ip_origen: str | None = None,
) -> None:
    """Caso de uso: anula un documento AP revirtiendo el asiento, sin borrarlo."""
    _cxp.eliminar_documento(
        db,
        documento_id,
        user_email=user_email,
        ip_origen=ip_origen,
    )


def registrar_pago_ap(
    db: Session,
    payload: PagoCreate,
    *,
    user_email: str | None = None,
):
    """Caso de uso: pago a proveedor con contabilización atómica."""
    return _cxp.registrar_pago(db, payload, user_email=user_email)


__all__ = [
    "anular_documento_ap",
    "registrar_documento_ap",
    "registrar_pago_ap",
    "CuentasPorPagarCRUD",
]
