# Informe de evolución arquitectónica — EvaluaERP

**Fecha:** 2026-10-10 (actualizado fase 3)  
**Rama de trabajo:** `chore/schema-ops-hardening` (+ cambios locales de esta fase)  
**Clasificación de preparación:** **APTO CON RESTRICCIONES** (ver § Fase 3 — no asciende a APTO)

---

## 1. Estado inicial

- Modular monolith en transición (`erp_platform` + `modules` + `services`/`crud`/`routes`).
- Alembic head en `0003_lop_residual_engine`; SQL 132–136/138 solo vía `startup_schema` / AUTO_MIGRATE.
- Contabilidad: varios dominios ya usaban `AccountingService`; CxP, UI contable y seed llamaban `crear_asiento` directo.
- Event bus con catálogo amplio; solo ventas emitía eventos.
- Routers UI muy grandes (LOP/LF/contabilidad) con orquestación embebida.
- Multiempresa `legacy` + `database_per_company` ya implementados con pruebas de aislamiento.

## 2. Problemas identificados

1. Dos caminos de esquema (Alembic vs parches de arranque).
2. Frontera contable incompleta.
3. Commits internos en flujos de pago (doble commit potencial).
4. Eventos de dominio subutilizados.
5. `modules/` demasiado delgados (re-exports).
6. Observabilidad sin correlación `request_id` / company / actor.
7. API de integración sin versión estable `/api/v1`.

## 3. Arquitectura final (implementada)

```
HTTP / Jinja / API v1
        ↓
modules.<dominio>          (casos de uso públicos)
        ↓
services / crud
        ↓
AccountingService → contabilidad_asientos (único writer)
        ↓
erp_platform (RBAC, tenancy, events, audit)
        ↓
PostgreSQL (identity + company DBs) / legacy DATABASE_URL
```

## 4. Decisiones tomadas

| Decisión | Razón |
|----------|--------|
| Nueva revisión Alembic `0004_platform_auth_mail_lf_lop` | Absorber SQL ya existentes sin editar migraciones desplegadas |
| Idempotencia por origen en `crear_asiento` | Evitar duplicados por reintentos en orígenes de negocio |
| Emisión de eventos tras commit en pagos | No acoplar notificaciones a TX parcial |
| Advisory lock en upgrade | Evitar migraciones concurrentes |
| No reescritura de routers LOP/LF completos | Riesgo alto; extracción incremental vía contratos `modules.leasing` |
| No microservicios / no cambio de stack | Principio innegociable |

## 5. Archivos principales modificados / creados

### Migraciones / schema
- `alembic/versions/0004_platform_auth_mail_lf_lop.py` **(nuevo)**
- `db/schema_revision.py`
- `services/platform/schema_upgrade.py`

### Contabilidad
- `modules/contabilidad/accounting_service.py`
- `crud/finanzas/contabilidad_asientos.py`
- `crud/finanzas/cuentas_por_pagar.py`
- `crud/finanzas/contabilidad.py`
- `routes/ui/contabilidad.py`
- `tools/seed_opening_balance.py`
- `services/cobranza/pago_service.py`
- `services/leasing_financiero_contabilidad.py`
- `services/leasing_operativo_contabilidad.py`

### Módulos / eventos
- `modules/bootstrap.py`
- `modules/cobranza/__init__.py`
- `modules/finanzas/__init__.py`
- `modules/leasing/activation.py`
- `modules/leasing/financiero.py`
- `modules/leasing/operativo.py`
- `routes/ui/cobranza.py`
- `crud/comercial/leasing_fin.py`

### API / observabilidad
- `routes/api/v1/*` **(nuevo)**
- `core/request_context.py` **(nuevo)**
- `core/observability_middleware.py` **(nuevo)**
- `main.py`

### Pruebas / CI / docs
- `tests/test_accounting_boundary_and_invariants.py`
- `tests/test_schema_migration_canonical.py`
- `tests/test_erp_process_matrix.py`
- `tests/test_architecture_boundaries.py`
- `tests/test_schema_upgrade.py`
- `.github/workflows/ci.yml`
- `docs/arquitectura_modular.md`
- `docs/mapa_procesos_erp.md`
- este informe

## 6. Contratos creados o consolidados

