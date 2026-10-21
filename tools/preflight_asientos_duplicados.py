# tools/preflight_asientos_duplicados.py
# -*- coding: utf-8 -*-
"""
Detecta asientos duplicados por (origen_tipo, origen_id) que impedirían la
migración 0005 (ux_asientos_origen_idempotente).

Uso:
  set EVALUA_TEST_DATABASE_URL=postgresql+psycopg://...
  python tools/preflight_asientos_duplicados.py

  # o modo legacy (solo si se entiende el riesgo)
  python tools/preflight_asientos_duplicados.py --url-env DATABASE_URL

No elimina ni modifica datos.
"""
from __future__ import annotations

import argparse
import os
import sys

from sqlalchemy import create_engine, text

_ORIGENES = (
    "AP_DOCUMENTO",
    "AP_PAGO",
    "NOTA_VENTA",
    "NOTA_VENTA_ANULACION",
    "PAGO_CLIENTE",
    "LEASING_FIN_ACTIVACION",
    "LOP_ACTIVACION",
    "LOP_FACTURACION",
    "FONDO_RENDIR_ENT",
    "FONDO_RENDIR_LIQ",
    "REMUNERACION_PROVISION",
    "REMUNERACION_PAGO",
    "REV_MANUAL",
    "INVENTARIO_MOV",
    "LOP_DEPRECIACION",
)

# Lista estática confiable (no input de usuario).
_ORIGENES_SQL = ", ".join(f"'{o}'" for o in _ORIGENES)
_SQL = f"""
SELECT origen_tipo, origen_id, COUNT(*)::int AS n, array_agg(id ORDER BY id) AS ids
FROM public.asientos_contables
WHERE origen_id > 0
  AND origen_tipo IN ({_ORIGENES_SQL})
GROUP BY origen_tipo, origen_id
HAVING COUNT(*) > 1
ORDER BY n DESC, origen_tipo, origen_id
LIMIT 100
"""


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Preflight duplicados de asientos por origen")
    parser.add_argument(
        "--url-env",
        default="EVALUA_TEST_DATABASE_URL",
        help="Nombre de variable de entorno con URL (default EVALUA_TEST_DATABASE_URL)",
    )
    args = parser.parse_args(argv)
    url = (os.getenv(args.url_env) or "").strip()
    if not url:
        print(
            f"BLOQUEADA: variable {args.url_env} no configurada.\n"
            "Ejemplo:\n"
            "  set EVALUA_TEST_DATABASE_URL=postgresql+psycopg://user:pass@127.0.0.1:5432/evalua_fase3_test\n"
            "  python tools/preflight_asientos_duplicados.py",
            file=sys.stderr,
        )
        return 3
    engine = create_engine(url, future=True, pool_pre_ping=True)
    try:
        if engine.dialect.name != "postgresql":
            print("error: solo PostgreSQL", file=sys.stderr)
            return 2
        with engine.connect() as conn:
            rows = conn.execute(text(_SQL)).mappings().all()
    finally:
        engine.dispose()

    if not rows:
        print("OK: sin duplicados incompatibles con ux_asientos_origen_idempotente")
        return 0

    print(f"CONFLICTOS={len(rows)} (no se eliminan datos)")
    for r in rows:
        print(f"  {r['origen_tipo']}/{r['origen_id']} n={r['n']} ids={list(r['ids'])}")
    print(
        "Acción: revise contablemente cada grupo y resuelva manualmente "
        "antes de aplicar Alembic 0005+."
    )
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
