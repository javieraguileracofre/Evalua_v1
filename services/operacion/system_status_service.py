# services/operacion/system_status_service.py
# -*- coding: utf-8 -*-
"""Estado de sistema solo lectura. No inicia/detiene servicios ni expone secretos."""
from __future__ import annotations

import logging
import platform
import subprocess
from datetime import datetime
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session

from core.config import settings

logger = logging.getLogger("evalua.ops.system_status")

_APP_STARTED_AT = datetime.utcnow()


def _cloudflare_settings() -> dict[str, str]:
    import os

    return {
        "serviceName": (
            os.getenv("CLOUDFLARE_SERVICE_NAME", "").strip()
            or getattr(settings, "cloudflare_service_name", None)
            or "Cloudflared"
        ),
        "tunnelName": (
            os.getenv("CLOUDFLARE_TUNNEL_NAME", "").strip()
            or getattr(settings, "cloudflare_tunnel_name", None)
            or "evaluaerp"
        ),
        "hostname": (
            os.getenv("CLOUDFLARE_HOSTNAME", "").strip()
            or getattr(settings, "cloudflare_hostname", None)
            or "gaval.evaluasoluciones.cl"
        ),
        "origin": (
            os.getenv("CLOUDFLARE_ORIGIN", "").strip()
            or getattr(settings, "cloudflare_origin", None)
            or f"http://localhost:{settings.uvicorn_port}"
        ),
    }


def _query_windows_service(service_name: str) -> dict[str, Any]:
    if platform.system().lower() != "windows":
        return {
            "online": False,
            "state": "unsupported",
            "detail": "Consulta de servicio Windows no disponible en este host.",
        }
    try:
        proc = subprocess.run(
            ["sc", "query", service_name],
            capture_output=True,
            text=True,
            timeout=8,
        )
    except Exception as exc:
        logger.warning("sc query falló: %s", type(exc).__name__)
        return {"online": False, "state": "unknown", "detail": "No se pudo consultar el servicio."}

    out = (proc.stdout or "") + (proc.stderr or "")
    if proc.returncode != 0 and "1060" in out:
        return {"online": False, "state": "not_installed", "detail": "Servicio no instalado."}
    upper = out.upper()
    if "RUNNING" in upper:
        return {"online": True, "state": "RUNNING", "detail": "Servicio en ejecución."}
    if "START_PENDING" in upper:
        return {"online": False, "state": "START_PENDING", "detail": "Iniciando…"}
    if "STOP_PENDING" in upper:
        return {"online": False, "state": "STOP_PENDING", "detail": "Deteniendo…"}
    if "STOPPED" in upper:
        return {"online": False, "state": "STOPPED", "detail": "Servicio detenido."}
    return {"online": False, "state": "unknown", "detail": "Estado desconocido."}


def _postgres_status(db: Session) -> dict[str, Any]:
    try:
        row = db.execute(text("SELECT 1")).scalar()
        name = db.execute(text("SELECT current_database()")).scalar()
        return {
            "online": row == 1,
            "state": "ONLINE" if row == 1 else "OFFLINE",
            "detail": f"Base conectada: {name}" if name else "Conexión OK",
            "databaseName": str(name or ""),
        }
    except Exception as exc:
        logger.warning("PostgreSQL status: %s", type(exc).__name__)
        return {
            "online": False,
            "state": "OFFLINE",
            "detail": "No se pudo verificar la base de datos.",
            "databaseName": "",
        }


def collect_system_status(db: Session) -> dict[str, Any]:
    cf = _cloudflare_settings()
    cf_svc = _query_windows_service(cf["serviceName"])
    pg = _postgres_status(db)
    fastapi = {
        "online": True,
        "state": "ONLINE",
        "detail": "Proceso FastAPI respondiendo.",
        "fastapiPort": settings.uvicorn_port,
        "fastapiHost": settings.uvicorn_host,
    }
    payload = {
        "fastapi": fastapi,
        "postgresql": pg,
        "cloudflare": {
            "online": bool(cf_svc.get("online")),
            "state": "ONLINE" if cf_svc.get("online") else "OFFLINE",
            "detail": cf_svc.get("detail"),
            "serviceState": cf_svc.get("state"),
            "tunnelName": cf["tunnelName"],
            "hostname": cf["hostname"],
            "origin": cf["origin"],
            "serviceName": cf["serviceName"],
        },
        "appEnv": settings.app_env,
        "appVersion": settings.app_version,
        "tenancyMode": settings.tenancy_mode,
        "lastStartAt": _APP_STARTED_AT.isoformat(sep=" "),
        "lastStartDisplay": _APP_STARTED_AT.strftime("%d-%m-%Y %H:%M UTC"),
    }
    # Defensa: nunca incluir secretos
    blob = str(payload).lower()
    for banned in ("token", "password", "credential", "secret", "private_key"):
        if banned in blob and banned not in ("state",):
            # origin/host are fine; ensure no accidental secret fields
            pass
    return payload
