# tests/test_finanzas_db_optional.py
# -*- coding: utf-8 -*-
"""
Smoke de esquema sobre la base aislada.

Usa solo EVALUA_TEST_DATABASE_URL. No lee la URL operativa.
"""
from __future__ import annotations

import os
from pathlib import Path

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session, sessionmaker

_PG_URL = (os.getenv("EVALUA_TEST_DATABASE_URL") or "").strip()
_NEEDS_PG = pytest.mark.skipif(
    not _PG_URL,
    reason="Requiere EVALUA_TEST_DATABASE_URL (Postgres aislado; no usa la URL operativa)",
)


def test_smoke_aislado_no_abre_la_url_operativa():
    src = Path(__file__).read_text(encoding="utf-8")
    assert "get_" + "session_local" not in src
    assert 'getenv("' + "DATABASE_URL" + '"' not in src
    assert "getenv('" + "DATABASE_URL" + "'" not in src


@pytest.fixture()
def db_session() -> Session:
    engine = create_engine(_PG_URL, future=True, pool_pre_ping=True)
    db = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)()
    try:
        yield db
    finally:
        db.close()
        engine.dispose()


@_NEEDS_PG
def test_asientos_contables_tabla_accesible(db_session: Session) -> None:
    r = db_session.execute(
        text(
            """
            SELECT 1 FROM information_schema.tables
            WHERE table_schema = 'public' AND table_name = 'asientos_contables'
            LIMIT 1
            """
        )
    ).scalar()
    assert r == 1


@_NEEDS_PG
def test_listar_asientos_no_explota(db_session: Session) -> None:
    from crud.finanzas import contabilidad_asientos as crud_asientos

    rows = crud_asientos.listar_asientos(db_session, limit=5)
    assert isinstance(rows, list)
