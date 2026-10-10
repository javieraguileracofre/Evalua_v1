# db/identity_session.py
# -*- coding: utf-8 -*-
from __future__ import annotations

from functools import lru_cache
from typing import Generator

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session, sessionmaker

from core.config import postgres_engine_connect_args, settings
from db.identity_base import IdentityBase


def _identity_url() -> str:
    url = (settings.identity_database_url or "").strip()
    if not url:
        raise RuntimeError("IDENTITY_DATABASE_URL no está configurada.")
    return url


@lru_cache(maxsize=1)
def get_identity_engine() -> Engine:
    url = _identity_url()
    connect_args = {}
    if url.startswith("postgres"):
        connect_args = postgres_engine_connect_args(url, settings.db_connect_timeout_seconds)
    return create_engine(
        url,
        echo=False,
        future=True,
        pool_pre_ping=True,
        pool_recycle=1800,
        pool_timeout=30,
        connect_args=connect_args,
    )


@lru_cache(maxsize=1)
def get_identity_sessionmaker() -> sessionmaker:
    return sessionmaker(bind=get_identity_engine(), autoflush=False, autocommit=False, future=True)


def get_identity_db() -> Generator[Session, None, None]:
    db = get_identity_sessionmaker()()
    try:
        yield db
    except SQLAlchemyError:
        db.rollback()
        raise
    finally:
        db.close()


def init_identity_schema() -> None:
    import models.identity.models  # noqa: F401

    IdentityBase.metadata.create_all(bind=get_identity_engine())
