# main.py
# -*- coding: utf-8 -*-
from __future__ import annotations

import html
import importlib
import logging
import pkgutil
import traceback
from pathlib import Path

from core.public_errors import log_unhandled

from fastapi import FastAPI, Request
from fastapi.exception_handlers import (
    http_exception_handler,
    request_validation_exception_handler,
)
from fastapi.exceptions import RequestValidationError
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException
from starlette.responses import FileResponse, HTMLResponse

from core.auth_middleware import AuthMiddleware
from core.config import settings
from core.csrf_middleware import CSRFMiddleware
from core.logging import setup_logging
from core.observability_middleware import ObservabilityMiddleware
from core.security_headers import SecurityHeadersMiddleware
from core.tenant import TenantResolutionMiddleware
from db.base_class import Base
from db.session import get_engine
from db.startup_schema import apply_startup_schema
from core.evalua_session_middleware import EvaluaSessionMiddleware

import models  # noqa: F401
import routes.ui as ui_routes_pkg


# ============================================================
# LOGGING
# ============================================================

setup_logging()
logger = logging.getLogger("evalua.main")


def health_payload(*, deep: bool = False) -> dict[str, object]:
    """Producción: status mínimo. Desarrollo /health/ready: dependencias."""
    base: dict[str, object] = {"status": "ok"}
    if settings.is_dev:
        base.update(
            {
                "app": settings.app_name,
                "env": settings.app_env,
                "tenancy_mode": getattr(settings, "tenancy_mode", "legacy"),
            }
        )
    if not deep:
        return base

    checks: dict[str, object] = {}
    overall = "ok"
    try:
        from db.schema_revision import ERP_SCHEMA_REVISION

        checks["schema_revision"] = ERP_SCHEMA_REVISION
    except Exception:
        checks["schema_revision"] = "unavailable"
        overall = "degraded"

    if getattr(settings, "database_per_company", False):
        try:
            from db.identity_session import get_identity_engine
            from sqlalchemy import text as sa_text

            eng = get_identity_engine()
            with eng.connect() as conn:
                conn.execute(sa_text("SELECT 1"))
            checks["identity_db"] = "ok"
        except Exception:
            checks["identity_db"] = "error"
            overall = "error"
    else:
        try:
            from db.session import get_engine
            from sqlalchemy import text as sa_text

            eng = get_engine(getattr(settings, "default_tenant_code", None) or None)
            with eng.connect() as conn:
                conn.execute(sa_text("SELECT 1"))
            checks["operational_db"] = "ok"
        except Exception:
            checks["operational_db"] = "error"
            overall = "error"

    base["status"] = overall
    base["checks"] = checks
    return base


# ============================================================
# PATHS
# ============================================================

BASE_DIR = Path(__file__).resolve().parent
STATIC_DIR = BASE_DIR / "static"


# ============================================================
# ORDEN DE MÓDULOS ERP
# ============================================================

ROUTER_ORDER = [
    "auth",
    "inicio",
    "home",
    "cliente",
    "proveedor",
    "postventa",
    "comercial",
    "leasing_financiero",
    "leasing_credito",
    "credito_riesgo",
    "credito_cobranzas",
    "leasing_operativo",
    "inventario",
    "ventas_pos",
    "taller",
    "fondos_rendir",
    "remuneraciones",
    "transporte_viajes",
    "cobranza",
    "cuentas_por_pagar",
    "finanzas",
    "tesoreria",
    "fin_periodos",
    "contabilidad",
    "admin_seguridad",
    "admin_correo",
    "admin_auditoria",
    "admin_backups",
    "admin_system_status",
    "admin_empresas",
    "empresa_contexto",
]


# ============================================================
# AUTO DESCUBRIMIENTO ROUTERS UI
# ============================================================

