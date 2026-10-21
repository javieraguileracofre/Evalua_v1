# routes/api/v1/leasing.py
# -*- coding: utf-8 -*-
from __future__ import annotations

from fastapi import APIRouter, Depends

from erp_platform.permissions import LEASING_VIEW
from routes.api.v1.deps import require_permission

router = APIRouter(prefix="/leasing", tags=["API v1 · Leasing"])


@router.get("/capabilities")
def leasing_capabilities(
    _auth: dict = Depends(require_permission(LEASING_VIEW)),
) -> dict:
    """Descubrimiento de capacidades de integración (sin exponer datos operativos)."""
    return {
        "productos": ["LEASING_FINANCIERO", "LEASING_OPERATIVO"],
        "eventos": [
            "ContratoLeasingActivado",
            "CuotaGenerada",
            "CuotaPagada",
        ],
        "notas": (
            "Las operaciones mutables de LOP siguen en /api/comercial/leasing-operativo "
            "y /api/leasing; este contrato v1 es el punto de evolución."
        ),
    }
