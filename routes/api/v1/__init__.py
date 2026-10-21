# routes/api/v1 — contrato HTTP versionado para integraciones.
# -*- coding: utf-8 -*-
from __future__ import annotations

from fastapi import APIRouter, Depends

from core.config import settings
from db.schema_revision import ERP_SCHEMA_REVISION
from routes.api.v1.deps import require_authenticated

router = APIRouter(prefix="/api/v1", tags=["API v1"])


@router.get("/meta")
def api_v1_meta() -> dict[str, object]:
    """Metadatos públicos mínimos del contrato API (sin secretos)."""
    return {
        "api": "evalua",
        "version": "v1",
        "app_version": getattr(settings, "app_version", "unknown"),
        "schema_revision": ERP_SCHEMA_REVISION,
        "tenancy_mode": getattr(settings, "tenancy_mode", "legacy"),
    }


@router.get("/session")
def api_v1_session(auth: dict = Depends(require_authenticated)) -> dict[str, object]:
    """Identidad de sesión autorizada (sin PII innecesaria)."""
    return {
        "authenticated": True,
        "user_id": auth.get("id") or auth.get("user_id"),
        "roles": list(auth.get("roles") or []) if isinstance(auth.get("roles"), (list, tuple, set)) else [],
    }


@router.get("/health")
def api_v1_health() -> dict[str, str]:
    return {"status": "ok", "api": "v1"}


# Sub-routers de dominio (extensibles sin romper HTML).
from routes.api.v1 import accounting as accounting_api  # noqa: E402
from routes.api.v1 import leasing as leasing_api  # noqa: E402
from routes.api.v1 import operations as operations_api  # noqa: E402
from routes.api.v1 import search as search_api  # noqa: E402

router.include_router(accounting_api.router)
router.include_router(leasing_api.router)
router.include_router(operations_api.router)
router.include_router(search_api.router)
