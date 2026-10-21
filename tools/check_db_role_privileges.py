# tools/check_db_role_privileges.py
# -*- coding: utf-8 -*-
"""
Comprueba que la URL indicada no sea un rol con DDL.

Uso (staging, nunca producción a ciegas):
  set EVALUA_APP_DATABASE_URL=postgresql+psycopg://evalua_app:...@host/db
  python tools/check_db_role_privileges.py

Códigos: 0 seguro, 1 inseguro o error, 3 sin URL.
"""
from __future__ import annotations

import os
import sys

from sqlalchemy import create_engine, text

from services.platform.db_role import app_role_is_safe


def main() -> int:
    url = (os.getenv("EVALUA_APP_DATABASE_URL") or "").strip()
    if not url:
        print(
            "BLOQUEADA POR ENTORNO: defina EVALUA_APP_DATABASE_URL con el rol de runtime.",
            file=sys.stderr,
        )
        return 3
    engine = create_engine(url, future=True, pool_pre_ping=True)
    try:
        with engine.connect() as conn:
            can_create = bool(
                conn.execute(
                    text("SELECT has_schema_privilege(current_user, 'public', 'CREATE')")
                ).scalar()
            )
            can_insert = bool(
                conn.execute(
                    text(
                        """
                        SELECT has_table_privilege(
                            current_user, 'public.asientos_contables', 'INSERT'
                        )
                        """
                    )
                ).scalar()
            )
            user = conn.execute(text("SELECT current_user")).scalar()
    except Exception as exc:
        print(f"FAIL: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1
    finally:
        engine.dispose()

    ok, message = app_role_is_safe(can_create=can_create, can_insert=can_insert)
    print(f"user={user} can_create={can_create} can_insert={can_insert}")
    print(message)
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
