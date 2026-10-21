#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Prepara una instalación local para crear una base PostgreSQL por cliente.

Crea erp_identity, activa TENANCY_MODE=database_per_company y copia los
usuarios de la base operacional. No imprime claves ni URLs.

  python tools/enable_database_per_company.py

Después hay que reiniciar la aplicación y volver a iniciar sesión.
"""
from __future__ import annotations

import os
import re
import secrets
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

IDENTITY_DB = "erp_identity"
_CODE_RE = re.compile(r"^[a-z][a-z0-9_]*$")


def main() -> int:
    os.chdir(ROOT)
    from dotenv import load_dotenv

    load_dotenv(ROOT / ".env")
    admin_url = (os.getenv("ADMIN_POSTGRES_URL") or "").strip()
    database_url = (os.getenv("DATABASE_URL") or "").strip()
    if not admin_url or not database_url:
        print("Faltan ADMIN_POSTGRES_URL y DATABASE_URL en .env.")
        return 1

    created = _ensure_identity_database(admin_url, database_url)
    print("erp_identity", "creada" if created else "ya existía")

    updates = _env_updates(database_url)
    _upsert_env(ROOT / ".env", updates)
    for key, value in updates.items():
        os.environ[key] = value

    _bootstrap_identity(database_url)
    print("Identidad lista. Reinicie EvaluaERP y vuelva a iniciar sesión.")
    return 0


def _ensure_identity_database(admin_url: str, database_url: str) -> bool:
    from sqlalchemy import create_engine, text
    from sqlalchemy.engine.url import make_url

    owner = make_url(database_url).username
    if not owner or not re.match(r"^[A-Za-z_][A-Za-z0-9_]*$", owner):
        raise SystemExit("El usuario de DATABASE_URL no es un identificador válido.")
    admin = create_engine(admin_url, future=True, pool_pre_ping=True)
    try:
        with admin.connect() as conn:
            conn = conn.execution_options(isolation_level="AUTOCOMMIT")
            exists = conn.execute(
                text("SELECT 1 FROM pg_database WHERE datname = :name"),
                {"name": IDENTITY_DB},
            ).scalar()
            if exists:
                return False
            conn.execute(text(f"CREATE DATABASE {IDENTITY_DB} OWNER {owner}"))
            return True
    finally:
        admin.dispose()


def _env_updates(database_url: str) -> dict[str, str]:
    from sqlalchemy.engine.url import make_url

    identity = make_url(database_url).set(database=IDENTITY_DB)
    key = (os.getenv("DB_CREDENTIALS_KEY") or "").strip()
    if len(key) < 32:
        key = secrets.token_hex(32)
    return {
        "TENANCY_MODE": "database_per_company",
        "IDENTITY_DATABASE_URL": identity.render_as_string(hide_password=False),
        "DB_CREDENTIALS_KEY": key,
    }


def _upsert_env(path: Path, updates: dict[str, str]) -> None:
    lines = path.read_text(encoding="utf-8").splitlines() if path.exists() else []
    seen: set[str] = set()
    out: list[str] = []
    for line in lines:
        stripped = line.strip()
        if stripped and not stripped.startswith("#") and "=" in line:
            key = line.split("=", 1)[0].strip()
            if key in updates:
                out.append(f"{key}={updates[key]}")
                seen.add(key)
                continue
        out.append(line)
    if out and out[-1] != "":
        out.append("")
    for key, value in updates.items():
        if key not in seen:
            out.append(f"{key}={value}")
    path.write_text("\n".join(out).rstrip() + "\n", encoding="utf-8")


def _bootstrap_identity(database_url: str) -> None:
    from sqlalchemy import create_engine, select
    from sqlalchemy.engine.url import make_url

    from core.module_catalog import ALL_ASSIGNABLE_KEYS, default_visible_modules_for_roles
    from db.identity_session import get_identity_sessionmaker, init_identity_schema
    from db.schema_revision import ERP_SCHEMA_REVISION
    from models.identity.models import Company, CompanyDatabase, Holding, IdentityUser, Membership
    from services.platform.db_credentials import encrypt_db_secret

    init_identity_schema()
    operational = create_engine(database_url, future=True, pool_pre_ping=True)
    try:
        people = _load_people(operational)
        tenant = _load_tenant(operational)
    finally:
        operational.dispose()

    factory = get_identity_sessionmaker()
    with factory() as db:
        by_email: dict[str, IdentityUser] = {}
        for person in people:
            found = db.scalar(select(IdentityUser).where(IdentityUser.email == person["email"]))
            if found is None:
                found = IdentityUser(
                    email=person["email"],
                    password_hash=person["password_hash"],
                    nombre_completo=person["nombre"],
                    activo=person["activo"],
                    is_platform_admin=person["platform_admin"],
                    session_version=1,
                )
                db.add(found)
                db.flush()
            else:
                found.activo = person["activo"]
                if person["platform_admin"]:
                    found.is_platform_admin = True
            by_email[person["email"]] = found
        db.commit()
        print(f"usuarios de identidad: {len(by_email)}")

        if tenant is None:
            print("No hay un tenant activo para vincular la base actual.")
            return
        code = tenant["code"]
        existing = db.scalar(select(Company).where(Company.code == code))
        if existing is not None:
            print(f"compañía ya vinculada: {code}")
            return
        source = make_url(database_url)
        version = _schema_version(database_url)
        if version != ERP_SCHEMA_REVISION:
            print(
                f"No se vinculó {tenant['database_name']}: "
                f"el esquema es {version or 'desconocido'} y el sistema espera {ERP_SCHEMA_REVISION}."
            )
            return
        holding = db.scalar(select(Holding).where(Holding.code == code))
        if holding is None:
            holding = Holding(code=code, name=tenant["name"][:200], status="ACTIVE")
            db.add(holding)
            db.flush()
        company = Company(
            holding_id=holding.id,
            code=code,
            legal_name=tenant["name"][:200],
            rut="",
            status="ACTIVE",
            status_detail=(
                "La base ya existía. Complete el RUT en la ficha: "
                "public.empresa no tenía razón social."
            ),
            schema_version=version,
        )
        db.add(company)
        db.flush()
        db.add(
            CompanyDatabase(
                company_id=company.id,
                database_name=tenant["database_name"],
                host=source.host or "127.0.0.1",
                port=int(source.port or 5432),
                database_user=tenant["database_user"],
                database_engine="postgresql+psycopg",
                encrypted_secret=encrypt_db_secret(source.password or ""),
                status="ACTIVE",
                schema_version=version,
            )
        )
        for person in people:
            user = by_email[person["email"]]
            db.add(
                Membership(
                    identity_user_id=int(user.id),
                    company_id=int(company.id),
                    access_scope="COMPANY_ADMIN" if person["platform_admin"] else "COMPANY",
                    role_codes=person["roles"],
                    module_keys=person["modules"] or list(default_visible_modules_for_roles(person["roles"])),
                    status="ACTIVE" if person["activo"] else "INACTIVE",
                )
            )
        if any(person["platform_admin"] for person in people):
            admin = next(by_email[p["email"]] for p in people if p["platform_admin"])
            admin_modules = set(ALL_ASSIGNABLE_KEYS)
            membership = db.scalar(
                select(Membership).where(
                    Membership.identity_user_id == admin.id,
                    Membership.company_id == company.id,
                )
            )
            if membership is not None:
                membership.module_keys = sorted(admin_modules)
                membership.role_codes = ["ADMIN"]
        db.commit()
        print(f"base vinculada: {code} -> {tenant['database_name']}")


def _load_people(engine) -> list[dict]:
    from sqlalchemy import text

    from core.module_catalog import default_visible_modules_for_roles

    with engine.connect() as conn:
        users = conn.execute(
            text(
                """
                SELECT id, email, password_hash, nombre_completo, activo
                FROM auth_usuarios
                ORDER BY id
                """
            )
        ).mappings().all()
        people = []
        for row in users:
            roles = conn.execute(
                text(
                    """
                    SELECT r.codigo
                    FROM auth_usuario_rol ur
                    JOIN auth_roles r ON r.id = ur.rol_id
                    WHERE ur.usuario_id = :id
                    ORDER BY r.codigo
                    """
                ),
                {"id": row["id"]},
            ).scalars().all()
            modules = conn.execute(
                text(
                    """
                    SELECT module_key
                    FROM auth_usuario_modulo_visible
                    WHERE usuario_id = :id
                    ORDER BY module_key
                    """
                ),
                {"id": row["id"]},
            ).scalars().all()
            role_codes = [str(item).strip().upper() for item in roles if str(item).strip()]
            if not role_codes:
                role_codes = ["CONSULTA"]
            module_keys = [str(item).strip().upper() for item in modules if str(item).strip()]
            if not module_keys:
                module_keys = sorted(default_visible_modules_for_roles(role_codes))
            people.append(
                {
                    "email": str(row["email"]).strip().lower(),
                    "password_hash": str(row["password_hash"]),
                    "nombre": str(row["nombre_completo"] or row["email"]).strip(),
                    "activo": bool(row["activo"]),
                    "platform_admin": "ADMIN" in role_codes,
                    "roles": role_codes,
                    "modules": module_keys,
                }
            )
        return people


def _load_tenant(engine) -> dict | None:
    from sqlalchemy import text

    with engine.connect() as conn:
        exists = conn.execute(text("SELECT to_regclass('public.tenants')")).scalar()
        if not exists:
            return _tenant_from_database(engine)
        row = conn.execute(
            text(
                """
                SELECT tenant_code, tenant_name, db_name, db_user
                FROM public.tenants
                WHERE is_active IS TRUE
                ORDER BY id
                LIMIT 1
                """
            )
        ).mappings().first()
    if row is None:
        return _tenant_from_database(engine)
    code = str(row["tenant_code"] or "").strip().lower()
    if not _CODE_RE.match(code):
        return _tenant_from_database(engine)
    return {
        "code": code,
        "name": str(row["tenant_name"] or code).strip() or code,
        "database_name": str(row["db_name"]).strip(),
        "database_user": str(row["db_user"]).strip(),
    }


def _tenant_from_database(engine) -> dict | None:
    from sqlalchemy.engine.url import make_url

    url = make_url(str(engine.url))
    name = (url.database or "").strip().lower()
    code = re.sub(r"[^a-z0-9_]", "_", name).strip("_")
    if not code or not code[0].isalpha():
        code = f"empresa_{code}".strip("_")
    code = code[:40]
    if not _CODE_RE.match(code) or not url.username:
        return None
    return {
        "code": code,
        "name": name or code,
        "database_name": url.database or name,
        "database_user": url.username,
    }


def _schema_version(database_url: str) -> str:
    from sqlalchemy import create_engine, text

    engine = create_engine(database_url, future=True, pool_pre_ping=True)
    try:
        with engine.connect() as conn:
            row = conn.execute(
                text("SELECT app_version FROM public.app_metadata ORDER BY id LIMIT 1")
            ).first()
        if row is None:
            return ""
        return str(row[0] or "").strip()
    finally:
        engine.dispose()


if __name__ == "__main__":
    raise SystemExit(main())