| Contrato | Ubicación |
|----------|-----------|
| Contabilización | `AccountingService.post_entry` / `reverse_manual_entry` / `find_by_origen` |
| CxP | `modules.finanzas.registrar_documento_ap` / `registrar_pago_ap` |
| Cobranza | `modules.cobranza.registrar_pago_cliente` |
| Activación leasing | `modules.leasing.activation` |
| API | `/api/v1/meta`, `/session`, `/accounting/*`, `/leasing/capabilities` |

## 7. Migraciones incorporadas

Ver sección **Informe de migraciones** más abajo.

## 8. Flujos contables refactorizados

- CxP documento y pago → `AccountingService`
- Asiento manual / reversión UI → `AccountingService`
- Seed apertura → `AccountingService`
- Pago cliente: `do_commit=False` + commit único + `PagoRealizado`
- Activación LF/LOP: evento `ContratoLeasingActivado`

## 9. Transacciones modificadas

- `contabilizar_pago_cliente`: un solo commit de negocio
- CxP ya usaba `do_commit=False` (preservado vía facade)
- Policy: casos de uso coordinan commit; CRUD internos participan con `do_commit=False`

## 10. Eventos implementados

| Evento | Estado |
|--------|--------|
| `VentaConfirmada` / `VentaAnulada` | Existente |
| `ContratoLeasingActivado` | Emitido LF/LOP + handler bootstrap |
| `PagoRealizado` | Emitido tras commit + handler bootstrap |

## 11. Cambios en tenancy

- Sin cambio de contrato `legacy` / `database_per_company`
- Sin empresas hardcodeadas
- Upgrade multiempresa con advisory lock
- Pruebas existentes de aislamiento preservadas

## 12–13. Pruebas ejecutadas y resultados

Comando principal:

```bash
python -m pytest \
  tests/test_architecture_boundaries.py \
  tests/test_schema_revision_alembic.py \
  tests/test_schema_migration_canonical.py \
  tests/test_accounting_boundary_and_invariants.py \
  tests/test_erp_process_matrix.py \
  tests/test_leasing_financiero_contabilidad.py \
  tests/test_http_smoke.py \
  tests/test_database_per_company.py \
  tests/test_security_hardening.py \
  tests/test_schema_upgrade.py -q
```

| Resultado | Detalle |
|-----------|---------|
| Aprobadas | Suite anterior + nuevas (tras ajuste advisory lock) |
| Fallidas corregidas | `test_upgrade_database_url_aplica_alembic_y_sella` (doble dispose) |
| Bloqueos ambientales | `create_app` con `AUTO_MIGRATE=true` en BD local sin permisos DDL (`leasing_op_simulacion`) — no usado en CI (`AUTO_MIGRATE_ON_STARTUP=false`) |
| Suite completa del repo | No ejecutada íntegramente en esta sesión (volumen + dependencia opcional de Postgres) |

## 14. Riesgos pendientes

1. Routers LOP/LF/contabilidad siguen >1000 líneas (extracción parcial).
2. `startup_schema` aún puede aplicar parches en dev con AUTO_MIGRATE (compatibilidad).
3. Idempotencia es a nivel aplicación (no UNIQUE DB) — carrera concurrente residual.
4. Handlers de eventos aún mayormente observabilidad (no side-effects de dominio).
5. Optimización de índices/performance: auditada conceptualmente, sin DDL nuevo sin EXPLAIN.

## 15. Deuda técnica restante

- Adelgazar routers prioritarios hasta ~400 líneas.
- Outbox persistente si se requieren efectos externos fiables.
- Separar rol DDL vs rol app en Postgres producción.
- Ampliar E2E quote-to-cash / procure-to-pay con Postgres de CI.

---

## Matriz de trazabilidad

