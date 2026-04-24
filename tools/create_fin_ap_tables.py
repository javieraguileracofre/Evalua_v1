# tools/create_fin_ap_tables.py
# -*- coding: utf-8 -*-
"""
Crea solo las tablas fin.ap_* (CxP) si no existen — mismo DDL que el ORM.

Útil tras 094_fin_ap_cxp_reset.sql cuando create_all de la app falla por permisos.

Ejemplo (PowerShell, usuario con derecho CREATE en fin y REFERENCES en public.proveedor):

  .\\env\\Scripts\\python.exe tools/create_fin_ap_tables.py --database-url "postgresql+psycopg://postgres:CLAVE@localhost:5432/EVALUA_V1_DB"

Luego (opcional) otorgar ownership a evalua_user y ejecutar 097_fin_ap_post_create_all.sql como postgres.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

import models  # noqa: F401 — registra metadata

from sqlalchemy import create_engine

from models.finanzas.compras_finanzas import (
    APDocumento,
    APDocumentoDetalle,
    APDocumentoImpuesto,
    APPago,
    APPagoAplicacion,
)


def main() -> None:
    parser = argparse.ArgumentParser(description="Crea tablas fin.ap_* si faltan (SQLAlchemy checkfirst).")
    parser.add_argument(
        "--database-url",
        default=None,
        help="URL SQLAlchemy. Si se omite, usa DATABASE_URL del .env (core.config).",
    )
    parser.add_argument(
        "--use-admin-url",
        action="store_true",
        help="Usa ADMIN_POSTGRES_URL del .env (rol con privilegios) en lugar de DATABASE_URL.",
    )
    args = parser.parse_args()

    from core.config import settings

    if args.use_admin_url:
        if not settings.admin_postgres_url:
            raise SystemExit(
                "ADMIN_POSTGRES_URL no está definido en .env. "
                "Añádela o ejecuta los GRANT en 096 como postgres y usa solo DATABASE_URL."
            )
        db_url = settings.admin_postgres_url
    elif args.database_url:
        db_url = args.database_url
    else:
        db_url = settings.database_url

    engine = create_engine(db_url, future=True)
    # Orden por FKs
    tables = [
        APDocumento.__table__,
        APDocumentoDetalle.__table__,
        APDocumentoImpuesto.__table__,
        APPago.__table__,
        APPagoAplicacion.__table__,
    ]
    with engine.begin() as conn:
        for t in tables:
            t.create(conn, checkfirst=True)
            print(f"OK (checkfirst): {t.schema}.{t.name}")


if __name__ == "__main__":
    main()
