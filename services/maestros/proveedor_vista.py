# services/maestros/proveedor_vista.py
# -*- coding: utf-8 -*-
"""
Capa de presentación sobre la dualidad Proveedor (maestros) / ProveedorFin (finanzas).

No consolida tablas (riesgo contable). Expone una vista unificada para listados UI.
"""
from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from models.finanzas.compras_finanzas import ProveedorFin
from models.maestros.proveedor import Proveedor


def proveedor_display_name(db: Session, *, proveedor_id: int | None = None, proveedor_fin_id: int | None = None) -> str:
    if proveedor_id:
        row = db.get(Proveedor, int(proveedor_id))
        if row is not None:
            return str(getattr(row, "razon_social", None) or getattr(row, "nombre", None) or f"Proveedor #{proveedor_id}")
    if proveedor_fin_id:
        row = db.get(ProveedorFin, int(proveedor_fin_id))
        if row is not None:
            return str(getattr(row, "nombre", None) or f"ProveedorFin #{proveedor_fin_id}")
    return "—"


def listar_proveedores_unificados(db: Session, *, limite: int = 100) -> list[dict[str, Any]]:
    """Lista maestros + finanzas con origen etiquetado (sin fusionar IDs)."""
    out: list[dict[str, Any]] = []
    for p in db.scalars(select(Proveedor).limit(limite)):
        out.append(
            {
                "origen": "maestro",
                "id": int(p.id),
                "nombre": str(getattr(p, "razon_social", None) or ""),
                "rut": str(getattr(p, "rut", None) or ""),
            }
        )
    for p in db.scalars(select(ProveedorFin).limit(limite)):
        out.append(
            {
                "origen": "finanzas",
                "id": int(p.id),
                "nombre": str(getattr(p, "nombre", None) or ""),
                "rut": str(getattr(p, "rut", None) or ""),
            }
        )
    out.sort(key=lambda r: (r["nombre"] or "").lower())
    return out
