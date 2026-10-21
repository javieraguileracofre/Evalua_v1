# tools/run_fase3_postgres_validation.py
# -*- coding: utf-8 -*-
"""
Validación operativa Fase 3 sobre PostgreSQL aislado.

Requiere EXCLUSIVAMENTE:
  EVALUA_TEST_DATABASE_URL=postgresql+psycopg://...

Pasos:
  1) Preflight duplicados de asientos
  2) alembic upgrade head (vía upgrade_database_url)
  3) Verificar índice ux_asientos_origen_idempotente y tabla outbox
  4) pytest concurrencia + outbox (si aplica)

No usa DATABASE_URL. No toca producción.
Código de salida:
  0 OK
  1 fallo de validación
  3 entorno bloqueado (sin EVALUA_TEST_DATABASE_URL)
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    url = (os.getenv("EVALUA_TEST_DATABASE_URL") or "").strip()
    if not url:
        print(
            "BLOQUEADA POR ENTORNO: EVALUA_TEST_DATABASE_URL no está definida.\n\n"
            "Pasos sugeridos (Windows / Postgres local):\n"
            "  1) Crear BD desechable (rol con DDL):\n"
            "       CREATE DATABASE evalua_fase3_test;\n"
            "  2) set EVALUA_TEST_DATABASE_URL=postgresql+psycopg://USER:PASS@127.0.0.1:5432/evalua_fase3_test\n"
            "  3) python tools/run_fase3_postgres_validation.py\n\n"
            "No use DATABASE_URL de producción/desarrollo operativo.",
            file=sys.stderr,
        )
        return 3

    env = os.environ.copy()
    env["EVALUA_TEST_DATABASE_URL"] = url
    # Evitar que pytest/app lean otra URL por accidente en subprocesses sensibles.
    env.pop("DATABASE_URL", None)

    print("== 1) Preflight duplicados ==")
    r1 = subprocess.run(
        [sys.executable, str(ROOT / "tools" / "preflight_asientos_duplicados.py")],
        cwd=str(ROOT),
        env=env,
    )
    if r1.returncode not in (0, 1):
        # 1 = conflictos (upgrade fallará); igual intentamos reportar.
        if r1.returncode == 3:
            return 3
    if r1.returncode == 1:
        print("FAIL: hay duplicados; no se aplica upgrade automático.", file=sys.stderr)
        return 1

    print("== 2) Alembic upgrade head ==")
    from services.platform.schema_upgrade import upgrade_database_url
    from db.schema_revision import ERP_SCHEMA_REVISION, runtime_schema_version, schema_is_current
    from sqlalchemy import create_engine, text

    try:
        rev = upgrade_database_url(url)
    except Exception as exc:
        print(f"FAIL upgrade: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1
    print(f"upgrade_revision={rev} expected={ERP_SCHEMA_REVISION}")

    print("== 3) Catálogo PostgreSQL ==")
    engine = create_engine(url, future=True, pool_pre_ping=True)
    try:
        runtime = runtime_schema_version(engine)
        with engine.connect() as conn:
            idx = conn.execute(
                text(
                    "SELECT 1 FROM pg_indexes WHERE schemaname='public' "
                    "AND indexname='ux_asientos_origen_idempotente'"
                )
            ).first()
            outbox = conn.execute(
                text(
                    "SELECT 1 FROM information_schema.tables "
                    "WHERE table_schema='public' AND table_name='domain_event_outbox'"
                )
            ).first()
            corr = conn.execute(
                text(
                    "SELECT 1 FROM pg_indexes WHERE schemaname='public' "
                    "AND indexname='ux_domain_event_outbox_correlation'"
                )
            ).first()
        print(f"runtime_app_version={runtime or '—'}")
        print(f"index_ux_asientos_origen_idempotente={'OK' if idx else 'MISSING'}")
        print(f"table_domain_event_outbox={'OK' if outbox else 'MISSING'}")
        print(f"index_ux_domain_event_outbox_correlation={'OK' if corr else 'MISSING'}")
        if not schema_is_current(runtime) or not idx or not outbox:
            return 1
    finally:
        engine.dispose()

    print("== 4) Pytest concurrencia (Postgres) ==")
    r4 = subprocess.run(
        [
            sys.executable,
            "-m",
            "pytest",
            "tests/test_accounting_concurrency.py",
            "tests/test_finanzas_db_optional.py",
            "tests/test_schema_migration_canonical.py",
            "-q",
            "--tb=short",
        ],
        cwd=str(ROOT),
        env=env,
    )
    if r4.returncode != 0:
        return 1

    print("OK: validación Fase 3 sobre EVALUA_TEST_DATABASE_URL completada")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
