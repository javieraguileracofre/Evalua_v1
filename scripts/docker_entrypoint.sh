#!/bin/sh
# Arranque contenedor: migraciones explícitas (nunca AUTO_MIGRATE implícito en prod).
set -eu

TENANCY_MODE="${TENANCY_MODE:-legacy}"
AUTO_MIGRATE_ON_STARTUP="${AUTO_MIGRATE_ON_STARTUP:-false}"

if [ "$AUTO_MIGRATE_ON_STARTUP" = "true" ] || [ "$AUTO_MIGRATE_ON_STARTUP" = "1" ]; then
  echo "WARN: AUTO_MIGRATE_ON_STARTUP=true no se usa en entrypoint; preferir alembic/tools."
fi

if [ "$TENANCY_MODE" = "legacy" ]; then
  if [ -n "${DATABASE_URL:-}" ]; then
    echo "Migrando esquema legacy (alembic upgrade head)..."
    python tools/upgrade_company_schema.py --legacy
  else
    echo "WARN: TENANCY_MODE=legacy sin DATABASE_URL; se omite migración."
  fi
else
  echo "TENANCY_MODE=$TENANCY_MODE: company DBs se migran con tools/upgrade_company_schema.py o Admin → Empresas."
fi

exec uvicorn main:app --host "${UVICORN_HOST:-0.0.0.0}" --port "${PORT:-8000}"
