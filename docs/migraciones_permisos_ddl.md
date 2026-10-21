# Migraciones Alembic — permisos DDL y operación

## Separación de roles (recomendado)

| Rol | Uso | Privilegios mínimos |
|-----|-----|---------------------|
| App (`evalua_app`) | runtime FastAPI | `SELECT/INSERT/UPDATE/DELETE` sobre tablas operativas; **sin** DDL |
| Migrador (`evalua_migrator`) | `tools/upgrade_company_schema.py` / Alembic | `CREATE/ALTER/INDEX` en schemas `public`/`fin`; ownership de objetos creados |
| Backup | `pg_dump` | lectura + posible `REPLICATION` según política |

No conceder `SUPERUSER` a la cuenta de aplicación.

## Antecedente local (permisos DDL)

Errores del tipo `InsufficientPrivilege` / `permiso denegado a la tabla …` durante `create_all` o `AUTO_MIGRATE` suelen indicar:

1. Usuario operativo sin DDL (correcto en prod; incorrecto si se usa AUTO_MIGRATE).
2. Objetos creados por otro rol (ownership) que impiden `ALTER`/`CREATE INDEX`.
3. Confusión entre identity DB y company DB.

**Solución operativa:** desactivar `AUTO_MIGRATE_ON_STARTUP` en prod y migrar con el rol migrador:

```bash
# Con DATABASE_URL / URL de empresa apuntando al rol migrador
python tools/upgrade_company_schema.py --legacy
# o
python tools/upgrade_company_schema.py --company CODIGO
```

## Validación en staging (checklist)

1. Base PostgreSQL aislada (no producción).
2. `python tools/upgrade_company_schema.py --status`
3. Upgrade a head (`0006_domain_event_outbox`).
4. Re-ejecutar upgrade → sin cambios pendientes.
5. Verificar `app_metadata.app_version`.
6. Verificar índice `ux_asientos_origen_idempotente` y tabla `domain_event_outbox`.
7. Probar advisory lock: dos upgrades concurrentes → uno espera/falla controlado.

Estado en esta fase: pruebas unitarias/mocks de upgrade + cadena Alembic **validadas en CI** (head `0009_fase_d_libros_tesoreria`).

Upgrade real contra Postgres aislado: ejecutar:

```bash
python tools/preflight_asientos_duplicados.py
python tools/run_fase3_postgres_validation.py
```

Requiere `EVALUA_TEST_DATABASE_URL`. En la sesión de Fase 3 del agente esa variable estaba **UNSET** → validación **BLOQUEADA POR ENTORNO**.