| ID | Requisito | Implementación | Archivos principales | Prueba | Estado |
|----|-----------|----------------|----------------------|--------|--------|
| P0-MIG | Alembic canónico | Revisión 0004 + ERP_SCHEMA_REVISION | `alembic/versions/0004_*`, `db/schema_revision.py` | `test_schema_migration_canonical` | IMPLEMENTADO Y VALIDADO |
| P0-MIG-UP | Upgrade controlado + lock | Advisory lock + UpgradeResult | `schema_upgrade.py` | `test_schema_upgrade` | IMPLEMENTADO Y VALIDADO |
| P0-MIG-AUTO | Reducir AUTO_MIGRATE | Documentado; prod ya false; SQL absorbidos | docs + 0004 | canonical | IMPLEMENTADO SIN VALIDACIÓN COMPLETA |
| P0-ACC | Frontera AccountingService | Migración CxP/UI/seed | `accounting_service.py`, cxp, contabilidad UI | `test_accounting_boundary_*` | IMPLEMENTADO Y VALIDADO |
| P0-ACC-INV | Partida doble / periodo / idempotencia | En `crear_asiento` | `contabilidad_asientos.py` | invariants tests | IMPLEMENTADO Y VALIDADO |
| P0-TX | TX críticas | Pago cliente commit único | `pago_service.py` | process matrix | PARCIAL |
| P1-MOD | Contratos modules | cobranza/finanzas/leasing.activation | `modules/*` | architecture + process matrix | PARCIAL |
| P1-EVT | Eventos dominio | ContratoActivado, PagoRealizado | bootstrap, LF/LOP, cobranza | process matrix | IMPLEMENTADO Y VALIDADO |
| P1-OWN | Guardrails ownership | AST boundaries ampliados | `test_architecture_boundaries.py` | mismo | IMPLEMENTADO Y VALIDADO |
| P2-PROC | Matriz procesos | Contratos + eventos | `test_erp_process_matrix.py`, `mapa_procesos_erp.md` | process matrix | PARCIAL |
| P2-API | API v1 | `/api/v1` | `routes/api/v1/*` | process matrix | IMPLEMENTADO Y VALIDADO |
| P2-OBS | Observabilidad | request_id + /health/ready | middleware, main | process matrix | IMPLEMENTADO Y VALIDADO |
| P2-SEC | Seguridad continua | Controles existentes + CI ampliado | `.github/workflows/ci.yml` | security + multiempresa | IMPLEMENTADO SIN VALIDACIÓN COMPLETA |
| P3-UX | Nav desde registry | Sin reescritura UI; registry ya alineado | tests registry | architecture | PARCIAL |
| P3-DOC | Docs procesos | mapa + informe + arquitectura | `docs/*` | n/a | IMPLEMENTADO Y VALIDADO |
| P3-PERF | Performance | Solo análisis; sin índices nuevos | — | — | NO IMPLEMENTADO |
| TEN | Multiempresa | Preservado + pruebas existentes | tenancy stack | `test_database_per_company` | IMPLEMENTADO Y VALIDADO |

---

## Informe de migraciones

### Revisiones

| Revisión | Rol |
|----------|-----|
| `0001_baseline` | Bootstrap completo company |
| `0002_ops_audit_backups` | SQL 137 |
| `0003_lop_residual_engine` | SQL 139 |
| `0004_platform_auth_mail_lf_lop` **(nueva)** | SQL 132,133,134,135,136,138 |

### SQL absorbidos en 0004

- `132_auth_password_reset_codes.sql`
- `133_mail_accounts.sql`
- `134_auth_usuario_session_version.sql`
- `135_leasing_financiero_cotizacion_fase1.sql`
- `136_leasing_financiero_estados_fase1.sql`
- `138_leasing_operativo_tipos_flota.sql`

### SQL que permanecen como herramientas / bootstrap

- Scripts operativos en `tools/`
- `startup_schema.ensure_*` para compatibilidad AUTO_MIGRATE en desarrollo
- Seeds de datos (no DDL de versión)

### Procedimiento de actualización

1. Backup de identity + company DB
2. `python tools/upgrade_company_schema.py --status`
3. `--company CODIGO` o `--all` / `--legacy`
4. Verificar `app_metadata.app_version == 0006_domain_event_outbox`
5. Verificar `Company.schema_version` en identity

### Rollback

`0004` **no es reversible de forma segura** (`NotImplementedError` en downgrade).  
`0005`/`0006` permiten DROP de índice/tabla outbox, pero la recuperación operativa recomendada sigue siendo **restaurar backup**.

---

## Fase 2 — Cierre de brechas críticas (2026-10-10)

Documento complementario de política: `docs/politica_transacciones.md`, `docs/migraciones_permisos_ddl.md`, `docs/performance_indices_fase2.md`.

### 1. Brechas verificadas

1. Idempotencia solo en aplicación (carrera concurrente posible).
2. Índice legado `ux_asientos_origen_unico` (SQL 108) demasiado amplio (rompería MANUAL y LOP_DEPRECIACION mensual).
3. `integracion_ventas` / `integracion_inventario` confirmaban asientos con `do_commit=True` por defecto dentro de casos de uso mayores.
4. Eventos emitidos fuera de TX / sin persistencia.
5. Upgrade Alembic no validado contra Postgres real en esta sesión.

### 2. Correcciones implementadas