def discover_ui_router_modules() -> list[str]:
    package_path = ui_routes_pkg.__path__

    discovered = [
        module_info.name
        for module_info in pkgutil.iter_modules(package_path)
        if not module_info.name.startswith("_")
    ]

    prioritized = [name for name in ROUTER_ORDER if name in discovered]
    remaining = sorted([name for name in discovered if name not in ROUTER_ORDER])

    ordered_modules = prioritized + remaining
    logger.info("Módulos UI detectados: %s", ", ".join(ordered_modules))
    return ordered_modules


def include_ui_routers(app: FastAPI) -> None:
    loaded_modules: list[str] = []

    for module_name in discover_ui_router_modules():
        try:
            full_module_name = f"{ui_routes_pkg.__name__}.{module_name}"
            module = importlib.import_module(full_module_name)

            router = getattr(module, "router", None)
            if router is None:
                logger.warning("El módulo %s no expone 'router'; se omite.", full_module_name)
                continue

            app.include_router(router)
            loaded_modules.append(module_name)
            logger.info("Router cargado: %s", module_name)

        except Exception as e:
            logger.exception("Error cargando router %s: %s", module_name, e)

    logger.info(
        "Routers UI cargados: %s",
        ", ".join(loaded_modules) if loaded_modules else "ninguno",
    )


# ============================================================
# CREACIÓN APP
# ============================================================

