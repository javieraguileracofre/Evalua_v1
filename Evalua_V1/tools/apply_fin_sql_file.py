# tools/apply_fin_sql_file.py
# -*- coding: utf-8 -*-
"""
Ejecuta un script SQL contra PostgreSQL (p. ej. db/psql/093_fin_ap_documento_contabilidad.sql).

CxP / ORM requieren columnas en fin.ap_documento; el rol de la app a veces no puede ALTER.
En ese caso aplique el SQL con un usuario con privilegios (p. ej. postgres) sobre la MISMA
base de datos que usa el tenant, usando --database-url.

Ejemplo (PowerShell, misma BD que el tenant pero usuario postgres):
  $u = "postgresql+psycopg://postgres:SU_CLAVE@localhost:5432/nombre_bd_tenant"
  .\\env\\Scripts\\python.exe tools/apply_fin_sql_file.py --database-url $u

O con psql (desde la raíz del repo):
  psql -h localhost -U postgres -d nombre_bd_tenant -f db/psql/093_fin_ap_documento_contabilidad.sql
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from sqlalchemy import create_engine

from core.config import settings
from db.tenant_registry import get_database_url_for_tenant


def run_sql_file(database_url: str, path: Path) -> None:
    sql = path.read_text(encoding="utf-8")
    engine = create_engine(database_url, future=True)
    with engine.connect() as conn:
        conn = conn.execution_options(isolation_level="AUTOCOMMIT")
        conn.exec_driver_sql(sql)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Aplica un archivo SQL (AUTOCOMMIT). Use --database-url con postgres si el rol de la app no puede ALTER.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "sql_file",
        nargs="?",
        default="db/psql/093_fin_ap_documento_contabilidad.sql",
        type=Path,
        help="Ruta al .sql (por defecto: migración CxP contabilidad AP)",
    )
    parser.add_argument(
        "--tenant-code",
        default=None,
        help=f"Solo si no usa --database-url: tenant en plataforma (default: {settings.default_tenant_code})",
    )
    parser.add_argument(
        "--database-url",
        default=None,
        metavar="URL",
        help="URL SQLAlchemy postgresql+psycopg://usuario:clave@host:puerto/base (dueño/superusuario). Misma BD que el tenant.",
    )
    args = parser.parse_args()

    path: Path = args.sql_file
    if not path.is_file():
        raise SystemExit(f"No existe el archivo: {path.resolve()}")

    if args.database_url and str(args.database_url).strip():
        url = str(args.database_url).strip()
        print(f"Aplicando {path} con URL explícita (usuario privilegiado) …")
    else:
        tenant = (args.tenant_code or settings.default_tenant_code or "").strip()
        if not tenant:
            raise SystemExit(
                "Defina --tenant-code / DEFAULT_TENANT_CODE, o bien --database-url con un superusuario."
            )
        url = get_database_url_for_tenant(tenant)
        print(f"Aplicando {path} en tenant {tenant!r} (URL del tenant) …")

    run_sql_file(url, path)
    print("Listo.")


if __name__ == "__main__":
    main()