- Índice único parcial `ux_asientos_origen_idempotente` + SAVEPOINT/`IntegrityError` en `crear_asiento`.
- `LOP_DEPRECIACION` usa `origen_id = fila_depreciacion.id` (un asiento por periodo).
- `do_commit=False` en ventas e inventario.
- Outbox `domain_event_outbox` + `publish_in_transaction` / `flush_outbox_after_commit`.
- Extracción `modules.contabilidad.manual_entries` para UI contable.
- Docs de permisos DDL y performance con honestidad de medición.

### 3. Archivos principales (fase 2)

- `alembic/versions/0005_asientos_origen_idempotente.py`, `0006_domain_event_outbox.py`
- `db/psql/140_*.sql`, `141_*.sql`, `db/schema_revision.py`
- `crud/finanzas/contabilidad_asientos.py`, `services/finanzas/integracion_*.py`
- `erp_platform/events/outbox.py`, `publish.py`
- `services/cobranza/pago_service.py`, `services/comercial/ventas_service.py`
- `services/leasing_*_contabilidad.py`, `crud/leasing_operativo/crud.py` (depreciación)
- `modules/contabilidad/manual_entries.py`, `routes/ui/contabilidad.py`
- Tests: `test_accounting_concurrency.py`, `test_transaction_boundaries.py`, `test_domain_event_outbox.py`

### 4–5. Restricciones / migraciones nuevas

| Revisión | Cambio |
|----------|--------|
| `0005_asientos_origen_idempotente` | UNIQUE parcial + drop índice amplio; preflight de duplicados |
| `0006_domain_event_outbox` | Tabla outbox + índices |

### 6. Procesos transaccionales corregidos

Ventas, inventario, pago cliente (outbox), activación LF (outbox + flush), política documentada.

### 7. Pruebas de concurrencia

| Prueba | Resultado |
|--------|-----------|
| `test_integrity_error_race_returns_existing` | VALIDADO (mock SAVEPOINT) |
| `test_postgres_concurrent_post_entry_no_duplicates` | **OMITIDO** sin `EVALUA_TEST_DATABASE_URL` — IMPLEMENTADO SIN VALIDACIÓN COMPLETA |

### 8. Validaciones Alembic

Cadena head=`0006` validada en tests. Upgrade real aislado: pendiente staging (`docs/migraciones_permisos_ddl.md`).

### 9. Eventos y garantías

- Outbox en misma TX → **at-least-once** tras commit.
- Handlers bootstrap siguen siendo observabilidad (idempotentes / no financieros).
- No se declara exactly-once.

### 10. Performance

Índice de fecha/origen añadido por justificación de código; sin EXPLAIN ANALYZE → no se declaran gains medidos.

### 11–12. Fallos / riesgos residuales

- Concurrencia Postgres real no ejecutada aquí.
- Routers LOP/LF aún grandes (extracción selectiva parcial: manual_entries + activation).
- Duplicados históricos bloquearían `0005` (migración falla con muestra; no auto-limpia).

### Matriz de riesgos (fase 2)

| Riesgo | Estado inicial | Corrección | Evidencia | Riesgo residual |
|--------|----------------|------------|-----------|-----------------|
| Carrera contable | Solo SELECT previo | UNIQUE parcial + SAVEPOINT | tests concurrency + migración 0005 | Validación Postgres real pendiente |
| TX parcial ventas/inventario | `do_commit` default True | `do_commit=False` | `test_transaction_boundaries` | Bajo |
| Eventos post-commit perdidos | emit best-effort | outbox TX + flush | outbox tests + código | Handlers aún no financieros |
| Índice amplio 108 | Riesgo MANUAL/depreciación | DROP + índice parcial | SQL 140 | Si 108 ya aplicado en prod, 0005 lo reemplaza |
| Upgrade no validado | Solo mocks | Docs + checklist staging | canonical tests | Staging pendiente |
| Routers gordos | >1000 LOC | Extracción selectiva | manual_entries | PARCIAL |
| Performance | Sin índices justificados | Índice fecha/origen | doc performance | Sin medición |

---

## Estado final de producción

**APTO CON RESTRICCIONES**

Mejoras de fase 2 reducen el riesgo crítico de doble asiento y TX parciales. Sigue sin validación de:

- `alembic upgrade` contra Postgres limpio/staging
- prueba concurrente real (`EVALUA_TEST_DATABASE_URL`)
- EXPLAIN ANALYZE con datos representativos

Condiciones para avanzar a **APTO**:

