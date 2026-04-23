# tools/create_tenant_database.py
# -*- coding: utf-8 -*-
from __future__ import annotations

import argparse
import re
from pathlib import Path

from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session, sessionmaker

from core.config import settings
from db.tenant_registry import get_platform_sessionmaker, register_tenant


IDENTIFIER_RE = re.compile(r"^[a-zA-Z_][a-zA-Z0-9_]*$")


def validate_identifier(value: str, field_name: str) -> str:
    if not IDENTIFIER_RE.match(value):
        raise ValueError(
            f"{field_name}='{value}' no es válido. "
            "Usa solo letras, números y guion bajo, comenzando con letra o _."
        )
    return value


def run_sql_file(engine, path: Path) -> None:
    sql = path.read_text(encoding="utf-8")
    with engine.connect() as conn:
        conn = conn.execution_options(isolation_level="AUTOCOMMIT")
        conn.exec_driver_sql(sql)


def main() -> None:
    parser = argparse.ArgumentParser(description="Crear base tenant para EvaluaERP")
    parser.add_argument("--tenant-code", required=True)
    parser.add_argument("--tenant-name", required=True)
    parser.add_argument("--db-name", required=True)
    parser.add_argument("--db-user", required=True)
    parser.add_argument("--db-password", required=True)
    parser.add_argument("--db-host", default="localhost")
    parser.add_argument("--db-port", type=int, default=5432)
    parser.add_argument("--db-driver", default="postgresql+psycopg")
    parser.add_argument("--db-sslmode", default="")
    args = parser.parse_args()

    tenant_code = validate_identifier(args.tenant_code.lower(), "tenant_code")
    db_name = validate_identifier(args.db_name, "db_name")
    db_user = validate_identifier(args.db_user, "db_user")

    if not settings.admin_postgres_url:
        raise RuntimeError("ADMIN_POSTGRES_URL no está configurado.")

    admin_engine = create_engine(settings.admin_postgres_url, future=True)

    create_user_sql = text(f"CREATE USER {db_user} WITH PASSWORD :pwd")
    create_db_sql = text(f"CREATE DATABASE {db_name} OWNER {db_user}")

    with admin_engine.connect() as conn:
        conn = conn.execution_options(isolation_level="AUTOCOMMIT")

        user_exists = conn.execute(
            text("SELECT 1 FROM pg_roles WHERE rolname = :name"),
            {"name": db_user},
        ).scalar()

        if not user_exists:
            conn.execute(create_user_sql, {"pwd": args.db_password})

        db_exists = conn.execute(
            text("SELECT 1 FROM pg_database WHERE datname = :name"),
            {"name": db_name},
        ).scalar()

        if not db_exists:
            conn.execute(create_db_sql)

    tenant_url = (
        f"{args.db_driver}://{db_user}:{args.db_password}@"
        f"{args.db_host}:{args.db_port}/{db_name}"
    )
    if args.db_sslmode:
        tenant_url += f"?sslmode={args.db_sslmode}"

    tenant_engine = create_engine(tenant_url, future=True)

    base_sql_files = [
        Path("db/psql/001_tenant_base.sql"),
        Path("db/psql/002_tenant_security.sql"),
        Path("db/psql/00_install_fin.sql"),
        Path("db/psql/70_fin_dashboard_views.sql"),
        Path("db/psql/80_fin_roles_grants.sql"),
        Path("db/psql/81_fin_periodos_cierre.sql"),
        Path("db/psql/82_fin_lock_periodo_triggers.sql"),
        Path("db/psql/83_fin_presupuesto.sql"),
        Path("db/psql/84_fin_conciliacion_bancaria.sql"),
        Path("db/psql/85_fin_admin_only_periodos.sql"),
        Path("db/psql/086_fin_foreign_keys.sql"),
        Path("db/psql/087_fin_updated_at_triggers.sql"),
    ]

    for sql_file in base_sql_files:
        if sql_file.exists():
            run_sql_file(tenant_engine, sql_file)

    PlatformSession = get_platform_sessionmaker()
    with PlatformSession() as db:
        register_tenant(
            db,
            tenant_code=tenant_code,
            tenant_name=args.tenant_name,
            db_driver=args.db_driver,
            db_host=args.db_host,
            db_port=args.db_port,
            db_name=db_name,
            db_user=db_user,
            db_password=args.db_password,
            db_sslmode=args.db_sslmode or None,
        )
        db.commit()

    print("=" * 80)
    print("TENANT CREADO CORRECTAMENTE")
    print("=" * 80)
    print(f"tenant_code : {tenant_code}")
    print(f"tenant_name : {args.tenant_name}")
    print(f"db_name     : {db_name}")
    print(f"db_user     : {db_user}")
    print("=" * 80)


if __name__ == "__main__":
    main()