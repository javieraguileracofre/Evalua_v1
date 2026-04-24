# core/config.py
# -*- coding: utf-8 -*-
from __future__ import annotations

import os
import re
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import quote_plus

from dotenv import load_dotenv


BASE_DIR = Path(__file__).resolve().parent.parent
ENV_FILE = BASE_DIR / ".env"

# Cargar .env antes de leer cualquier variable
load_dotenv(dotenv_path=ENV_FILE)


def _normalize_postgres_url_for_psycopg(url: str) -> str:
    """
    Render, Heroku y otros entregan `postgres://` o `postgresql://`; el proyecto usa
    SQLAlchemy 2 + psycopg 3 (`postgresql+psycopg://`).
    """
    u = (url or "").strip()
    if not u:
        return u
    lower = u.lower()
    if lower.startswith("postgresql+psycopg:") or lower.startswith("postgresql+asyncpg:"):
        return u
    if lower.startswith("postgres://"):
        return "postgresql+psycopg://" + u[len("postgres://") :]
    if lower.startswith("postgresql://"):
        return "postgresql+psycopg://" + u[len("postgresql://") :]
    return u


def _ensure_sslmode_require_for_supabase(url: str) -> str:
    """Supabase (db.*.supabase.co o *.pooler.supabase.com) exige TLS; sin sslmode puede colgar hasta connect_timeout."""
    u = (url or "").strip()
    if not u:
        return u
    lo = u.lower()
    if "supabase.co" not in lo and "pooler.supabase.com" not in lo:
        return u
    if "sslmode=" in u.lower():
        return u
    return f"{u}{'&' if '?' in u else '?'}sslmode=require"


def _database_url_from_db_parts() -> str | None:
    """
    Si no hay DATABASE_URL, arma postgresql+psycopg desde DB_USER, DB_PASSWORD,
    DB_HOST, DB_PORT, DB_NAME (y opcional DB_SSLMODE para Supabase, p. ej. require).
    """
    host = os.getenv("DB_HOST", "").strip()
    user = os.getenv("DB_USER", "").strip()
    password = os.getenv("DB_PASSWORD", "").strip()
    name = os.getenv("DB_NAME", "").strip()
    port = (os.getenv("DB_PORT") or "5432").strip() or "5432"
    if not host or not user or not password or not name:
        return None
    base = (
        f"postgresql+psycopg://{quote_plus(user)}:{quote_plus(password)}"
        f"@{host}:{port}/{quote_plus(name)}"
    )
    sslmode = os.getenv("DB_SSLMODE", "").strip()
    if sslmode:
        base += f"?sslmode={quote_plus(sslmode)}"
    return base


def _to_bool(value: str | None, default: bool = False) -> bool:
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "y", "on"}


def _to_int(value: str | None, default: int) -> int:
    if value is None or not str(value).strip():
        return default
    try:
        n = int(str(value).strip(), 10)
    except ValueError:
        return default
    if n < 1 or n > 65535:
        return default
    return n


def rewrite_supabase_direct_db_url_to_pooler(url: str) -> str:
    """
    db.<ref>.supabase.co:5432 suele resolver a IPv6; en Render (solo IPv4) aparece
    «Network is unreachable». Reescribe a pooler transacción :6543 con usuario postgres.<ref>.

    Host/puerto del pooler: SUPABASE_POOLER_HOST / SUPABASE_POOLER_PORT (defaults del template).
    Para forzar la URL directa (p. ej. máquina con IPv6): SUPABASE_ALLOW_DIRECT_DB_URL=true.
    """
    if os.getenv("SUPABASE_ALLOW_DIRECT_DB_URL", "").strip().lower() in (
        "1",
        "true",
        "yes",
        "on",
    ):
        return url
    raw = (url or "").strip()
    if not raw:
        return raw
    try:
        from sqlalchemy.engine.url import URL, make_url

        u = make_url(raw)
    except Exception:
        return url
    host = (u.host or "").lower()
    if "pooler.supabase.com" in host:
        return url
    if not re.match(r"^db\.[^.]+\.supabase\.co$", host):
        return url
    p = u.port
    if p is not None and p != 5432:
        return url
    ref = host.removeprefix("db.").removesuffix(".supabase.co")
    if not ref:
        return url
    pooler_host = os.getenv(
        "SUPABASE_POOLER_HOST", "aws-1-us-east-2.pooler.supabase.com"
    ).strip()
    pooler_port = _to_int(os.getenv("SUPABASE_POOLER_PORT"), 6543)
    q = dict(u.query) if u.query else {}
    ql = {k.lower() for k in q}
    if "sslmode" not in ql:
        q["sslmode"] = "require"
    new_u = URL.create(
        "postgresql+psycopg",
        username=f"postgres.{ref}",
        password=u.password,
        host=pooler_host,
        port=pooler_port,
        database=u.database or "postgres",
        query=q,
    )
    return new_u.render_as_string(hide_password=False)


