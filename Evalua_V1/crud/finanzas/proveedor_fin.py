# crud/finanzas/proveedor_fin.py
# -*- coding: utf-8 -*-
from __future__ import annotations

from typing import Optional

from sqlalchemy import text
from sqlalchemy.orm import Session, joinedload

from crud.finanzas.cxp_montos_sql import cxp_sql_saldo_desde_lineas, cxp_sql_total_desde_lineas
from models.finanzas.compras_finanzas import ProveedorFin
from schemas.finanzas.proveedor_fin import ProveedorFinCreate, ProveedorFinUpdate


class ProveedorFinCRUD:
    def get_by_proveedor_id(self, db: Session, proveedor_id: int) -> Optional[ProveedorFin]:
        return (
            db.query(ProveedorFin)
            .options(joinedload(ProveedorFin.proveedor))
            .filter(ProveedorFin.proveedor_id == proveedor_id)
            .first()
        )

    def upsert(
        self,
        db: Session,
        payload: ProveedorFinCreate | ProveedorFinUpdate,
        proveedor_id: int,
    ) -> ProveedorFin:
        try:
            row = self.get_by_proveedor_id(db, proveedor_id)

            if row is None:
                row = ProveedorFin(
                    proveedor_id=proveedor_id,
                    condicion_pago_dias=payload.condicion_pago_dias,
                    limite_credito=payload.limite_credito,
                    estado=payload.estado,
                    notas=payload.notas,
                )
                db.add(row)
            else:
                row.condicion_pago_dias = payload.condicion_pago_dias
                row.limite_credito = payload.limite_credito
                row.estado = payload.estado
                row.notas = payload.notas

            db.flush()
            db.refresh(row)
            db.commit()
            db.refresh(row)
            return row

        except Exception:
            db.rollback()
            raise

    def delete_by_proveedor_id(self, db: Session, proveedor_id: int) -> None:
        try:
            row = self.get_by_proveedor_id(db, proveedor_id)
            if row:
                db.delete(row)
                db.flush()
            db.commit()
        except Exception:
            db.rollback()
            raise

    def get_resumen_financiero(self, db: Session, proveedor_id: int) -> dict:
        _t = cxp_sql_total_desde_lineas("d")
        _s = cxp_sql_saldo_desde_lineas("d")
        row = db.execute(
            text(
                f"""
                SELECT
                    COALESCE(COUNT(d.id), 0) AS total_documentos,
                    COALESCE(SUM(({_t})), 0) AS total_documentado,
                    COALESCE(SUM(({_s})), 0) AS saldo_pendiente,
                    COALESCE(SUM(
                        CASE
                            WHEN ({_s}) > 0
                             AND d.fecha_vencimiento < CURRENT_DATE
                            THEN 1
                            ELSE 0
                        END
                    ), 0) AS docs_vencidos
                FROM fin.ap_documento d
                WHERE d.proveedor_id = :proveedor_id
                """
            ),
            {"proveedor_id": proveedor_id},
        ).mappings().first()

        return dict(row) if row else {
            "total_documentos": 0,
            "total_documentado": 0,
            "saldo_pendiente": 0,
            "docs_vencidos": 0,
        }


proveedor_fin = ProveedorFinCRUD()