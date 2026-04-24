# db/tenant_registry.py
# -*- coding: utf-8 -*-
from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache
from urllib.parse import quote_plus

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import sessionmaker

from core.config import postgres_engine_connect_args, settings


@dataclass(frozen=True)
class TenantRecord:
    tenant_code: str
    tenant_name: str
    db_driver: str
    db_host: str
    db_port: int
    db_name: str
    db_user: str
    db_password: str
    db_sslmode: str | None
    is_active: bool


@lru_cache(maxsize=1)
def get_platform_engine() -> Engine:
    return create_engine(
        settings.platform_database_url,
        echo=False,
        future=True,
        pool_pre_ping=True,
        pool_timeout=30,
        connect_args=postgres_engine_connect_args(
            settings.platform_database_url,
            settings.db_connect_timeout_seconds,
        ),
    )


@lru_cache(maxsize=1)
def get_platform_sessionmaker():
    return sessionmaker(
        bind=get_platform_engine(),
        autoflush=False,
        autocommit=False,
        future=True,
    )


def get_tenant_record(tenant_code: str) -> TenantRecord | None:
    sql = text(
        """
        SELECT
            tenant_code,
            tenant_name,
            db_driver,
            db_host,
            db_port,
            db_name,
            db_user,
            db_password,
            db_sslmode,
            is_active
        FROM public.tenants
        WHERE tenant_code = :tenant_code
        LIMIT 1
        """
    )

    SessionLocal = get_platform_sessionmaker()
    with SessionLocal() as db:
        row = db.execute(sql, {"tenant_code": tenant_code}).mappings().first()

    if not row:
        return None

    return TenantRecord(
        tenant_code=row["tenant_code"],
        tenant_name=row["tenant_name"],
        db_driver=row["db_driver"],
        db_host=row["db_host"],
        db_port=row["db_port"],
        db_name=row["db_name"],
        db_user=row["db_user"],
        db_password=row["db_password"],
        db_sslmode=row["db_sslmode"],
        is_active=row["is_active"],
    )


def build_database_url(record: TenantRecord) -> str:
    password = quote_plus(record.db_password)
    ssl_raw = (record.db_sslmode or "").strip()
    # Supabase exige TLS desde Internet; sin sslmode psycopg puede colgar hasta connect_timeout.
    host_lo = (record.db_host or "").lower()
    if not ssl_raw and (
        "supabase.co" in host_lo or "pooler.supabase.com" in host_lo
    ):
        ssl_raw = "require"
    ssl_q = f"?sslmode={quote_plus(ssl_raw)}" if ssl_raw else ""

    return (
        f"{record.db_driver}://{record.db_user}:{password}"
        f"@{record.db_host}:{record.db_port}/{record.db_name}{ssl_q}"
    )


def _single_db_tenant_fallback_enabled() -> bool:
    """Un solo Postgres (p. ej. Supabase): sin fila en public.tenants, usar DATABASE_URL."""
    return os.getenv("EVALUA_SINGLE_DB_TENANT", "").strip().lower() in (
        "1",
        "true",
        "yes",
        "on",
    )


def get_database_url_for_tenant(tenant_code: str) -> str:
    record = get_tenant_record(tenant_code)
    if record is None:
        if _single_db_tenant_fallback_enabled():
            return settings.database_url
        raise RuntimeError(f"No existe tenant_code='{tenant_code}' en la base platform.")
    if not record.is_active:
        raise RuntimeError(f"El tenant '{tenant_code}' está inactivo.")
    return build_database_url(record)