# Performance — evidencia fase 2

## Cambio aplicado con justificación de código (sin EXPLAIN ANALYZE)

| Índice | Justificación | Medición |
|--------|---------------|----------|
| `ux_asientos_origen_idempotente` | Integridad/concurrencia, no solo performance | Validado por diseño + test de carrera (mock); Postgres real opcional |
| `ix_asientos_contables_fecha_origen` | Soporte a `listar_asientos` ordenado por fecha + filtro origen | **Sin EXPLAIN ANALYZE** — no hay dataset representativo en esta sesión |

## Consultas candidatas (pendientes de EXPLAIN en staging)

1. Listado de asientos por rango de fechas (`contabilidad_asientos.listar_asientos`).
2. Cartera CxC / pagos por cliente.
3. Documentos AP abiertos + saldo.
4. Contratos LOP/LF por estado.
5. Auditoría `auth_audit_event` por fecha.

No se crearon vistas materializadas.

## Limitación

Sin datos de producción/staging no se declaran mejoras de latencia. Próximo paso: correr `EXPLAIN (ANALYZE, BUFFERS)` en staging con volúmenes reales antes de más índices.
