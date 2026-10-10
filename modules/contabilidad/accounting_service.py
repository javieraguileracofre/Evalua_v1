# modules/contabilidad/accounting_service.py
# -*- coding: utf-8 -*-
"""
Contrato único de contabilización.

Otros módulos NO deben llamar `crear_asiento` ni escribir tablas de asientos
directamente: deben usar este servicio (o emitir eventos que lo consuman).
"""
from __future__ import annotations

from datetime import date, datetime
from typing import Any, Sequence

from sqlalchemy.orm import Session

from crud.finanzas.contabilidad_asientos import (
    crear_asiento,
    eliminar_asiento_contable,
    obtener_asiento_detalle,
)


class AccountingService:
    """Fachada del dominio Contabilidad."""

    def post_entry(
        self,
        db: Session,
        *,
        fecha: datetime | date | None,
        origen_tipo: str,
        origen_id: int,
        glosa: str,
        detalles: Sequence[dict[str, Any]],
        usuario: str | None = None,
        moneda: str = "CLP",
        do_commit: bool = True,
    ) -> int:
        return crear_asiento(
            db,
            fecha=fecha,
            origen_tipo=origen_tipo,
            origen_id=origen_id,
            glosa=glosa,
            detalles=detalles,
            usuario=usuario,
            moneda=moneda,
            do_commit=do_commit,
        )

    def get_entry(self, db: Session, asiento_id: int) -> dict[str, Any] | None:
        return obtener_asiento_detalle(db, asiento_id)

    def delete_entry(self, db: Session, asiento_id: int) -> None:
        eliminar_asiento_contable(db, asiento_id)


accounting_service = AccountingService()