def create_app() -> FastAPI:
    logger.info("Iniciando aplicación %s (%s)", settings.app_name, settings.app_env)

    docs_on = settings.is_dev
    app = FastAPI(
        title=settings.app_name,
        version=settings.app_version,
        docs_url="/docs" if docs_on else None,
        redoc_url="/redoc" if docs_on else None,
        openapi_url="/openapi.json" if docs_on else None,
    )

    from core.platform_messages import MSG_DB_DOWN, MSG_NO_ACCESS, MSG_NO_COMPANY, MSG_SCHEMA_OLD
    from db.company_engine import CompanyAccessDenied, CompanyDatabaseUnavailable

    _safe_denial = {MSG_DB_DOWN, MSG_NO_ACCESS, MSG_NO_COMPANY, MSG_SCHEMA_OLD}

    @app.exception_handler(CompanyDatabaseUnavailable)
    async def company_database_unavailable(request: Request, exc: CompanyDatabaseUnavailable) -> HTMLResponse:
        del request, exc
        return HTMLResponse(
            f"<!DOCTYPE html><html lang=\"es\"><body><p>{html.escape(MSG_DB_DOWN)}</p></body></html>",
            status_code=503,
        )

    @app.exception_handler(CompanyAccessDenied)
    async def company_access_denied(request: Request, exc: CompanyAccessDenied) -> HTMLResponse:
        del request
        text = str(exc) if str(exc) in _safe_denial else MSG_NO_ACCESS
        return HTMLResponse(
            f"<!DOCTYPE html><html lang=\"es\"><body><p>{html.escape(text)}</p></body></html>",
            status_code=403,
        )

    app.add_exception_handler(HTTPException, http_exception_handler)
    app.add_exception_handler(RequestValidationError, request_validation_exception_handler)

    @app.exception_handler(Exception)
    async def unhandled_exception_handler(request: Request, exc: Exception) -> HTMLResponse:
        """Registra el fallo; en desarrollo muestra traza en HTML. En producción no expone el mensaje de la excepción."""
        err_id = log_unhandled(
            "Error no manejado",
            exc,
            extra={
                "method": request.method,
                "path": str(request.url.path),
            },
        )
        if settings.is_dev:
            resumen = html.escape(f"{type(exc).__name__}: {exc!s}"[:900])
            tb = traceback.format_exc()
            if len(tb) > 120_000:
                tb = tb[:120_000] + "\n…(recortado)"
            safe = html.escape(tb)
            body = (
                "<!DOCTYPE html><html lang=\"es\"><head><meta charset=\"utf-8\"/>"
                "<title>Error (desarrollo)</title></head>"
                "<body style=\"font-family:ui-monospace,Consolas,monospace;"
                "background:#0b0f14;color:#e6edf3;padding:1.25rem;line-height:1.35;\">"
                f"<h1 style=\"font-size:1.1rem;margin:0 0 .75rem;\">Error en desarrollo</h1>"
                f"<p style=\"opacity:.85;margin:0 0 1rem;\">"
                f"<strong>{html.escape(request.method)}</strong> "
                f"<code>{html.escape(str(request.url.path))}</code> "
                f"<span style=\"opacity:.7;\">· ref <code>{html.escape(err_id)}</code></span></p>"
                "<p class=\"mb-2\"><strong>Resumen:</strong></p>"
                f"<pre style=\"white-space:pre-wrap;word-break:break-word;"
                "background:#1a1520;border:1px solid #402040;border-radius:8px;"
                f"padding:.75rem;\">{resumen}</pre>"
                f"<pre style=\"white-space:pre-wrap;word-break:break-word;"
                "background:#111923;border:1px solid #223047;border-radius:8px;"
                "padding:1rem;overflow:auto;margin-top:1rem;\">{safe}</pre>"
                "<p style=\"margin-top:1rem;font-size:.85rem;opacity:.75;\">"
                "Revise también la consola donde corre Uvicorn.</p></body></html>"
            )
            return HTMLResponse(content=body, status_code=500)
        safe_id = html.escape(err_id)
        body = (
            "<!DOCTYPE html><html lang=\"es\"><head><meta charset=\"utf-8\"/>"
            "<title>Error</title></head><body style=\"font-family:system-ui,sans-serif;padding:1.25rem;\">"
            "<h1>Error del servidor</h1>"
            "<p>Lo sentimos, ocurrió un error inesperado. El equipo puede localizar el incidente "
            f"en los registros con el identificador <strong><code>{safe_id}</code></strong>.</p>"
            f"<p style=\"color:#555;font-size:.9rem;\"><strong>{html.escape(request.method)}</strong> "
            f"<code>{html.escape(str(request.url.path))}</code></p>"
            "<p style=\"color:#555;font-size:.9rem;\">No comparta este identificador en canales públicos; "
            "envíelo solo a su administrador o soporte interno.</p>"
            "</body></html>"
        )
        return HTMLResponse(content=body, status_code=500)

    # Orden: insert(0) en cada add → el último add queda en índice 0 del stack interno.
    # Flujo real (tras ServerError): Observability → Session → CSRF → Tenant → Auth → rutas.
    # TrustedHost y cabeceras de seguridad quedan más afuera.
    app.add_middleware(AuthMiddleware)
    app.add_middleware(TenantResolutionMiddleware)
    app.add_middleware(CSRFMiddleware)
    app.add_middleware(
        EvaluaSessionMiddleware,
        secret_key=settings.secret_key,
        session_cookie="evalua_session",
        max_age=settings.auth_session_max_age_seconds,
        same_site="lax",
        https_only=settings.auth_cookie_secure,
    )
    app.add_middleware(ObservabilityMiddleware)
    app.add_middleware(SecurityHeadersMiddleware)
    from starlette.middleware.trustedhost import TrustedHostMiddleware

    app.add_middleware(TrustedHostMiddleware, allowed_hosts=list(settings.allowed_hosts))
    logger.info(
        "Middleware de sesión y autenticación activos (cookie_secure=%s, hosts=%s).",
        settings.auth_cookie_secure,
        ",".join(settings.allowed_hosts),
    )

    if STATIC_DIR.exists():
        app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")
        logger.info("Static montado en /static")
    else:
        logger.warning("No se encontró carpeta static: %s", STATIC_DIR)

    if getattr(settings, "database_per_company", False):
        try:
            from db.identity_session import init_identity_schema

            init_identity_schema()
            logger.info("Esquema de identidad listo.")
        except Exception as exc:
            logger.critical("No se pudo preparar erp_identity: %s", type(exc).__name__)
            if not settings.is_dev:
                raise RuntimeError("No se pudo preparar la base de identidad.") from exc
        engine = None
    else:
        engine = get_engine(getattr(settings, "default_tenant_code", None) or None)
    if engine is not None:
        try:
            apply_startup_schema(
                engine,
                allow_ddl=bool(settings.auto_migrate_on_startup),
                create_all=Base.metadata.create_all if settings.auto_migrate_on_startup else None,
            )
            if settings.auto_migrate_on_startup:
                logger.info("Metadata/DDL sincronizados para tenant '%s'", settings.default_tenant_code)
        except Exception as e:
            logger.critical("Error crítico ejecutando DDL/migraciones al iniciar: %s", e, exc_info=True)
            if not settings.is_dev:
                raise RuntimeError("Fallo de migración automática en arranque.") from e

    include_ui_routers(app)

    from routes.api.lop import router as lop_api_router
    from routes.api.v1 import router as api_v1_router

    app.include_router(api_v1_router)
    app.include_router(lop_api_router, prefix="/api/comercial/leasing-operativo")
    # Alias profesional pedido por motor residual (mismos handlers)
    app.include_router(lop_api_router, prefix="/api/leasing", include_in_schema=False)
    logger.info(
        "API v1 en /api/v1; LOP en /api/comercial/leasing-operativo (+ alias /api/leasing)"
    )

    try:
        from modules.bootstrap import register_domain_handlers

        register_domain_handlers()
    except Exception as exc:
        logger.warning("No se pudieron registrar handlers de dominio: %s", type(exc).__name__)

    try:
        from erp_platform.events.sweeper import start_outbox_sweeper

        start_outbox_sweeper()
    except Exception as exc:
        logger.warning("No se pudo iniciar el barrido de outbox: %s", type(exc).__name__)

    @app.get("/health", tags=["Health"])
    def healthcheck() -> dict[str, object]:
        return health_payload(deep=False)

    @app.get("/health/ready", tags=["Health"])
    def health_ready() -> dict[str, object]:
        payload = health_payload(deep=True)
        # No exponer detalles de infraestructura sensibles en producción.
        if not settings.is_dev and isinstance(payload.get("checks"), dict):
            safe = {
                k: ("ok" if v == "ok" else "error")
                for k, v in payload["checks"].items()
                if k in {"identity_db", "operational_db"}
            }
            payload["checks"] = safe
        return payload

    favicon_path = STATIC_DIR / "favicon.ico"
    if favicon_path.is_file():

        @app.get("/favicon.ico", include_in_schema=False)
        def favicon():
            return FileResponse(favicon_path, media_type="image/x-icon")

    logger.info("Aplicación iniciada correctamente")
    return app


