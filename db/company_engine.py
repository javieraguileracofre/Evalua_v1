# db/company_engine.py
# -*- coding: utf-8 -*-
"""Un engine por compañía. No abre otra base si la seleccionada falla."""
from __future__ import annotations

from urllib.parse import quote_plus

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import sessionmaker

from core.company_context import get_company_context
from core.config import postgres_engine_connect_args, settings
from core.platform_messages import MSG_DB_DOWN, MSG_NO_ACCESS, MSG_NO_COMPANY

_ENGINES: dict[int, Engine] = {}
_MAKERS: dict[int, sessionmaker] = {}
_MAX_ENGINES = 32


class CompanyAccessDenied(RuntimeError):
    pass


class CompanyDatabaseUnavailable(RuntimeError):
    pass


def invalidate_company_engine(company_id: int) -> None:
    maker = _MAKERS.pop(int(company_id), None)
    engine = _ENGINES.pop(int(company_id), None)
    if engine is not None:
        engine.dispose()
    del maker


def _evict_if_needed() -> None:
    while len(_ENGINES) > _MAX_ENGINES:
        oldest = next(iter(_ENGINES))
        invalidate_company_engine(oldest)


def build_company_url(*, engine_name: str, database_name: str, host: str, port: int, user: str, secret: str) -> str:
    if engine_name == "sqlite":
        return f"sqlite:///{database_name}"
    password = quote_plus(secret)
    driver = engine_name or "postgresql+psycopg"
    return f"{driver}://{quote_plus(user)}:{password}@{host}:{int(port)}/{database_name}"


def _load_record(company_id: int):
    from sqlalchemy import select

    from db.identity_session import get_identity_sessionmaker
    from models.identity.models import CompanyDatabase

    db = get_identity_sessionmaker()()
    try:
        row = db.execute(
            select(CompanyDatabase).where(CompanyDatabase.company_id == int(company_id))
        ).scalar_one_or_none()
        if row is None:
            return None
        return {
            "database_name": row.database_name,
            "host": row.host,
            "port": int(row.port),
            "database_user": row.database_user,
            "database_engine": row.database_engine,
            "encrypted_secret": row.encrypted_secret,
            "status": row.status,
        }
    finally:
        db.close()


def get_company_engine(company_id: int) -> Engine:
    """Abre solo la base de company_id. Un fallo no consulta otra compañía."""
    cid = int(company_id)
    record = _load_record(cid)
    if record is None or record["status"] != "ACTIVE":
        invalidate_company_engine(cid)
        raise CompanyAccessDenied(MSG_NO_ACCESS)
    cached = _ENGINES.get(cid)
    if cached is not None:
        return cached
    engine: Engine | None = None
    try:
        secret = ""
        if record["database_engine"] != "sqlite":
            from services.platform.db_credentials import decrypt_db_secret

            secret = decrypt_db_secret(record["encrypted_secret"])
        url = build_company_url(
            engine_name=record["database_engine"],
            database_name=record["database_name"],
            host=record["host"],
            port=record["port"],
            user=record["database_user"],
            secret=secret,
        )
        kwargs: dict = {
            "echo": False,
            "future": True,
            "pool_pre_ping": True,
            "pool_recycle": 1800,
            "pool_timeout": 30,
        }
        if record["database_engine"] != "sqlite":
            kwargs["pool_size"] = 5
            kwargs["max_overflow"] = 10
            kwargs["connect_args"] = postgres_engine_connect_args(url, settings.db_connect_timeout_seconds)
        engine = create_engine(url, **kwargs)
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
    except CompanyAccessDenied:
        if engine is not None:
            engine.dispose()
        raise
    except Exception as exc:
        if engine is not None:
            engine.dispose()
        raise CompanyDatabaseUnavailable(MSG_DB_DOWN) from exc
    _ENGINES[cid] = engine
    _evict_if_needed()
    return engine


def get_company_sessionmaker(company_id: int) -> sessionmaker:
    cid = int(company_id)
    maker = _MAKERS.get(cid)
    if maker is None:
        maker = sessionmaker(bind=get_company_engine(cid), autoflush=False, autocommit=False, future=True)
        _MAKERS[cid] = maker
    return maker


def get_active_company_engine() -> Engine:
    ctx = get_company_context()
    if ctx is None or not ctx.authorized:
        raise CompanyAccessDenied(MSG_NO_COMPANY)
    return get_company_engine(ctx.company_id)
