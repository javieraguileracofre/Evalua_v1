# tools/upgrade_company_schema.py
# -*- coding: utf-8 -*-
"""
Upgrade canónico de esquema ERP.

Uso:
  # Inventario (multiempresa)
  python tools/upgrade_company_schema.py --status

  # Una compañía
  python tools/upgrade_company_schema.py --company acme

  # Todas las ACTIVE desactualizadas
  python tools/upgrade_company_schema.py --all

  # Modo legacy (DATABASE_URL)
  python tools/upgrade_company_schema.py --legacy

No imprime URLs ni secretos.
"""
from __future__ import annotations

import argparse
import sys


def _status() -> int:
    from db.identity_session import get_identity_sessionmaker
    from services.platform.schema_upgrade import list_schema_status
    from db.schema_revision import ERP_SCHEMA_REVISION

    db = get_identity_sessionmaker()()
    try:
        rows = list_schema_status(db)
    finally:
        db.close()
    print(f"esperado={ERP_SCHEMA_REVISION}")
    outdated = 0
    for row in rows:
        flag = "OK" if row.is_current else "OUTDATED"
        if row.needs_upgrade:
            outdated += 1
        print(
            f"{flag} code={row.code} status={row.status} "
            f"identity={row.identity_version or '—'} "
            f"dbreg={row.database_version or '—'} "
            f"runtime={row.runtime_version or '—'} "
            f"{row.detail}"
        )
    print(f"total={len(rows)} needs_upgrade={outdated}")
    return 0


def _upgrade_one(code: str) -> int:
    from sqlalchemy import select

    from db.identity_session import get_identity_sessionmaker
    from models.identity.models import Company
    from services.platform.schema_upgrade import upgrade_company

    db = get_identity_sessionmaker()()
    try:
        company = db.execute(
            select(Company).where(Company.code == code.strip().lower())
        ).scalar_one_or_none()
        if company is None:
            print(f"error: compañía '{code}' no encontrada")
            return 1
        result = upgrade_company(db, int(company.id))
        print(
            f"{'OK' if result.ok else 'FAIL'} code={result.code} "
            f"revision={result.revision or '—'} {result.detail}"
        )
        return 0 if result.ok else 2
    finally:
        db.close()


def _upgrade_all() -> int:
    from db.identity_session import get_identity_sessionmaker
    from services.platform.schema_upgrade import list_schema_status, upgrade_company

    db = get_identity_sessionmaker()()
    try:
        rows = [r for r in list_schema_status(db) if r.needs_upgrade]
        if not rows:
            print("nada que actualizar")
            return 0
        failed = 0
        for row in rows:
            result = upgrade_company(db, row.company_id)
            print(
                f"{'OK' if result.ok else 'FAIL'} code={result.code} "
                f"revision={result.revision or '—'} {result.detail}"
            )
            if not result.ok:
                failed += 1
        return 2 if failed else 0
    finally:
        db.close()


def _upgrade_legacy() -> int:
    from core.config import settings
    from services.platform.schema_upgrade import upgrade_legacy_database

    url = (settings.database_url or "").strip()
    if not url:
        print("error: DATABASE_URL no configurada (modo legacy)")
        return 1
    try:
        rev = upgrade_legacy_database(url)
        print(f"OK legacy revision={rev}")
        return 0
    except Exception as exc:
        print(f"FAIL legacy error={type(exc).__name__}")
        return 2


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Upgrade de esquema Evalua ERP")
    g = parser.add_mutually_exclusive_group(required=True)
    g.add_argument("--status", action="store_true", help="Inventario de versiones")
    g.add_argument("--company", metavar="CODE", help="Actualiza una compañía por código")
    g.add_argument("--all", action="store_true", help="Actualiza todas las desactualizadas")
    g.add_argument("--legacy", action="store_true", help="Migrar DATABASE_URL (TENANCY_MODE=legacy)")
    args = parser.parse_args(argv)

    if args.status:
        return _status()
    if args.company:
        return _upgrade_one(args.company)
    if args.all:
        return _upgrade_all()
    if args.legacy:
        return _upgrade_legacy()
    return 1


if __name__ == "__main__":
    sys.exit(main())
