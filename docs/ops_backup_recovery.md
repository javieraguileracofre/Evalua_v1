# Operación: respaldos y recuperación

Procedimientos verificables alineados con `services/operacion/database_backup_service.py` y UI Admin → Backups.

## Respaldo

| Objetivo | Acción |
|----------|--------|
| Base identity | `pg_dump` de `IDENTITY_DATABASE_URL` (modo company) o backup completo en legacy |
| Una empresa | Backup de la base registrada en `CompanyDatabase` (nunca URL arbitraria del cliente) |
| Metadatos | Registrar en `ops_database_backup` vía UI/admin existente |

## Restauración

1. Restaurar el dump sobre una base nueva o staging (no sobreescribir producción sin ventana).
2. Verificar conectividad y `SELECT 1`.
3. Ejecutar `python tools/upgrade_company_schema.py --company CODIGO` si el dump es anterior al head.
4. Verificar `app_metadata.app_version` = `ERP_SCHEMA_REVISION`.
5. Smoke: login, selector de empresa, hub finanzas/leasing.

## Restricciones

- No restaurar dumps entre empresas distintas sin revisión legal/operativa.
- Downgrade Alembic de `0004` no es seguro: recuperación = restore de backup.
- Simulacros deben usarse en entornos no productivos.