# ============================================================
# APP INSTANCE
# ============================================================

app = create_app()


# ============================================================
# RUN LOCAL
# ============================================================

if __name__ == "__main__":
    import uvicorn

    if settings.is_dev and settings.uvicorn_host in {"0.0.0.0", "::"} and not settings.secret_key_is_strong:
        raise SystemExit(
            "Arranque bloqueado: UVICORN_HOST=0.0.0.0 en desarrollo requiere SECRET_KEY "
            "de al menos 32 caracteres aleatorios. Use UVICORN_HOST=127.0.0.1 o rote SECRET_KEY."
        )

    if settings.uvicorn_host in {"0.0.0.0", "::"}:
        logger.info(
            "Acceso desde iPhone u otros equipos: misma Wi‑Fi que esta PC y en el navegador "
            "http://<IP-de-esta-PC>:%s (no uses 127.0.0.1 desde el móvil). Si Windows pide firewall, permite redes privadas.",
            settings.uvicorn_port,
        )
    else:
        logger.info(
            "Servidor solo en esta máquina: http://%s:%s",
            settings.uvicorn_host,
            settings.uvicorn_port,
        )

    uvicorn.run(
        "main:app",
        host=settings.uvicorn_host,
        port=settings.uvicorn_port,
        reload=settings.app_debug,
        log_level="info",
    )