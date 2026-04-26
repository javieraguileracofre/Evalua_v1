from __future__ import annotations

import logging
from datetime import datetime
from decimal import Decimal

from sqlalchemy.orm import Session

from crud import fondos_rendir as crud_fr
from crud import fondos_rendir_contabilidad as crud_fr_cont

logger = logging.getLogger(__name__)


def crear_anticipo_y_contabilizar(
    db: Session,
    *,
    empleado_id: int,
    vehiculo_transporte_id: int | None,
    monto_anticipo: Decimal,
    fecha_entrega: datetime,
    observaciones: str | None,
    usuario: str | None = None,
):
    """
    Caso de uso: crea fondo por rendir y registra asiento de entrega.
    """
    fondo = crud_fr.crear_fondo(
        db,
        empleado_id=empleado_id,
        vehiculo_transporte_id=vehiculo_transporte_id,
        monto_anticipo=monto_anticipo,
        fecha_entrega=fecha_entrega,
        observaciones=observaciones,
    )
    crud_fr_cont.contabilizar_entrega_anticipo(db, fondo, usuario=usuario)
    logger.info("Fondo por rendir creado y contabilizado: folio=%s id=%s", fondo.folio, fondo.id)
    return fondo


def aprobar_rendicion_y_contabilizar(
    db: Session,
    *,
    fondo_id: int,
    usuario: str | None = None,
):
    """
    Caso de uso: aprueba rendición y genera asiento de liquidación.
    """
    crud_fr.aprobar_rendicion(db, fondo_id)
    db.flush()
    fondo = crud_fr.obtener_fondo(db, fondo_id)
    if not fondo:
        raise ValueError("Anticipo no encontrado.")
    crud_fr_cont.contabilizar_liquidacion_rendicion(db, fondo, usuario=usuario)
    logger.info(
        "Rendición aprobada y contabilizada: folio=%s id=%s",
        fondo.folio,
        fondo.id,
    )
    return fondo


def diagnosticar_setup_contable(db: Session) -> dict[str, dict[str, str]]:
    return crud_fr_cont.diagnostico_cuentas_fondos_rendir(db)
