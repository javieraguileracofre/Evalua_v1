#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Crea el primer usuario administrador (rol ADMIN).
Ejecutar desde la raíz del proyecto con .env configurado:

  python tools/create_admin_user.py --email admin@empresa.cl --password "ClaveSegura123" --nombre "Administrador"
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def main() -> int:
    import os

    os.chdir(ROOT)
    from dotenv import load_dotenv

    load_dotenv(ROOT / ".env")

    from core.config import settings

    p = argparse.ArgumentParser(description="Alta del primer administrador.")
    p.add_argument("--email", required=True, help="Email de acceso (único).")
    p.add_argument("--password", required=True, help="Contraseña (mín. 10 caracteres, con letras y números).")
    p.add_argument("--nombre", default="", help="Nombre para mostrar.")
    args = p.parse_args()

    if settings.database_per_company:
        return _create_platform_admin(args.email, args.password, args.nombre)
    return _create_legacy_admin(args.email, args.password, args.nombre)


def _create_platform_admin(email: str, password: str, nombre: str) -> int:
    from crud.auth.usuarios import hash_password
    from db.identity_session import get_identity_sessionmaker, init_identity_schema
    from models.identity.models import IdentityUser
    from sqlalchemy import select

    init_identity_schema()
    factory = get_identity_sessionmaker()
    with factory() as db:
        existing = db.scalar(select(IdentityUser).where(IdentityUser.email == email.strip().lower()))
        if existing is not None:
            existing.is_platform_admin = True
            existing.activo = True
            db.commit()
            print(f"OK — Administrador de plataforma ya existía id={existing.id}")
            return 0
        user = IdentityUser(
            email=email.strip().lower(),
            password_hash=hash_password(password),
            nombre_completo=(nombre or "").strip(),
            activo=True,
            is_platform_admin=True,
        )
        db.add(user)
        db.commit()
        print(f"OK — Administrador de plataforma id={user.id}")
    return 0


def _create_legacy_admin(email: str, password: str, nombre: str) -> int:
    from crud.auth.usuarios import crear_usuario_admin
    from db.session import get_engine
    from sqlalchemy.orm import sessionmaker

    engine = get_engine(None)
    SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
    try:
        with SessionLocal() as db:
            u = crear_usuario_admin(
                db,
                email=email,
                password=password,
                nombre_completo=nombre or "",
            )
            db.commit()
            print(f"OK — Usuario creado id={u.id} email={u.email!r}")
    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
