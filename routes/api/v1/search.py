# routes/api/v1/search.py
# -*- coding: utf-8 -*-
"""Buscador global de acciones y registros, acotado a la empresa y a los módulos de la sesión."""
from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.orm import Session

from db.session import get_db
from routes.api.v1.deps import require_authenticated
from services.ux.workspace import acciones_json, buscar_entidades

router = APIRouter(tags=["API v1 · Búsqueda"])
logger = logging.getLogger("evalua.ux")


@router.get("/search")
def api_v1_search(
    request: Request,
    q: str = Query("", max_length=80),
    auth: dict = Depends(require_authenticated),
    db: Session = Depends(get_db),
) -> dict[str, object]:
    term = (q or "").strip()
    try:
        results = buscar_entidades(request, db, auth, term)
    except Exception:
        logger.exception("busqueda global")
        db.rollback()
        results = []
    return {
        "q": term,
        "actions": acciones_json(request, auth, term),
        "results": results,
    }
