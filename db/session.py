# db/session.py
# -*- coding: utf-8 -*-
from __future__ import annotations

from typing import Generator

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session, sessionmaker

from core.config import postgres_engine_connect_args, settings
from core.platform_messages import MSG_DB_DOWN, MSG_SCHEMA_OLD
from db.schema_revision import schema_is_current

_ENGINE_CACHE: dict[str, Engine] = {}
_SESSIONMAKER_CACHE: dict[str, sessionmaker] = {}
_LEGACY_KEY = "__legacy__"


def _legacy_engine() -> Engine:
    if not (settings.database_url or "").strip():
        raise RuntimeError("La instalación legacy no tiene DATABASE_URL.")
    if _LEGACY_KEY not in _ENGINE_CACHE:
        _ENGINE_CACHE[_LEGACY_KEY] = create_engine(
            settings.database_url,
            echo=False,
            future=True,
            pool_pre_ping=True,
            pool_recycle=1800,
            pool_size=5,
            max_overflow=10,
            pool_timeout=30,
            connect_args=postgres_engine_connect_args(
                settings.database_url,
                settings.db_connect_timeout_seconds,
            ),
        )
    return _ENGINE_CACHE[_LEGACY_KEY]


def get_engine(tenant_code: str | None = None) -> Engine:
    """En legacy usa DATABASE_URL. En database_per_company usa solo la compañía autorizada."""
    del tenant_code
    if not settings.database_per_company:
        return _legacy_engine()
    from db.company_engine import CompanyDatabaseUnavailable, get_active_company_engine

    try:
        return get_active_company_engine()
    except CompanyDatabaseUnavailable:
        raise
    except Exception as exc:
        raise CompanyDatabaseUnavailable(MSG_DB_DOWN) from exc


def get_session_local(tenant_code: str | None = None) -> sessionmaker:
    if not settings.database_per_company:
        if _LEGACY_KEY not in _SESSIONMAKER_CACHE:
            _SESSIONMAKER_CACHE[_LEGACY_KEY] = sessionmaker(
                bind=_legacy_engine(),
                autoflush=False,
                autocommit=False,
                future=True,
            )
        return _SESSIONMAKER_CACHE[_LEGACY_KEY]
    from core.company_context import get_company_context
    from db.company_engine import CompanyAccessDenied, get_company_sessionmaker

    ctx = get_company_context()
    if ctx is None or not ctx.authorized:
        raise CompanyAccessDenied(MSG_DB_DOWN)
    if not schema_is_current(ctx.schema_version):
        raise CompanyAccessDenied(MSG_SCHEMA_OLD)
    return get_company_sessionmaker(ctx.company_id)


def get_db() -> Generator[Session, None, None]:
    from db.company_engine import CompanyAccessDenied, CompanyDatabaseUnavailable

    try:
        SessionLocal = get_session_local()
    except (CompanyAccessDenied, CompanyDatabaseUnavailable):
        raise
    db: Session = SessionLocal()
    try:
        yield db
    except SQLAlchemyError as exc:
        db.rollback()
        from sqlalchemy.exc import OperationalError

        if settings.database_per_company and isinstance(exc, OperationalError):
            from db.company_engine import CompanyDatabaseUnavailable

            raise CompanyDatabaseUnavailable(MSG_DB_DOWN) from exc
        raise
    finally:
        db.close()


def get_account_db() -> Generator[Session, None, None]:
    """Recuperación de clave: identidad en database_per_company, operación en legacy."""
    if settings.database_per_company:
        from db.identity_session import get_identity_db

        yield from get_identity_db()
        return
    yield from get_db()


def get_login_db() -> Generator[Session | None, None, None]:
    """El login de plataforma no abre una base de compañía."""
    if settings.database_per_company:
        yield None
        return
    yield from get_db()
