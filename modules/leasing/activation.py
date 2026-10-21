# modules/leasing/activation.py — casos de uso de activación contable.
# -*- coding: utf-8 -*-
from __future__ import annotations

from sqlalchemy.orm import Session

from services.leasing_financiero_contabilidad import activar_contabilidad_leasing_financiero
from services.leasing_operativo_contabilidad import registrar_asiento_activacion


def activar_leasing_financiero(db: Session, cotizacion, *, usuario: str | None = None) -> int:
    """Activa contabilidad LF y emite ContratoLeasingActivado."""
    return activar_contabilidad_leasing_financiero(db, cotizacion, usuario=usuario)


def activar_leasing_operativo(
    db: Session,
    sim,
    *,
    contrato_id: int,
    factura_compra: dict,
    usuario: str,
) -> int | None:
    """Activa contabilidad LOP y emite ContratoLeasingActivado."""
    return registrar_asiento_activacion(
        db,
        sim,
        contrato_id=contrato_id,
        factura_compra=factura_compra,
        usuario=usuario,
    )


__all__ = ["activar_leasing_financiero", "activar_leasing_operativo"]