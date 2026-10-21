# Mapa de procesos EvaluaERP

Documenta procesos de negocio con ownership real del código (no propuestas).

## Quote-to-cash

| Ítem | Detalle |
|------|---------|
| Objetivo | Cotizar/vender, generar CxC, contabilizar y cobrar |
| Módulo propietario | `COMERCIAL` + `COBRANZA` + `CONTABILIDAD` |
| Caso de uso | `modules.comercial.sales.crear_venta_pos` → `integracion_ventas` → `modules.cobranza.registrar_pago_cliente` |
| Tablas | `nota_venta`, CxC, `asientos_contables`, caja |
| Contratos | `AccountingService.post_entry`, eventos `VentaConfirmada` / `PagoRealizado` |
| TX | Contabilización con `do_commit=False` dentro del caso de uso; commit al final |
| Auth | RBAC comercial / cobranza |
| Pruebas | `tests/test_erp_process_matrix.py`, integraciones leasing/ventas existentes |

## Procure-to-pay

| Ítem | Detalle |
|------|---------|
| Objetivo | Documentos AP, pagos a proveedores, asientos |
| Módulo propietario | `CXP` / `FINANZAS` |
| Caso de uso | `modules.finanzas.registrar_documento_ap` / `registrar_pago_ap` |
| Contabilización | Solo vía `AccountingService` (origen `AP_DOCUMENTO` / `AP_PAGO`) |
| Pruebas | frontera contable + schemas CxP |

## Lease-to-asset

| Ítem | Detalle |
|------|---------|
| Objetivo | Cotizar, activar contrato LF/LOP, obligaciones y contabilidad |
| Módulo propietario | `LEASING_FINANCIERO` / `LEASING_OPERATIVO` |
| Caso de uso | `modules.leasing.activation.activar_leasing_*` |
| Evento | `ContratoLeasingActivado` |
| Pruebas | `tests/test_leasing_financiero_*`, `tests/test_leasing_operativo_*`, matriz de procesos |

## Hire-to-retire / Nómina

| Ítem | Detalle |
|------|---------|
| Objetivo | Provisión y pago de remuneraciones |
| Módulo propietario | `RRHH` |
| Contabilización | `crud/remuneraciones_contabilidad.py` → `AccountingService` |
| Nota | Fórmulas laborales no modificadas en esta fase |

## Inventario y taller

| Ítem | Detalle |
|------|---------|
| Objetivo | Stock, OT, costos |
| Integración contable | `services/finanzas/integracion_inventario.py` → `AccountingService` |
| Estado | Contratos `modules.inventario` / `modules.taller` aún delgados; routers UI siguen orquestando |

## Cierre contable

| Ítem | Detalle |
|------|---------|
| Objetivo | Abrir/cerrar periodos; bloquear asientos |
| Implementación | `crud.finanzas.periodos.assert_periodo_abierto_para_fecha` dentro de `crear_asiento` |
| UI | `routes/ui/fin_periodos.py` |

## Administración de empresas / schema

| Ítem | Detalle |
|------|---------|
| Tenancy | `legacy` y `database_per_company` |
| Upgrade | `tools/upgrade_company_schema.py` + Alembic head = `ERP_SCHEMA_REVISION` |
| Docs | `docs/arquitectura_modular.md`, `docs/informe_evolucion_arquitectonica.md` |

## Autenticación y selección de empresa

| Ítem | Detalle |
|------|---------|
| Identity DB | Usuarios, memberships, registro de bases |
| Resolución | Contexto autorizado (`CompanyContext`); la UI no aporta URLs/credenciales |
| Pruebas | `tests/test_database_per_company.py`, `tests/test_security_*` |
