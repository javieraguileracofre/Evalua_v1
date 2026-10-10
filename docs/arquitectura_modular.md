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

1. **Alembic** (`alembic/versions`) — revisión head = `db.schema_revision.ERP_SCHEMA_REVISION`.
2. **SQL** en `db/psql/*.sql` — aplicados por revisiones Alembic o por `db.schema_bootstrap.apply_company_schema`.
3. **`db/startup_schema.py`** — parches idempotentes solo con `AUTO_MIGRATE_ON_STARTUP=true` (bloqueado en producción). Con el flag en false solo corre seeds de datos.

En multiempresa, `app_metadata.app_version` y `Company.schema_version` deben igualar `ERP_SCHEMA_REVISION`.

### Operación de upgrade (checklist)

| Modo | Comando / UI |
|------|----------------|
| Legacy | `python tools/upgrade_company_schema.py --legacy` (también en `scripts/docker_entrypoint.sh`) |
| Inventario company | `python tools/upgrade_company_schema.py --status` |
| Una compañía | `python tools/upgrade_company_schema.py --company CODIGO` o Admin → Empresas → **Actualizar esquema** |
| Todas desactualizadas | `python tools/upgrade_company_schema.py --all` |

Producción: `AUTO_MIGRATE_ON_STARTUP=false`. El deploy Docker no usa DDL implícito; migra legacy en el entrypoint y company DBs vía tool/admin.

## Frontend

`templates/` se reorganizará progresivamente (`platform/`, `comercial/`, …) sin romper rutas Jinja actuales.
