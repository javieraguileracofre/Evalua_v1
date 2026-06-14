#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Aplica migraciones LOP 108/109 en PostgreSQL (Supabase o local).

  python tools/apply_lop_migrations.py

Usa ADMIN_POSTGRES_URL o DATABASE_URL del .env (clave actual del panel Supabase).
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

try:
    from dotenv import load_dotenv

    load_dotenv(ROOT / ".env")
except ImportError:
    pass

from sqlalchemy import create_engine, text

from core.config import settings
from db.startup_schema import (
    _has_column,
    _has_table,
    ensure_leasing_operativo_schema,
)


def _resolve_url() -> str:
    url = (settings.admin_postgres_url or settings.database_url or "").strip()
    if not url:
        raise SystemExit("Configure DATABASE_URL o ADMIN_POSTGRES_URL en .env")
    if url.startswith("postgresql://"):
        url = url.replace("postgresql://", "postgresql+psycopg://", 1)
    return url


def main() -> None:
    engine = create_engine(_resolve_url(), pool_pre_ping=True)
    with engine.connect() as conn:
        conn.execute(text("SELECT 1"))
    print("Conexión OK")
    print("moneda:", _has_column(engine, schema="public", table="leasing_op_contrato", column="moneda"))
    print("gestion_evento:", _has_table(engine, schema="public", table="leasing_op_gestion_evento"))
    ensure_leasing_operativo_schema(engine)
    print("Tras migración:")
    print("moneda:", _has_column(engine, schema="public", table="leasing_op_contrato", column="moneda"))
    print("gestion_evento:", _has_table(engine, schema="public", table="leasing_op_gestion_evento"))
    print("dias_mora:", _has_column(engine, schema="public", table="leasing_op_cuota", column="dias_mora"))
    print("Listo.")


if __name__ == "__main__":
    main()
