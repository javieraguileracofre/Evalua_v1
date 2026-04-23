#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Bootstrap de Supabase: esquema mínimo (000–002), fila tenants, create_all, usuario ADMIN.

  cd Evalua_V1
  python tools/supabase_bootstrap.py

Credenciales (en orden de prioridad):
  1) DATABASE_URL en .env
  2) DB_HOST + DB_USER + DB_PASSWORD + DB_NAME (+ DB_PORT, DB_SSLMODE opcionales), igual que core.config
  3) DB_PASSWORD (o --db-password) + SUPABASE_PROJECT_REF / --project-ref:
     usuario DB_USER o postgres, host db.<ref>.supabase.co si DB_HOST vacío

La fila en public.tenants usa el mismo usuario/host/bd que la conexión resuelta
(para que la app coincida con tu .env).
"""
from __future__ import annotations

import argparse
import os
import sys
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import quote_plus

ROOT = Path(__file__).resolve().parent.parent
PSQL_DIR = ROOT / "db" / "psql"

DEFAULT_PROJECT_REF = "qtrqsdabrpxitmqvqdko"
DEFAULT_TENANT = "athletic"
MASTER_EMAIL = "javier.aguilera@evaluasoluciones.cl"
MASTER_PASSWORD = "Evalua1234##"
MASTER_NAME = "Javier Aguilera"


@dataclass(frozen=True)
class ResolvedDb:
    sqlalchemy_url: str
    user: str
    password_plain: str
    host: str
    port: int
    db_name: str
    sslmode: str | None


def _load_dotenv() -> None:
    try:
        from dotenv import load_dotenv

        load_dotenv(ROOT / ".env")
    except ImportError:
        pass


def _build_url(
    host: str,
    user: str,
    password: str,
    db_name: str,
    port: int,
    sslmode: str | None,
) -> str:
    quser = quote_plus(user)
    qpwd = quote_plus(password)
    qdb = quote_plus(db_name)
    base = f"postgresql+psycopg://{quser}:{qpwd}@{host}:{port}/{qdb}"
    if sslmode:
        base += f"?sslmode={quote_plus(sslmode)}"
    return base


def _from_database_url(url: str) -> ResolvedDb:
    from sqlalchemy.engine.url import make_url

    u = make_url(url)
    pwd = u.password or ""
    user = u.username or ""
    host = u.host or ""
    port = int(u.port or 5432)
    dbn = u.database or ""
    sslmode = None
    if u.query:
        q = dict(u.query)
        sslmode = (q.get("sslmode") or "").strip() or None
    return ResolvedDb(
        sqlalchemy_url=url,
        user=user,
        password_plain=str(pwd),
        host=host,
        port=port,
        db_name=dbn,
        sslmode=sslmode,
    )


def _from_full_db_env() -> ResolvedDb | None:
    host = os.getenv("DB_HOST", "").strip()
    user = os.getenv("DB_USER", "").strip()
    password = os.getenv("DB_PASSWORD", "").strip()
    name = os.getenv("DB_NAME", "").strip()
    port_str = (os.getenv("DB_PORT") or "5432").strip() or "5432"
    if not host or not user or not password or not name:
        return None
    port = int(port_str)
    sslmode = os.getenv("DB_SSLMODE", "").strip() or None
    url = _build_url(host, user, password, name, port, sslmode)
    return ResolvedDb(
        sqlalchemy_url=url,
        user=user,
        password_plain=password,
        host=host,
        port=port,
        db_name=name,
        sslmode=sslmode,
    )


def _from_password_and_ref(args: argparse.Namespace) -> ResolvedDb | None:
    pwd = (getattr(args, "db_password", None) or "").strip() or os.getenv(
        "DB_PASSWORD", ""
    ).strip()
    if not pwd:
        return None
    ref = (
        (args.project_ref or os.getenv("SUPABASE_PROJECT_REF") or DEFAULT_PROJECT_REF)
        .strip()
        or DEFAULT_PROJECT_REF
    )
    host = os.getenv("DB_HOST", "").strip() or f"db.{ref}.supabase.co"
    user = os.getenv("DB_USER", "").strip() or "postgres"
    name = os.getenv("DB_NAME", "").strip() or "postgres"
    port = int((os.getenv("DB_PORT") or "5432").strip() or "5432")
    ssl_raw = os.getenv("DB_SSLMODE", "").strip()
    if ssl_raw:
        sslmode: str | None = ssl_raw
    else:
        sslmode = "require" if "supabase.co" in host.lower() else None
    url = _build_url(host, user, pwd, name, port, sslmode)
    return ResolvedDb(
        sqlalchemy_url=url,
        user=user,
        password_plain=pwd,
        host=host,
        port=port,
        db_name=name,
        sslmode=sslmode,
    )


def resolve_connection(args: argparse.Namespace) -> ResolvedDb | None:
    _load_dotenv()
    du = os.getenv("DATABASE_URL", "").strip()
    if du:
        return _from_database_url(du)
    full = _from_full_db_env()
    if full:
        return full
    return _from_password_and_ref(args)


def _run_sql_file(engine, path: Path) -> None:
    sql = path.read_text(encoding="utf-8")
    if not sql.strip():
        return
    # No usar begin(): no se puede pasar a AUTOCOMMIT dentro de una transacción ya abierta.
    with engine.connect() as conn:
        conn = conn.execution_options(isolation_level="AUTOCOMMIT")
        conn.exec_driver_sql(sql)


def _upsert_tenant(engine, r: ResolvedDb) -> None:
    from sqlalchemy import text

    with engine.begin() as conn:
        conn.execute(
            text(
                """
                INSERT INTO public.tenants (
                    tenant_code, tenant_name, db_driver, db_host, db_port,
                    db_name, db_user, db_password, db_sslmode, is_active
                ) VALUES (
                    :code, :name, 'postgresql+psycopg', :host, :port,
                    :dbname, :dbuser, :pwd, :sslmode, TRUE
                )
                ON CONFLICT (tenant_code) DO UPDATE SET
                    tenant_name = EXCLUDED.tenant_name,
                    db_driver = EXCLUDED.db_driver,
                    db_host = EXCLUDED.db_host,
                    db_port = EXCLUDED.db_port,
                    db_name = EXCLUDED.db_name,
                    db_user = EXCLUDED.db_user,
                    db_password = EXCLUDED.db_password,
                    db_sslmode = EXCLUDED.db_sslmode,
                    is_active = EXCLUDED.is_active,
                    updated_at = NOW()
                """
            ),
            {
                "code": DEFAULT_TENANT,
                "name": "Evalua (Supabase)",
                "host": r.host,
                "port": r.port,
                "dbname": r.db_name,
                "dbuser": r.user,
                "pwd": r.password_plain,
                "sslmode": r.sslmode,
            },
        )


def main() -> int:
    p = argparse.ArgumentParser(
        description="Bootstrap BD + usuario maestro (lee .env: DATABASE_URL o DB_*)."
    )
    p.add_argument(
        "--db-password",
        default="",
        help="Contraseña (si no está en DB_PASSWORD / DATABASE_URL en .env).",
    )
    p.add_argument(
        "--project-ref",
        default=os.getenv("SUPABASE_PROJECT_REF", DEFAULT_PROJECT_REF),
        help=f"Ref Supabase si no hay DB_HOST. Por defecto: {DEFAULT_PROJECT_REF}",
    )
    p.add_argument(
        "--skip-sql",
        action="store_true",
        help="No ejecutar 000/001/002 (si ya los aplicaste en SQL Editor).",
    )
    args = p.parse_args()

    resolved = resolve_connection(args)
    if not resolved:
        print(
            "Error: define DATABASE_URL, o DB_HOST+DB_USER+DB_PASSWORD+DB_NAME, "
            "o DB_PASSWORD (y opcionalmente DB_USER, SUPABASE_PROJECT_REF) en .env; "
            "o pasa --db-password.",
            file=sys.stderr,
        )
        return 1

    url = resolved.sqlalchemy_url

    os.environ.setdefault("APP_ENV", "development")
    os.environ.setdefault("APP_DEBUG", "true")
    os.environ.setdefault(
        "SECRET_KEY",
        "bootstrap-script-dev-key-min-32-characters-long!!",
    )
    os.environ["DATABASE_URL"] = url
    os.environ["PLATFORM_DATABASE_URL"] = url
    os.environ["DEFAULT_TENANT_CODE"] = DEFAULT_TENANT

    from sqlalchemy import create_engine

    engine = create_engine(
        url,
        future=True,
        pool_pre_ping=True,
        connect_args={"connect_timeout": 25},
    )

    files = [
        PSQL_DIR / "000_platform_registry.sql",
        PSQL_DIR / "001_tenant_base.sql",
        PSQL_DIR / "002_tenant_security.sql",
    ]
    for f in files:
        if not f.is_file():
            print(f"Error: no existe {f}", file=sys.stderr)
            return 1

    try:
        if not args.skip_sql:
            for f in files:
                print(f"Aplicando {f.name}...")
                _run_sql_file(engine, f)
        print("Registrando tenant en public.tenants...")
        _upsert_tenant(engine, resolved)
    except Exception as exc:
        print(f"Error SQL / tenant: {exc}", file=sys.stderr)
        return 1
    finally:
        engine.dispose()

    import db.session as db_session
    import db.tenant_registry as tenant_registry

    tenant_registry.get_platform_engine.cache_clear()
    tenant_registry.get_platform_sessionmaker.cache_clear()
    db_session._ENGINE_CACHE.clear()
    db_session._SESSIONMAKER_CACHE.clear()

    import models  # noqa: F401 — registra metadatos
    from db.base_class import Base
    from db.session import get_engine
    from db.startup_schema import ensure_auth_roles_seed

    print("Creando tablas SQLAlchemy (create_all) y roles...")
    try:
        eng = get_engine(DEFAULT_TENANT)
        Base.metadata.create_all(bind=eng)
        ensure_auth_roles_seed(eng)
    except Exception as exc:
        print(f"Error create_all / roles: {exc}", file=sys.stderr)
        return 1

    from sqlalchemy.orm import sessionmaker

    from crud.auth.usuarios import crear_usuario_admin, get_usuario_por_email

    SessionLocal = sessionmaker(bind=eng, autoflush=False, autocommit=False, future=True)
    try:
        with SessionLocal() as db:
            existing = get_usuario_por_email(db, MASTER_EMAIL)
            if existing:
                print(f"Usuario ya existe: {MASTER_EMAIL!r} (id={existing.id}). No se duplica.")
            else:
                crear_usuario_admin(
                    db,
                    email=MASTER_EMAIL,
                    password=MASTER_PASSWORD,
                    nombre_completo=MASTER_NAME,
                )
                db.commit()
                print(f"Usuario maestro creado: {MASTER_EMAIL!r}")
    except Exception as exc:
        print(f"Error usuario maestro: {exc}", file=sys.stderr)
        return 1

    print("Listo. Arranca la app con el mismo .env (DATABASE_URL o DB_*).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
