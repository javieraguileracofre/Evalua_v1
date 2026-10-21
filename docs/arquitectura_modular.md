# Arquitectura modular Evalua ERP

## Objetivo

Evolucionar el monolito FastAPI/Jinja hacia un **modular monolith** multiempresa, sin microservicios prematuros.

## Capas

```text
UI / routes/ui
        ↓
modules.*          ← contratos públicos por dominio
        ↓
services / crud    ← implementación (legacy en transición)
        ↓
erp_platform.*     ← Identity, Tenancy, RBAC, Audit, Email, Events
        ↓
PostgreSQL (Company DB) + Identity DB
```

## Platform (`erp_platform/`)

> El paquete se llama `erp_platform` para **no sombrear** el stdlib `platform`.

Solo capacidades transversales:

- Identity / Tenancy / RBAC / Security / Audit / Email / Operations / Events / Registry

Los módulos ERP **pueden** importar `erp_platform`.  
`erp_platform` **no** debe importar lógica de leasing, nómina o inventario.

## Módulos (`modules/`)

Bounded contexts con ownership de datos (lógico):

| Módulo | Ownership |
|--------|-----------|
| contabilidad | asientos, plan de cuentas |
| comercial | clientes, notas de venta, postventa |
| leasing | cotizaciones/contratos LF/LO |
| credito_cobranzas | hub crédito → recuperación (agrupa crédito + cobranza) |
| credito | solicitudes y score |
| cobranza | CxC / pagos |
| inventario | stock y movimientos |
| taller | OT (consume inventario vía servicio) |
| rrhh | empleados / remuneraciones |
| analytics | solo lectura / KPIs |

## Contabilidad

Único dueño de asientos. Integraciones deben usar:

```python
from modules.contabilidad import accounting_service
accounting_service.post_entry(...)
```

## Eventos

Bus interno síncrono: `erp_platform.events`.

Ejemplos: `VentaConfirmada`, `ContratoLeasingActivado`, `PagoRealizado`.

Sin message broker por ahora.

## Dependencias permitidas

Definidas en `erp_platform.registry.ERP_MODULES` (`depends_on`).

Flujo: Platform ← Modules ← UI.

## Migración progresiva

1. Platform + registry + events + AccountingService *(esta fase)*
2. Contabilidad / Finanzas / Leasing (reducir imports de models cruzados)
3. Cobranzas / Inventario / Taller
4. RRHH / Analytics
5. Separación física de servicios **solo si hay necesidad real**

## Schema / migraciones (canónico)

Fuente de verdad del esquema operacional:

1. **Alembic** (`alembic/versions`) — revisión head = `db.schema_revision.ERP_SCHEMA_REVISION` (hoy `0009_fase_d_libros_tesoreria`).
2. **SQL** en `db/psql/*.sql` — absorbidos por revisiones Alembic (p. ej. 0002→137, 0003→139, 0004→132…138, 0005→140, 0006→141, 0007→142, 0008→143, 0009→144) o por `db.schema_bootstrap.apply_company_schema` en bases nuevas.
3. **`db/startup_schema.py`** — parches idempotentes **solo** con `AUTO_MIGRATE_ON_STARTUP=true` (bloqueado en producción). Con el flag en false solo corre seeds de datos. No es fuente de verdad del versionado.

`ERP_SCHEMA_REVISION` **no sustituye** el historial Alembic: debe coincidir exactamente con el head (`tests/test_schema_revision_alembic.py`, `tests/test_schema_migration_canonical.py`).

En multiempresa, `app_metadata.app_version` y `Company.schema_version` deben igualar `ERP_SCHEMA_REVISION`. El upgrade usa advisory lock PostgreSQL para evitar ejecuciones concurrentes.

### Operación de upgrade (checklist)

| Modo | Comando / UI |
|------|----------------|
| Legacy | `python tools/upgrade_company_schema.py --legacy` (también en `scripts/docker_entrypoint.sh`) |
| Inventario company | `python tools/upgrade_company_schema.py --status` |
| Una compañía | `python tools/upgrade_company_schema.py --company CODIGO` o Admin → Empresas → **Actualizar esquema** |
| Todas desactualizadas | `python tools/upgrade_company_schema.py --all` |

Producción: `AUTO_MIGRATE_ON_STARTUP=false`. El deploy Docker no usa DDL implícito; migra legacy en el entrypoint y company DBs vía tool/admin.

## Contabilidad (frontera obligatoria)

Escritura de asientos **solo** vía `modules.contabilidad.accounting_service` (`post_entry`, `reverse_manual_entry`, `find_by_origen`).

Invariantes en `crud.finanzas.contabilidad_asientos.crear_asiento` (implementación interna):

- Partida doble (`Decimal`)
- Periodo abierto
- Idempotencia por `(origen_tipo, origen_id)` en orígenes de negocio (`ORIGENES_IDEMPOTENTES`)

Guardrail: `tests/test_accounting_boundary_and_invariants.py`.

## Eventos de dominio

Bus síncrono `erp_platform.events`. Emisiones productivas:

| Evento | Emisor |
|--------|--------|
| `VentaConfirmada` / `VentaAnulada` | `services.comercial.ventas_service` |
| `ContratoLeasingActivado` | LF/LOP contabilidad |
| `PagoRealizado` | `services.cobranza.pago_service` (tras commit) |

Handlers: `modules.bootstrap.register_domain_handlers`.

## API versionada

- `/api/v1/*` — contrato estable para integraciones (`meta`, `session`, `accounting`, `leasing/capabilities`)
- `/api/comercial/leasing-operativo` y `/api/leasing` — API LOP existente (compatibilidad)

## Observabilidad

- Middleware `ObservabilityMiddleware`: `X-Request-ID`, logs con `company_id`/`actor_id` del contexto autorizado
- `/health` — liveness
- `/health/ready` — readiness (DB / identity según tenancy)

## Frontend

`templates/` se reorganizará progresivamente (`platform/`, `comercial/`, …) sin romper rutas Jinja actuales.