1. Staging: upgrade a `0006` + smoke contable + prueba concurrente.
2. Confirmar ausencia de duplicados de origen antes de `0005` (o resolución manual).
3. `AUTO_MIGRATE_ON_STARTUP=false` y rol migrador separado.

No se afirma despliegue ni validación en producción.

### Diagnóstico por área (fase 2)

| Área | Estado | Pruebas | Fallos | Riesgo residual | Próxima acción |
|------|--------|---------|--------|-----------------|----------------|
| CONTABILIDAD | IMPLEMENTADO SIN VALIDACIÓN COMPLETA | boundary, concurrency (mock) | — | carrera real PG | correr test PG en staging |
| TRANSACCIONES | IMPLEMENTADO Y VALIDADO | transaction_boundaries | — | Bajo | mantener política |
| EVENTOS | IMPLEMENTADO Y VALIDADO | outbox unit | — | at-least-once | job periódico dispatch opcional |
| MIGRACIONES | IMPLEMENTADO SIN VALIDACIÓN COMPLETA | schema canonical/upgrade | — | staging | upgrade aislado |
| MULTIEMPRESA | IMPLEMENTADO Y VALIDADO | database_per_company | — | Bajo | — |
| MODULARIDAD | PARCIAL | architecture | — | routers grandes | seguir extracción |
| PERFORMANCE | PARCIAL | — | — | sin medición | EXPLAIN staging |
| OPERACIÓN Y SEGURIDAD | IMPLEMENTADO SIN VALIDACIÓN COMPLETA | security/http | — | DDL local | rol migrador |

---

## Fase 3 — Validación operativa y concurrencia real (2026-10-10)

### Entorno auditado

| Recurso | Estado |
|---------|--------|
| `EVALUA_TEST_DATABASE_URL` | **UNSET** |
| `DATABASE_URL` (shell) | UNSET (existe en `.env` pero **no se usa** para Fase 3) |
| Docker | No disponible |
| PostgreSQL local (servicios 17/18) | Running, pero **sin credenciales** para crear BD aislada (`psql` pide password; sin `.pgpass`) |

Conclusión de entorno: la validación contra PostgreSQL real quedó **BLOQUEADA POR ENTORNO**. No se usó `DATABASE_URL` operativa ni se ejecutaron migraciones sobre bases reales.

### Auditoría del índice 0005 (sin cambiar la revisión)

| Aspecto | Hallazgo |
|---------|----------|
| Clave | `(origen_tipo, origen_id)` |
| Parcial | `origen_id > 0` + lista blanca de tipos |
| Manuales | Excluidos (`MANUAL_*` no están en la lista) |
| `LOP_DEPRECIACION` | Incluido; granularidad = id de fila de depreciación (código Fase 2) |
| Anulaciones | `NOTA_VENTA_ANULACION` / `REV_MANUAL` tienen clave propia |
| Multiempresa | Aislamiento por **base por compañía** (no columna company_id en asientos) |
| Duplicados históricos | Preflight en migración + tool `tools/preflight_asientos_duplicados.py` (no auto-borra) |

Comentario del SQL 140 corregido (documentación; no se reescribe 0005).

### Correcciones Fase 3 (código)

| Cambio | Archivo |
|--------|---------|
| Head Alembic → `0007_outbox_correlation_unique` | `db/schema_revision.py`, `alembic/versions/0007_*` |
| Unique `correlation_id` en outbox | `db/psql/142_*.sql` |
| Claim atómico outbox (`UPDATE … FOR UPDATE SKIP LOCKED`) | `erp_platform/events/outbox.py` |
| Enqueue idempotente por correlation + SAVEPOINT | `outbox.py` |
| Script validación PG aislada | `tools/run_fase3_postgres_validation.py` (exit 3 si falta URL) |
| Preflight duplicados | `tools/preflight_asientos_duplicados.py` |

### Pruebas ejecutadas (esta sesión)

Comando:

```bash
python tools/run_fase3_postgres_validation.py
# → exit 3 BLOQUEADA POR ENTORNO

python -m pytest \
  tests/test_schema_migration_canonical.py \
  tests/test_accounting_concurrency.py \
  tests/test_transaction_boundaries.py \
  tests/test_domain_event_outbox.py \
  tests/test_accounting_boundary_and_invariants.py \
  tests/test_erp_process_matrix.py \
  tests/test_architecture_boundaries.py \
  tests/test_schema_upgrade.py \
  tests/test_leasing_financiero_contabilidad.py \
  tests/test_database_per_company.py \
  tests/test_security_hardening.py -q
```

