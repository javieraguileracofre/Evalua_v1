-- 137_ops_audit_backups.sql
-- Auditoría operacional y metadatos de respaldos (sin secretos).

CREATE TABLE IF NOT EXISTS public.auth_audit_event (
    id              BIGSERIAL PRIMARY KEY,
    actor_id        BIGINT,
    company_code    VARCHAR(40),
    action          VARCHAR(64) NOT NULL,
    module          VARCHAR(64) NOT NULL DEFAULT 'security',
    entity          VARCHAR(64),
    entity_id       VARCHAR(64),
    result          VARCHAR(20) NOT NULL DEFAULT 'ok',
    ip_hmac         VARCHAR(64),
    user_agent      VARCHAR(240),
    detail_json     TEXT,
    created_at      TIMESTAMP WITHOUT TIME ZONE NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS ix_auth_audit_event_created
    ON public.auth_audit_event (created_at DESC);
CREATE INDEX IF NOT EXISTS ix_auth_audit_event_action
    ON public.auth_audit_event (action);
CREATE INDEX IF NOT EXISTS ix_auth_audit_event_actor
    ON public.auth_audit_event (actor_id);

CREATE TABLE IF NOT EXISTS public.ops_database_backup (
    id               BIGSERIAL PRIMARY KEY,
    status           VARCHAR(20) NOT NULL DEFAULT 'pending',
    backup_type      VARCHAR(20) NOT NULL DEFAULT 'manual',
    engine_name      VARCHAR(40) NOT NULL DEFAULT 'postgresql',
    database_name    VARCHAR(120) NOT NULL DEFAULT '',
    file_name        VARCHAR(255),
    file_path        VARCHAR(500),
    size_bytes       BIGINT,
    checksum_sha256  VARCHAR(64),
    created_by_id    BIGINT,
    error_message    VARCHAR(500),
    company_code     VARCHAR(40),
    started_at       TIMESTAMP WITHOUT TIME ZONE,
    finished_at      TIMESTAMP WITHOUT TIME ZONE,
    created_at       TIMESTAMP WITHOUT TIME ZONE NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS ix_ops_database_backup_created
    ON public.ops_database_backup (created_at DESC);
CREATE INDEX IF NOT EXISTS ix_ops_database_backup_status
    ON public.ops_database_backup (status);
