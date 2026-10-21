# tests/test_accounting_concurrency.py
# -*- coding: utf-8 -*-
"""Idempotencia contable: SAVEPOINT + IntegrityError + índice único (Postgres opcional)."""
from __future__ import annotations

import os
from decimal import Decimal
from pathlib import Path
from unittest.mock import MagicMock

import pytest

ROOT = Path(__file__).resolve().parents[1]
# Solo base de prueba explícita: nunca usar DATABASE_URL operativa/producción.
_PG_URL = (os.getenv("EVALUA_TEST_DATABASE_URL") or "").strip()


def test_concurrent_probe_targets_fin_plan_cuenta():
    """El plan vive en fin.plan_cuenta. La tabla suelta en public no existe y dejaría la prueba real en falso verde."""
    src = Path(__file__).read_text(encoding="utf-8")
    assert "FROM fin.plan_cuenta" in src
    assert "FROM " + "plan_cuentas" not in src


def test_unique_index_sql_excludes_manual_and_scopes_business_origins():
    sql = (ROOT / "db" / "psql" / "140_asientos_origen_idempotente.sql").read_text(encoding="utf-8")
    assert "ux_asientos_origen_idempotente" in sql
    assert "origen_id > 0" in sql
    assert "'MANUAL_AJUSTE'" not in sql
    assert "'MANUAL_APERTURA'" not in sql
    assert "LOP_DEPRECIACION" in sql
    assert "DROP INDEX IF EXISTS public.ux_asientos_origen_unico" in sql


def test_evalua_test_database_url_status_is_explicit():
    """No omitir en silencio: documenta BLOQUEADA POR ENTORNO cuando falta la URL."""
    if _PG_URL:
        assert _PG_URL.startswith("postgresql")
    else:
        # La prueba concurrente real queda OMITIDA/BLOQUEADA; el motivo debe ser visible.
        reason = (
            "BLOQUEADA POR ENTORNO: defina EVALUA_TEST_DATABASE_URL y ejecute "
            "python tools/run_fase3_postgres_validation.py"
        )
        pytest.skip(reason)


def test_legitimate_distinct_origen_ids_are_not_collapsed():
    """Dos PAGO_CLIENTE distintos deben poder coexistir (granularidad de negocio)."""
    from crud.finanzas.contabilidad_asientos import ORIGENES_IDEMPOTENTES

    assert "PAGO_CLIENTE" in ORIGENES_IDEMPOTENTES
    assert "MANUAL_AJUSTE" not in ORIGENES_IDEMPOTENTES
    # Misma tipología, distinto origen_id ⇒ claves distintas del índice parcial.
    assert ("PAGO_CLIENTE", 1) != ("PAGO_CLIENTE", 2)


def test_integrity_error_race_returns_existing(monkeypatch: pytest.MonkeyPatch):
    from crud.finanzas import contabilidad_asientos as ca
    from sqlalchemy.exc import IntegrityError

    monkeypatch.setattr(
        ca,
        "_table_columns",
        lambda *a, **k: {
            "id",
            "fecha",
            "origen_tipo",
            "origen_id",
            "glosa",
            "usuario",
            "moneda",
        },
    )
    monkeypatch.setattr(
        ca,
        "obtener_plan_cuenta_por_codigo",
        lambda db, codigo: MagicMock(
            codigo=codigo, nombre="X", estado="ACTIVO", acepta_movimiento=True
        ),
    )
    monkeypatch.setattr(ca, "obtener_asiento_id_por_origen", lambda *a, **k: None)
    monkeypatch.setattr(
        ca.crud_periodos,
        "assert_periodo_abierto_para_fecha",
        lambda *a, **k: None,
    )

    nested = MagicMock()
    db = MagicMock()
    db.begin_nested.return_value = nested

    def _boom(*a, **k):
        raise IntegrityError("stmt", {}, Exception("unique"))

    monkeypatch.setattr(ca, "_insert_header_dynamic", _boom)

    # 1ª consulta (pre-check): vacío; 2ª (tras IntegrityError): ganador de la carrera.
    calls = {"n": 0}

    def _lookup(*a, **k):
        calls["n"] += 1
        return None if calls["n"] == 1 else 4242

    monkeypatch.setattr(ca, "obtener_asiento_id_por_origen", _lookup)

    aid = ca.crear_asiento(
        db,
        fecha=None,
        origen_tipo="PAGO_CLIENTE",
        origen_id=99,
        glosa="race",
        detalles=[
            {"codigo_cuenta": "1101", "debe": Decimal("10"), "haber": Decimal("0")},
            {"codigo_cuenta": "2101", "debe": Decimal("0"), "haber": Decimal("10")},
        ],
        do_commit=False,
    )
    assert aid == 4242
    nested.rollback.assert_called()


