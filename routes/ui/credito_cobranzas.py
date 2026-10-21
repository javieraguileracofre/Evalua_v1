# routes/ui/credito_cobranzas.py
# -*- coding: utf-8 -*-
"""Hub del módulo Crédito y cobranzas (crédito/riesgo + cobranza)."""
from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from core.ui_templates import EvaluaTemplates as Jinja2Templates
from sqlalchemy.orm import Session

from core.nav_visibility import usuario_puede_ver_submodulo_nav
from core.paths import TEMPLATES_DIR
from core.rbac import guard_credito_cobranzas_hub
from db.session import get_db

router = APIRouter(prefix="/credito-cobranzas", tags=["Crédito y cobranzas"])
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))
logger = logging.getLogger("evalua.credito_cobranzas.ui")


def _safe_read(db: Session, label: str, fallback: Any, fn):
    try:
        return fn()
    except Exception:
        logger.exception("Crédito y cobranzas hub: falló %s; se usa fallback.", label)
        try:
            db.rollback()
        except Exception:
            pass
        return fallback


@router.get("", response_class=HTMLResponse, name="credito_cobranzas_hub")
@router.get("/", response_class=HTMLResponse, name="credito_cobranzas_hub_slash", include_in_schema=False)
def credito_cobranzas_hub(request: Request, db: Session = Depends(get_db)):
    if (redir := guard_credito_cobranzas_hub(request)) is not None:
        return redir

    auth = getattr(request.state, "auth_user", None)
    from core.module_catalog import NAV_CREDITO_COBRANZAS_SUBMODULE_KEYS
    from core.nav_visibility import modulos_visibles_en_sesion, usuario_puede_ver_modulo_nav

    show_credito = usuario_puede_ver_submodulo_nav(auth, "CREDITO_RIESGO")
    show_cobranza = usuario_puede_ver_submodulo_nav(auth, "COBRANZA")
    # Retrocompat: usuarios con solo FINANZAS (menú anterior) y sin claves del nuevo módulo.
    if not show_cobranza:
        visible = modulos_visibles_en_sesion(auth)
        tiene_area_cc = bool(
            visible & frozenset(("CREDITO_COBRANZAS", *NAV_CREDITO_COBRANZAS_SUBMODULE_KEYS))
        )
        if not tiene_area_cc:
            show_cobranza = usuario_puede_ver_modulo_nav(auth, "FINANZAS")

    kpi_credito: dict[str, Any] | None = None
    kpi_cobranza: dict[str, Any] | None = None

    if show_credito:
        from crud.comercial import credito_riesgo as crud_cr

        kpi_credito = _safe_read(
            db,
            "dashboard_kpis",
            {
                "total_solicitudes": 0,
                "aprobadas": 0,
                "rechazadas": 0,
                "comite": 0,
                "score_promedio": None,
                "monto_solicitado_total": 0,
                "monto_aprobado_total": 0,
            },
            lambda: crud_cr.dashboard_kpis(db),
        )

    if show_cobranza:
        from crud.cobranza import cobranza as crud_cobranza

        kpi_cobranza = _safe_read(
            db,
            "resumen_cobranza_general",
            {
                "total_documentos": 0,
                "total_monto": 0,
                "total_saldo": 0,
                "total_saldo_contable": 0,
            },
            lambda: crud_cobranza.resumen_cobranza_general(db),
        )

    return templates.TemplateResponse(
        "credito_cobranzas/hub.html",
        {
            "request": request,
            "active_menu": "credito_cobranzas",
            "show_credito": show_credito,
            "show_cobranza": show_cobranza,
            "kpi_credito": kpi_credito,
            "kpi_cobranza": kpi_cobranza,
        },
    )
