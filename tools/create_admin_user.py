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
    from crud.auth.usuarios import crear_usuario_admin
    from db.session import get_engine
    from sqlalchemy.orm import sessionmaker

    p = argparse.ArgumentParser(description="Alta usuario administrador en auth_usuarios.")
    p.add_argument("--email", required=True, help="Email de acceso (único).")
    p.add_argument("--password", required=True, help="Contraseña (mín. 10 caracteres).")
    p.add_argument("--nombre", default="", help="Nombre para mostrar.")
    args = p.parse_args()

    engine = get_engine(settings.default_tenant_code)
    SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)

    try:
        with SessionLocal() as db:
            u = crear_usuario_admin(
                db,
                email=args.email,
                password=args.password,
                nombre_completo=args.nombre or "",
            )
            db.commit()
            print(f"OK — Usuario creado id={u.id} email={u.email!r}")
    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