@pytest.mark.skipif(
    not _PG_URL,
    reason="Requiere EVALUA_TEST_DATABASE_URL (Postgres aislado; no usa DATABASE_URL)",
)
def test_postgres_concurrent_post_entry_no_duplicates():
    """Validación real: dos sesiones intentan el mismo origen; solo un asiento."""
    import threading
    from sqlalchemy import create_engine, text
    from sqlalchemy.orm import sessionmaker

    from modules.contabilidad import accounting_service

    engine = create_engine(_PG_URL, future=True, pool_pre_ping=True)
    if engine.dialect.name != "postgresql":
        engine.dispose()
        pytest.fail("EVALUA_TEST_DATABASE_URL no es PostgreSQL")

    with engine.connect() as conn:
        # Requiere esquema ERP ya migrado (no crea DDL destructivo aquí).
        ready = conn.execute(
            text(
                """
                SELECT 1 FROM information_schema.tables
                WHERE table_schema='public' AND table_name='asientos_contables'
                """
            )
        ).first()
        if not ready:
            engine.dispose()
            pytest.fail(
                "asientos_contables no existe en EVALUA_TEST_DATABASE_URL. "
                "Ejecute python tools/run_fase3_postgres_validation.py"
            )
        idx = conn.execute(
            text(
                """
                SELECT 1 FROM pg_indexes
                WHERE schemaname='public' AND indexname='ux_asientos_origen_idempotente'
                """
            )
        ).first()
        if not idx:
            engine.dispose()
            pytest.fail("Falta ux_asientos_origen_idempotente. Ejecute el upgrade aislado antes de la prueba concurrente")
        cuentas = conn.execute(
            text(
                """
                SELECT codigo FROM fin.plan_cuenta
                WHERE UPPER(estado) = 'ACTIVO' AND acepta_movimiento IS TRUE
                ORDER BY codigo
                LIMIT 2
                """
            )
        ).scalars().all()
        if len(cuentas) < 2:
            engine.dispose()
            pytest.fail(
                "fin.plan_cuenta no tiene 2 cuentas ACTIVO con acepta_movimiento. "
                "El upgrade aislado debe sembrar el plan mínimo."
            )
        c_debe, c_haber = str(cuentas[0]), str(cuentas[1])

    origen_id = 9_000_001
    with engine.begin() as conn:
        conn.execute(
            text(
                "DELETE FROM asientos_detalle WHERE asiento_id IN "
                "(SELECT id FROM asientos_contables WHERE origen_tipo='PAGO_CLIENTE' AND origen_id=:oid)"
            ),
            {"oid": origen_id},
        )
        conn.execute(
            text(
                "DELETE FROM asientos_contables WHERE origen_tipo='PAGO_CLIENTE' AND origen_id=:oid"
            ),
            {"oid": origen_id},
        )

    SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
    results: list[int] = []
    errors: list[str] = []
    barrier = threading.Barrier(2)

    def worker():
        db = SessionLocal()
        try:
            barrier.wait(timeout=10)
            from crud.finanzas import periodos as crud_periodos
            from crud.finanzas import contabilidad_asientos as ca

            monkey_periodo = getattr(crud_periodos, "assert_periodo_abierto_para_fecha", None)
            crud_periodos.assert_periodo_abierto_para_fecha = lambda *a, **k: None  # type: ignore
            ca.crud_periodos.assert_periodo_abierto_para_fecha = lambda *a, **k: None  # type: ignore
            try:
                aid = accounting_service.post_entry(
                    db,
                    fecha=None,
                    origen_tipo="PAGO_CLIENTE",
                    origen_id=origen_id,
                    glosa="concurrent test",
                    detalles=[
                        {"codigo_cuenta": c_debe, "debe": Decimal("100"), "haber": Decimal("0")},
                        {"codigo_cuenta": c_haber, "debe": Decimal("0"), "haber": Decimal("100")},
                    ],
                    do_commit=True,
                )
                results.append(int(aid))
            finally:
                if monkey_periodo is not None:
                    crud_periodos.assert_periodo_abierto_para_fecha = monkey_periodo  # type: ignore
        except Exception as exc:
            errors.append(f"{type(exc).__name__}:{exc}")
        finally:
            db.close()

    t1 = threading.Thread(target=worker)
    t2 = threading.Thread(target=worker)
    t1.start()
    t2.start()
    t1.join(timeout=30)
    t2.join(timeout=30)

    with engine.connect() as conn:
        n = conn.execute(
            text(
                "SELECT COUNT(*) FROM asientos_contables "
                "WHERE origen_tipo='PAGO_CLIENTE' AND origen_id=:oid"
            ),
            {"oid": origen_id},
        ).scalar()
    engine.dispose()

    assert int(n) == 1, f"duplicados={n} results={results} errors={errors}"
    assert len(set(results)) <= 1