-- 142_outbox_correlation_unique.sql
-- Idempotencia de publicación: un correlation_id no genera dos filas PENDING/DONE.
-- Compatible con at-least-once (reintentos actualizan la misma fila vía dispatch).

CREATE UNIQUE INDEX IF NOT EXISTS ux_domain_event_outbox_correlation
    ON public.domain_event_outbox (correlation_id)
    WHERE correlation_id IS NOT NULL AND btrim(correlation_id) <> '';

COMMENT ON INDEX public.ux_domain_event_outbox_correlation IS
    'Evita duplicar eventos de dominio con el mismo correlation_id.';
