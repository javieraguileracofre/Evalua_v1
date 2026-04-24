# db/session.py
# -*- coding: utf-8 -*-
from __future__ import annotations

from typing import Generator

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session, sessionmaker

from core.config import postgres_engine_connect_args, settings
from core.tenant import get_current_tenant_code
from db.tenant_registry import get_database_url_for_tenant


_ENGINE_CACHE: dict[str, Engine] = {}
_SESSIONMAKER_CACHE: dict[str, sessionmaker] = {}


def _resolve_tenant_code(explicit_tenant_code: str | None = None) -> str:
    code = explicit_tenant_code or get_current_tenant_code() or settings.default_tenant_code
    return (code or settings.default_tenant_code).strip().lower()


def get_engine(tenant_code: str | None = None) -> Engine:
    resolved_tenant = _resolve_tenant_code(tenant_code)

    if resolved_tenant not in _ENGINE_CACHE:
        database_url = get_database_url_for_tenant(resolved_tenant)
        _ENGINE_CACHE[resolved_tenant] = create_engine(
            database_url,
            echo=False,
            future=True,
            pool_pre_ping=True,
            pool_timeout=30,
            connect_args=postgres_engine_connect_args(
                database_url,
                settings.db_connect_timeout_seconds,
            ),
        )

    return _ENGINE_CACHE[resolved_tenant]


def get_session_local(tenant_code: str | None = None) -> sessionmaker:
    resolved_tenant = _resolve_tenant_code(tenant_code)

    if resolved_tenant not in _SESSIONMAKER_CACHE:
        _SESSIONMAKER_CACHE[resolved_tenant] = sessionmaker(
            bind=get_engine(resolved_tenant),
            autoflush=False,
            autocommit=False,
            future=True,
        )

    return _SESSIONMAKER_CACHE[resolved_tenant]


def get_db() -> Generator[Session, None, None]:
    SessionLocal = get_session_local()
    db: Session = SessionLocal()

    try:
        yield db
    except SQLAlchemyError:
        db.rollback()
        raise
    finally:
        db.close()