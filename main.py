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
from starlette.responses import HTMLResponse

from core.auth_middleware import AuthMiddleware
from core.config import settings
from core.csrf_middleware import CSRFMiddleware
from core.logging import setup_logging
from core.tenant import TenantResolutionMiddleware
from db.base_class import Base
from db.session import get_engine
from db.startup_schema import (
    ensure_ap_documento_contabilidad_columns,
    ensure_auth_roles_seed,
    ensure_comercial_leasing_financiero_schema,
    ensure_credito_riesgo_schema,
    ensure_leasing_operativo_schema,
    ensure_fin_config_contable_seed,
    ensure_fondos_rendir_asiento_columns,
    ensure_postventa_crm_schema,
    ensure_taller_ordenes_cotizacion_columns,
    ensure_vehiculo_transporte_consumo_column,
)
from core.evalua_session_middleware import EvaluaSessionMiddleware

import models  # noqa: F401
import routes.ui as ui_routes_pkg


# ============================================================
# LOGGING
# ============================================================

setup_logging()
logger = logging.getLogger("evalua.main")


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
    "leasing_operativo",
    "inventario",
    "ventas_pos",
    "taller",
    "fondos_rendir",
    "transporte_viajes",
    "cobranza",
    "cuentas_por_pagar",
    "finanzas",
    "fin_periodos",
    "contabilidad",
    "admin_seguridad",
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
    # Flujo real (tras ServerError): Session → CSRF → Tenant → Auth → rutas.
    # CSRF es ASGI puro (no BaseHTTPMiddleware) para no vaciar el cuerpo POST hacia FastAPI.
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
    logger.info(
        "Middleware de sesión y autenticación activos (cookie_secure=%s).",
        settings.auth_cookie_secure,
    )

    if STATIC_DIR.exists():
        app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")
        logger.info("Static montado en /static")
    else:
        logger.warning("No se encontró carpeta static: %s", STATIC_DIR)

    engine = get_engine(settings.default_tenant_code)
    if settings.auto_migrate_on_startup:
        try:
            Base.metadata.create_all(bind=engine)
            logger.info("Metadata sincronizada para tenant '%s'", settings.default_tenant_code)
            ensure_ap_documento_contabilidad_columns(engine)
            ensure_taller_ordenes_cotizacion_columns(engine)
            ensure_fondos_rendir_asiento_columns(engine)
            ensure_vehiculo_transporte_consumo_column(engine)
            ensure_auth_roles_seed(engine)
            ensure_fin_config_contable_seed(engine)
            ensure_comercial_leasing_financiero_schema(engine)
            ensure_credito_riesgo_schema(engine)
            ensure_leasing_operativo_schema(engine)
            ensure_postventa_crm_schema(engine)
        except Exception as e:
            logger.critical("Error crítico ejecutando DDL/migraciones al iniciar: %s", e, exc_info=True)
            if not settings.is_dev:
                raise RuntimeError("Fallo de migración automática en arranque.") from e
    else:
        logger.info("AUTO_MIGRATE_ON_STARTUP=false: se omiten create_all y ensure_* en arranque.")

    include_ui_routers(app)

    @app.get("/health", tags=["Health"])
    def healthcheck() -> dict[str, str]:
        return {
            "status": "ok",
            "app": settings.app_name,
            "env": settings.app_env,
            "default_tenant": settings.default_tenant_code,
        }

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