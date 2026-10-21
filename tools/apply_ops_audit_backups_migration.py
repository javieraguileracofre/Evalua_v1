# tools/apply_ops_audit_backups_migration.py
# -*- coding: utf-8 -*-
"""Aplica db/psql/137_ops_audit_backups.sql y sincroniza Alembic a 0002."""
from __future__ import annotations

from sqlalchemy import text

from core.config import settings
from db.session import get_engine
from db.startup_schema import ensure_ops_audit_backups_schema


def main() -> int:
    engine = get_engine()
    print("dialect:", engine.dialect.name)
    print("tenancy:", settings.tenancy_mode)

    with engine.connect() as conn:
        before = conn.execute(
            text(
                """
                SELECT table_name FROM information_schema.tables
                WHERE table_schema='public'
                  AND table_name IN ('auth_audit_event','ops_database_backup','alembic_version')
                ORDER BY 1
                """
            )
        ).fetchall()
        print("before:", [r[0] for r in before])
        try:
            ver = conn.execute(text("SELECT version_num FROM alembic_version")).fetchall()
            print("alembic_version before:", [r[0] for r in ver])
        except Exception as exc:
            print("alembic_version before: (none)", type(exc).__name__)

    print("Applying ensure_ops_audit_backups_schema...")
    ensure_ops_audit_backups_schema(engine)

    with engine.connect() as conn:
        after = conn.execute(
            text(
                """
                SELECT table_name FROM information_schema.tables
                WHERE table_schema='public'
                  AND table_name IN ('auth_audit_event','ops_database_backup','alembic_version')
                ORDER BY 1
                """
            )
        ).fetchall()
        print("after ensure:", [r[0] for r in after])

    from alembic import command
    from alembic.config import Config

    cfg = Config("alembic.ini")
    # ConfigParser interpreta '%' — escapar sin imprimir la URL (puede contener secretos).
    db_url = (settings.database_url or "").replace("%", "%%")
    cfg.set_main_option("sqlalchemy.url", db_url)
    print("Running alembic upgrade head...")
    try:
        command.upgrade(cfg, "head")
        print("alembic upgrade: OK")
    except Exception as exc:
        print("alembic upgrade error:", type(exc).__name__)
        with engine.connect() as conn:
            tables = {
                r[0]
                for r in conn.execute(
                    text(
                        """
                        SELECT table_name FROM information_schema.tables
                        WHERE table_schema='public'
                          AND table_name IN ('auth_audit_event','ops_database_backup')
                        """
                    )
                ).fetchall()
            }
        if tables == {"auth_audit_event", "ops_database_backup"}:
            print("Tables present; ensuring alembic_version + stamp 0002...")
            with engine.begin() as conn:
                conn.execute(
                    text(
                        """
                        CREATE TABLE IF NOT EXISTS alembic_version (
                            version_num VARCHAR(32) NOT NULL
                        )
                        """
                    )
                )
                count = conn.execute(text("SELECT count(*) FROM alembic_version")).scalar()
                if int(count or 0) == 0:
                    conn.execute(
                        text("INSERT INTO alembic_version (version_num) VALUES ('0002_ops_audit_backups')")
                    )
                else:
                    conn.execute(
                        text("UPDATE alembic_version SET version_num = '0002_ops_audit_backups'")
                    )
            print("alembic stamp: OK")
        else:
            print("Missing tables after ensure; abort.")
            return 1

    with engine.connect() as conn:
        try:
            ver = conn.execute(text("SELECT version_num FROM alembic_version")).fetchall()
            print("alembic_version after:", [r[0] for r in ver])
        except Exception as exc:
            print("alembic_version after: (none)", type(exc).__name__)
            return 1
        cols_audit = conn.execute(
            text(
                """
                SELECT column_name FROM information_schema.columns
                WHERE table_schema='public' AND table_name='auth_audit_event'
                ORDER BY ordinal_position
                """
            )
        ).fetchall()
        cols_bak = conn.execute(
            text(
                """
                SELECT column_name FROM information_schema.columns
                WHERE table_schema='public' AND table_name='ops_database_backup'
                ORDER BY ordinal_position
                """
            )
        ).fetchall()
        print("auth_audit_event cols:", [c[0] for c in cols_audit])
        print("ops_database_backup cols:", [c[0] for c in cols_bak])
        if not cols_audit or not cols_bak:
            print("ERROR: tablas no creadas")
            return 1
    print("MIGRATION_OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