| Resultado | Detalle |
|-----------|---------|
| APROBADAS | Suite anterior + head 0007 + outbox SKIP LOCKED + gate exit 3 |
| OMITIDAS | `test_evalua_test_database_url_status_is_explicit`, `test_postgres_concurrent_post_entry_no_duplicates` (sin `EVALUA_TEST_DATABASE_URL`) |
| FALLIDAS | 0 |
| BLOQUEADAS POR ENTORNO | Upgrade real, concurrencia PG, EXPLAIN ANALYZE, separación de roles DDL |

### Cómo desbloquear (comando canónico)

```bat
REM 1) Crear BD desechable con rol migrador (fuera de este agente si no hay password)
CREATE DATABASE evalua_fase3_test;

REM 2) Apuntar solo a la BD de prueba
set EVALUA_TEST_DATABASE_URL=postgresql+psycopg://USER:PASS@127.0.0.1:5432/evalua_fase3_test

REM 3) Validación integral Fase 3
python tools/run_fase3_postgres_validation.py
```

### Performance

Sin datos representativos ni `EVALUA_TEST_DATABASE_URL`: **NO IMPLEMENTADO** medición. Sigue vigente `docs/performance_indices_fase2.md`.

### Multiempresa

Pruebas unitarias `test_database_per_company` **APROBADAS**. Upgrade `--all` / legacy contra bases reales: **no ejecutado** (bloqueado).

### Clasificación Fase 3

**APTO CON RESTRICCIONES** — **no** se asciende a **APTO**.

Motivo: faltan evidencias obligatorias de concurrencia PostgreSQL real y upgrade de esquema en base aislada. El código y las suites locales están verdes; la preparación productiva sigue condicionada a ejecutar `tools/run_fase3_postgres_validation.py` con `EVALUA_TEST_DATABASE_URL`.

### Diagnóstico por área (post Fase 3)

| Área | Estado | Pruebas | Fallos | Riesgo residual | Próxima acción |
|------|--------|---------|--------|-----------------|----------------|
| CONTABILIDAD | IMPLEMENTADO SIN VALIDACIÓN COMPLETA | concurrency mock APROBADA; PG OMITIDA | 0 | carrera real no medida | `run_fase3_postgres_validation.py` |
| TRANSACCIONES | IMPLEMENTADO Y VALIDADO | transaction_boundaries | 0 | Bajo | — |
| EVENTOS | IMPLEMENTADO SIN VALIDACIÓN COMPLETA | outbox unit + SKIP LOCKED | 0 | dispatch multi-worker en PG real | validar en BD prueba |
| MIGRACIONES | IMPLEMENTADO SIN VALIDACIÓN COMPLETA | canonical 0007 | 0 | upgrade real | script Fase 3 |
| MULTIEMPRESA | IMPLEMENTADO Y VALIDADO | database_per_company | 0 | upgrade multi-DB real | staging |
| MODULARIDAD | PARCIAL | architecture | 0 | routers grandes | incremental |
| PERFORMANCE | NO IMPLEMENTADO | — | — | sin EXPLAIN | staging con datos |
| OPERACIÓN Y SEGURIDAD | PARCIAL | security | 0 | roles DDL no verificados | checklist permisos |

---

## Fase 4 — Hardening QA / seguridad API (2026-10-10)

Revisión senior + QA sobre el estado post Fase 3. **No** asciende a APTO (sigue pendiente `EVALUA_TEST_DATABASE_URL`).

### Correcciones

| Cambio | Archivos | Evidencia |
|--------|----------|-----------|
| Reclaim de outbox `PROCESSING` huérfano (`SKIP LOCKED`) | `erp_platform/events/outbox.py` | `test_domain_event_outbox` |
| RBAC en `/api/v1` contabilidad/leasing (`CONTABILIDAD.VIEW` / `LEASING.VIEW`) | `routes/api/v1/deps.py`, `accounting.py`, `leasing.py` | `test_erp_process_matrix` + boundaries |
| Observabilidad: identidad en excepciones + Request-ID de cliente | `core/observability_middleware.py` | process matrix |
| Guardrail arquitectura API con permisos | `tests/test_architecture_boundaries.py` | APROBADO |

### Clasificación

**APTO CON RESTRICCIONES** (sin cambio). Condición APTO sigue siendo la validación PostgreSQL aislada de Fase 3.
