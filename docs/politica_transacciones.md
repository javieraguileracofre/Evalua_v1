# Política de transacciones (EvaluaERP)

## Regla

1. El **caso de uso** (`modules.*` / servicio de aplicación) es dueño del `commit` / `rollback`.
2. Las funciones de contabilización e integración deben usar `do_commit=False` cuando participan en una operación mayor.
3. Los efectos externos (correo, handlers) **no** forman parte de la TX PostgreSQL.
4. Eventos de dominio relevantes se persisten en **outbox** dentro de la misma TX (`publish_in_transaction`) y se despachan con `flush_outbox_after_commit` tras el commit.

## Flujos auditados (fase 2)

| Flujo | Commit | Contabilización | Evento |
|-------|--------|-----------------|--------|
| Pago cliente | `pago_service` | `do_commit=False` | outbox `PagoRealizado` |
| Venta POS | `ventas_service` | `integracion_ventas` `do_commit=False` | outbox `VentaConfirmada` / `VentaAnulada` |
| CxP doc/pago | `CuentasPorPagarCRUD` | `do_commit=False` | — |
| Activación LF | `activar_flujo_contable` | `do_commit=False` | outbox + flush post-commit |
| Activación LOP | caller | `do_commit=False` | outbox en misma TX |
| Inventario recepción | caller | `do_commit=False` | — |
| Nómina | caller | `do_commit=False` | — |
| Asiento manual UI | UI (commit implícito del servicio) | `idempotent=False` | — |

## Idempotencia contable

- Aplicación: `ORIGENES_IDEMPOTENTES` + `SELECT` previo.
- PostgreSQL: índice único parcial `ux_asientos_origen_idempotente` (revisión `0005`).
- Carreras: `SAVEPOINT` + captura de `IntegrityError` → retorno del asiento existente.

## Outbox

- Persistencia en la misma TX (`publish_in_transaction`).
- Despacho post-commit (`flush_outbox_after_commit` / `dispatch_pending`).
- Workers concurrentes: claim `UPDATE … FOR UPDATE SKIP LOCKED`.
- Idempotencia de publicación: `ux_domain_event_outbox_correlation` (revisión `0007`).
- Semántica: **at-least-once** (no exactly-once).