def postgres_engine_connect_args(database_url: str, connect_timeout_seconds: int) -> dict:
    """
    Args para SQLAlchemy + psycopg. El pooler Supabase en puerto 6543 (modo transacción)
    no mantiene prepared statements entre transacciones; prepare_threshold=None lo evita.
    """
    args: dict = {"connect_timeout": int(connect_timeout_seconds)}
    u = database_url or ""
    if ":6543/" in u or ":6543?" in u:
        args["prepare_threshold"] = None
    return args


@dataclass(frozen=True)
class Settings:
    app_name: str
    app_env: str
    app_debug: bool
    app_version: str
    # Uvicorn: 127.0.0.1 = solo esta PC; 0.0.0.0 = también móviles/otros PCs en la misma red (Wi‑Fi).
    uvicorn_host: str
    uvicorn_port: int

    database_url: str
    platform_database_url: str
    admin_postgres_url: str | None

    default_tenant_code: str
    tenant_header_name: str
    tenant_query_param: str
    tenant_cookie_name: str

    log_level: str
    secret_key: str
    access_token_expire_minutes: int
    # Cookie de sesión solo por HTTPS (recomendado en producción detrás de TLS).
    auth_cookie_secure: bool
    # Duración máxima de la sesión en segundos (Starlette SessionMiddleware max_age).
    auth_session_max_age_seconds: int
    # Timeout TCP al conectar a PostgreSQL (evita cuelgues indefinidos si el servidor no responde).
    db_connect_timeout_seconds: int

    # Contabilidad — fondos por rendir (códigos en fin.plan_cuenta)
    fondo_rendir_cuenta_anticipo: str
    fondo_rendir_cuenta_caja: str
    fondo_rendir_cuenta_gasto: str

    @property
    def is_dev(self) -> bool:
        return self.app_env.lower() in {"dev", "development", "local"}

    @staticmethod
    def load() -> "Settings":
        database_url = os.getenv("DATABASE_URL", "").strip()
        if not database_url:
            database_url = (_database_url_from_db_parts() or "").strip()

        platform_database_url = os.getenv("PLATFORM_DATABASE_URL", "").strip()
        if not platform_database_url and database_url:
            platform_database_url = database_url

        database_url = _normalize_postgres_url_for_psycopg(database_url)
        platform_database_url = _normalize_postgres_url_for_psycopg(platform_database_url)
        database_url = rewrite_supabase_direct_db_url_to_pooler(database_url)
        platform_database_url = rewrite_supabase_direct_db_url_to_pooler(platform_database_url)
        database_url = _ensure_sslmode_require_for_supabase(database_url)
        platform_database_url = _ensure_sslmode_require_for_supabase(platform_database_url)

        if not database_url:
            raise RuntimeError(
                f"DATABASE_URL no está configurado (ni DB_HOST/DB_USER/DB_PASSWORD/DB_NAME). "
                f"Revisa el archivo: {ENV_FILE}"
            )

        if not platform_database_url:
            raise RuntimeError(
                f"PLATFORM_DATABASE_URL no está configurado. Revisa el archivo: {ENV_FILE}"
            )

        app_env_raw = os.getenv("APP_ENV", "development").strip()
        app_env_lower = app_env_raw.lower()
        is_dev = app_env_lower in {"dev", "development", "local"}

        secret_key = os.getenv("SECRET_KEY", "change-me-now").strip()
        weak_keys = {
            "",
            "change-me-now",
            "cambia-esto-en-produccion",
            "secret",
            "changeme",
            "evalua",
        }
        if not is_dev:
            if secret_key.lower() in weak_keys or len(secret_key) < 32:
                raise RuntimeError(
                    "SECRET_KEY no es válida para producción: use al menos 32 caracteres "
                    "aleatorios (p. ej. openssl rand -hex 32) y defínala en .env. "
                    f"APP_ENV={app_env_raw!r}."
                )

        # Por defecto 0.0.0.0 para poder abrir la app desde el iPhone u otros equipos en la LAN.
        uvicorn_host = os.getenv("UVICORN_HOST", "0.0.0.0").strip() or "0.0.0.0"
        uvicorn_port = _to_int(os.getenv("UVICORN_PORT") or os.getenv("PORT"), 8000)

        auth_cookie_secure = _to_bool(os.getenv("AUTH_COOKIE_SECURE"), default=not is_dev)
        # En desarrollo local (http://127.0.0.1) las cookies Secure no se guardan: la sesión CSRF fallaría siempre.
        if is_dev:
            auth_cookie_secure = False
        auth_session_max_age = _to_int(os.getenv("AUTH_SESSION_MAX_AGE_SECONDS"), 28800)
        if auth_session_max_age < 300:
            auth_session_max_age = 28800

        db_connect_timeout = _to_int(os.getenv("DB_CONNECT_TIMEOUT_SECONDS"), 10)
        if db_connect_timeout < 2:
            db_connect_timeout = 10
        if db_connect_timeout > 120:
            db_connect_timeout = 120

        admin_postgres_url = os.getenv("ADMIN_POSTGRES_URL", "").strip() or None
        if admin_postgres_url:
            admin_postgres_url = _normalize_postgres_url_for_psycopg(admin_postgres_url)
            admin_postgres_url = rewrite_supabase_direct_db_url_to_pooler(admin_postgres_url)
            admin_postgres_url = _ensure_sslmode_require_for_supabase(admin_postgres_url)

        return Settings(
            app_name=os.getenv("APP_NAME", "EvaluaERP").strip(),
            app_env=app_env_raw,
            app_debug=_to_bool(os.getenv("APP_DEBUG"), default=True),
            app_version=os.getenv("APP_VERSION", "1.0.0").strip(),
            uvicorn_host=uvicorn_host,
            uvicorn_port=uvicorn_port,
            database_url=database_url,
            platform_database_url=platform_database_url,
            admin_postgres_url=admin_postgres_url,
            default_tenant_code=os.getenv("DEFAULT_TENANT_CODE", "athletic").strip(),
            tenant_header_name=os.getenv("TENANT_HEADER_NAME", "X-Tenant-Code").strip(),
            tenant_query_param=os.getenv("TENANT_QUERY_PARAM", "tenant").strip(),
            tenant_cookie_name=os.getenv("TENANT_COOKIE_NAME", "tenant_code").strip(),
            log_level=os.getenv("LOG_LEVEL", "INFO").strip().upper(),
            secret_key=secret_key,
            access_token_expire_minutes=int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "60")),
            auth_cookie_secure=auth_cookie_secure,
            auth_session_max_age_seconds=auth_session_max_age,
            db_connect_timeout_seconds=db_connect_timeout,
            fondo_rendir_cuenta_anticipo=os.getenv("FONDO_RENDIR_CUENTA_ANTICIPO", "").strip(),
            fondo_rendir_cuenta_caja=os.getenv("FONDO_RENDIR_CUENTA_CAJA", "").strip(),
            fondo_rendir_cuenta_gasto=os.getenv("FONDO_RENDIR_CUENTA_GASTO", "").strip(),
        )


settings = Settings.load()