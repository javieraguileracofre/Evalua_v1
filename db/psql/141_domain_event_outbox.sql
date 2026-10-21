-- 141_domain_event_outbox.sql
-- Outbox transaccional para eventos de dominio que deben sobrevivir al commit.
-- Persistidos en la misma TX de negocio; despacho posterior idempotente.

CREATE TABLE IF NOT EXISTS public.domain_event_outbox (
    id              BIGSERIAL PRIMARY KEY,
    event_name      VARCHAR(80) NOT NULL,
    payload_json    JSONB NOT NULL DEFAULT '{}'::jsonb,
    company_id      BIGINT NULL,
    actor_id        BIGINT NULL,
    correlation_id  VARCHAR(64) NULL,
    status          VARCHAR(20) NOT NULL DEFAULT 'PENDING',
    attempts        INTEGER NOT NULL DEFAULT 0,
    last_error      TEXT NULL,
    created_at      TIMESTAMP WITHOUT TIME ZONE NOT NULL DEFAULT NOW(),
    processed_at    TIMESTAMP WITHOUT TIME ZONE NULL,
    CONSTRAINT ck_domain_event_outbox_status
        CHECK (status IN ('PENDING', 'PROCESSING', 'DONE', 'FAILED'))
);

CREATE INDEX IF NOT EXISTS ix_domain_event_outbox_pending
    ON public.domain_event_outbox (status, created_at)
    WHERE status IN ('PENDING', 'FAILED');

CREATE INDEX IF NOT EXISTS ix_domain_event_outbox_company
    ON public.domain_event_outbox (company_id, created_at DESC);

COMMENT ON TABLE public.domain_event_outbox IS
    'Outbox de eventos de dominio (al menos una vez; consumidores idempotentes).';
