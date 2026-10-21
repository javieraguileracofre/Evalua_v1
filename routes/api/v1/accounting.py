# routes/api/v1/accounting.py
# -*- coding: utf-8 -*-
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from db.session import get_db
from erp_platform.permissions import CONTABILIDAD_VIEW
from modules.contabilidad import accounting_service
from routes.api.v1.deps import require_permission

router = APIRouter(prefix="/accounting", tags=["API v1 · Contabilidad"])


@router.get("/entries/{asiento_id}")
def get_entry(
    asiento_id: int,
    db: Session = Depends(get_db),
    _auth: dict = Depends(require_permission(CONTABILIDAD_VIEW)),
) -> dict:
    data = accounting_service.get_entry(db, asiento_id)
    if not data:
        raise HTTPException(status_code=404, detail="Asiento no encontrado.")
    # Contrato estable: no exponer ORM crudo.
    cab = data.get("cabecera") or {}
    return {
        "id": cab.get("id") or asiento_id,
        "fecha": str(cab.get("fecha") or ""),
        "origen_tipo": cab.get("origen_tipo"),
        "origen_id": cab.get("origen_id"),
        "glosa": cab.get("glosa"),
        "moneda": cab.get("moneda") or "CLP",
        "lineas": [
            {
                "codigo_cuenta": d.get("codigo_cuenta"),
                "debe": str(d.get("debe") or "0"),
                "haber": str(d.get("haber") or "0"),
                "descripcion": d.get("descripcion"),
            }
            for d in (data.get("detalles") or [])
        ],
    }


@router.get("/entries/by-origen/{origen_tipo}/{origen_id}")
def get_entry_by_origen(
    origen_tipo: str,
    origen_id: int,
    db: Session = Depends(get_db),
    _auth: dict = Depends(require_permission(CONTABILIDAD_VIEW)),
) -> dict:
    found = accounting_service.find_by_origen(
        db, origen_tipo=origen_tipo, origen_id=origen_id
    )
    if found is None:
        raise HTTPException(status_code=404, detail="Asiento de origen no encontrado.")
    return {"asiento_id": found, "origen_tipo": origen_tipo, "origen_id": origen_id}
