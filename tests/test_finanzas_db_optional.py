# tests/test_finanzas_db_optional.py
# -*- coding: utf-8 -*-
"""
Consultas mínimas a BD si existe DATABASE_URL (saltadas en entornos sin Postgres).

Sirve como smoke de esquema en CI con base de datos de prueba.
"""
from __future__ import annotations

import os

import pytest
from sqlalchemy import text
from sqlalchemy.orm import Session

pytestmark = pytest.mark.skipif(
    not os.getenv("DATABASE_URL", "").strip(),
    reason="DATABASE_URL no definida; omitiendo integración",
)


@pytest.fixture()
def db_session() -> Session:
    from db.session import get_session_local

    SessionLocal = get_session_local()
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


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


def test_listar_asientos_no_explota(db_session: Session) -> None:
    from crud.finanzas import contabilidad_asientos as crud_asientos

    rows = crud_asientos.listar_asientos(db_session, limit=5)
    assert isinstance(rows, list)
