#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Vacía datos de tablas (TRUNCATE ... RESTART IDENTITY CASCADE) excepto maestros definidos.

Por defecto conserva:
  - public.clientes
  - public.proveedor
  - public.proveedor_banco
  - public.proveedor_contacto
  - public.proveedor_direccion
  - fin.proveedor_fin

Modo seguro:
  - Sin --execute solo muestra qué tablas truncaría (dry-run).
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from sqlalchemy import text

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from db.session import get_engine


DEFAULT_KEEP = {
    "public.clientes",
    "public.proveedor",
    "public.proveedor_banco",
    "public.proveedor_contacto",
    "public.proveedor_direccion",
    "fin.proveedor_fin",
}

SYSTEM_KEEP = {
    "information_schema",
    "pg_catalog",
}


def qident(name: str) -> str:
    return '"' + name.replace('"', '""') + '"'


def parse_keep(values: list[str]) -> set[str]:
    out = set(DEFAULT_KEEP)
    for item in values:
        val = item.strip()
        if not val:
            continue
        if "." not in val:
            val = f"public.{val}"
        out.add(val.lower())
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description="Purge de datos: vacía todo excepto clientes/proveedores.")
    ap.add_argument("--tenant", default=None, help="Código tenant (default del sistema).")
    ap.add_argument(
        "--schema",
        action="append",
        default=["public", "fin"],
        help="Schema a considerar (repetible). Default: public y fin.",
    )
    ap.add_argument(
        "--keep",
        action="append",
        default=[],
        help="Tabla a conservar (schema.tabla o tabla). Repetible.",
    )
    ap.add_argument(
        "--execute",
        action="store_true",
        help="Ejecuta TRUNCATE. Sin esta bandera solo imprime plan.",
    )
    args = ap.parse_args()

    keep = parse_keep(args.keep)
    schemas = sorted({s.strip() for s in args.schema if s.strip() and s.strip() not in SYSTEM_KEEP})
    if not schemas:
        raise SystemExit("No hay schemas válidos.")

    engine = get_engine(args.tenant)
    with engine.connect() as conn:
        rows = conn.execute(
            text(
                """
                SELECT table_schema, table_name
                FROM information_schema.tables
                WHERE table_type = 'BASE TABLE'
                  AND table_schema = ANY(:schemas)
                ORDER BY table_schema, table_name
                """
            ),
            {"schemas": schemas},
        ).mappings().all()

    all_tables = [f"{r['table_schema']}.{r['table_name']}".lower() for r in rows]
    to_truncate = [t for t in all_tables if t not in keep]

    print("Schemas:", ", ".join(schemas))
    print("Conservar:")
    for t in sorted(keep):
        print("  -", t)
    print(f"\nTablas encontradas: {len(all_tables)}")
    print(f"Tablas a truncar: {len(to_truncate)}")
    for t in to_truncate:
        print("  *", t)

    if not args.execute:
        print("\n[DRY-RUN] No se ejecutó TRUNCATE. Use --execute para aplicar.")
        return 0

    if not to_truncate:
        print("Nada que truncar.")
        return 0

    sql_tables = []
    for full in to_truncate:
        sch, tab = full.split(".", 1)
        sql_tables.append(f"{qident(sch)}.{qident(tab)}")

    truncate_sql = f"TRUNCATE TABLE {', '.join(sql_tables)} RESTART IDENTITY CASCADE"
    with engine.begin() as conn:
        conn.exec_driver_sql(truncate_sql)

    print("\nOK: purge ejecutado correctamente.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

