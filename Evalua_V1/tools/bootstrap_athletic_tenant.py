# tools/bootstrap_athletic_tenant.py
# -*- coding: utf-8 -*-
from __future__ import annotations

from db.tenant_registry import get_platform_sessionmaker, register_tenant


def main() -> None:
    PlatformSession = get_platform_sessionmaker()

    with PlatformSession() as db:
        register_tenant(
            db,
            tenant_code="athletic",
            tenant_name="Athletic",
            db_driver="postgresql+psycopg",
            db_host="localhost",
            db_port=5432,
            db_name="evalua_v1_db",
            db_user="evalua_user",
            db_password="CAMBIAR_EN_PRODUCCION",
            db_sslmode=None,
        )
        db.commit()

    print("Athletic registrado como tenant por defecto.")


if __name__ == "__main__":
    main()