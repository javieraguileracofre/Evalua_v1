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
    archivar_origen_asiento,
    crear_asiento,
    crear_reversion_asiento_manual,
    obtener_asiento_detalle,
    obtener_asiento_id_por_origen,
    revertir_asiento_negocio,
)
from erp_platform.events import types as event_types
from services.audit.financial import audit_financial_fact


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
        idempotent: bool | None = None,
        emit_event: bool = False,
        company_id: int | None = None,
        actor_id: int | None = None,
    ) -> int:
        try:
            asiento_id = crear_asiento(
                db,
                fecha=fecha,
                origen_tipo=origen_tipo,
                origen_id=origen_id,
                glosa=glosa,
                detalles=detalles,
                usuario=usuario,
                moneda=moneda,
                do_commit=False,
                idempotent=idempotent,
            )
            ot = str(origen_tipo or "").strip().upper()
            audit_financial_fact(
                db,
                action="ASIENTO_POSTEADO",
                module="contabilidad",
                entity="asiento",
                entity_id=asiento_id,
                actor_id=actor_id,
                company_id=company_id,
                detail={"origen_tipo": ot, "origen_id": int(origen_id or 0)},
            )
            if emit_event:
                from erp_platform.events import publish_in_transaction

                publish_in_transaction(
                    db,
                    event_name=event_types.FACTURA_REGISTRADA,
                    payload={
                        "asiento_id": asiento_id,
                        "origen_tipo": ot,
                        "origen_id": int(origen_id or 0),
                    },
                    company_id=company_id,
                    actor_id=actor_id,
                    correlation_id=f"FACTURA:{ot}:{int(origen_id or 0)}",
                )
            if do_commit:
                db.commit()
                if emit_event:
                    from erp_platform.events import flush_outbox_after_commit

                    flush_outbox_after_commit(db)
            return asiento_id
        except Exception:
            if do_commit:
                db.rollback()
            raise

    def get_entry(self, db: Session, asiento_id: int) -> dict[str, Any] | None:
        return obtener_asiento_detalle(db, asiento_id)

    def find_by_origen(
        self,
        db: Session,
        *,
        origen_tipo: str,
        origen_id: int,
    ) -> int | None:
        return obtener_asiento_id_por_origen(
            db, origen_tipo=origen_tipo, origen_id=origen_id
        )

    def reverse_business_entry(
        self,
        db: Session,
        *,
        asiento_original_id: int,
        origen_tipo: str,
        origen_id: int,
        glosa: str | None = None,
        usuario: str | None = None,
        do_commit: bool = False,
    ) -> int:
        """Reversión de un asiento de negocio. No borra el original."""
        return revertir_asiento_negocio(
            db,
            asiento_original_id=asiento_original_id,
            origen_tipo=origen_tipo,
            origen_id=origen_id,
            glosa=glosa,
            usuario=usuario,
            do_commit=do_commit,
        )

    def release_origin_key(self, db: Session, asiento_id: int) -> None:
        """Archiva la clave de origen para permitir un asiento nuevo del mismo documento."""
        archivar_origen_asiento(db, asiento_id)

    def reverse_manual_entry(
        self,
        db: Session,
        *,
        asiento_original_id: int,
        glosa: str | None = None,
        usuario: str | None = None,
        do_commit: bool = True,
    ) -> int:
        """Reversión trazable (espejo) de asientos MANUAL_* vía REV_MANUAL."""
        return crear_reversion_asiento_manual(
            db,
            asiento_original_id=asiento_original_id,
            glosa=glosa,
            usuario=usuario,
            do_commit=do_commit,
        )


accounting_service = AccountingService()
