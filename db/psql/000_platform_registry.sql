CREATE EXTENSION IF NOT EXISTS pgcrypto;

CREATE TABLE IF NOT EXISTS public.tenants (
    id                BIGSERIAL PRIMARY KEY,
    tenant_code       VARCHAR(60) NOT NULL UNIQUE,
    tenant_name       VARCHAR(160) NOT NULL,
    db_driver         VARCHAR(80)  NOT NULL DEFAULT 'postgresql+psycopg',
    db_host           VARCHAR(120) NOT NULL,
    db_port           INTEGER      NOT NULL DEFAULT 5432,
    db_name           VARCHAR(120) NOT NULL UNIQUE,
    db_user           VARCHAR(120) NOT NULL,
    db_password       TEXT         NOT NULL,
    db_sslmode        VARCHAR(20),
    is_active         BOOLEAN      NOT NULL DEFAULT TRUE,
    created_at        TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    updated_at        TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS ix_tenants_code_active
    ON public.tenants (tenant_code, is_active);

CREATE TABLE IF NOT EXISTS public.tenant_domains (
    id                BIGSERIAL PRIMARY KEY,
    tenant_id         BIGINT NOT NULL REFERENCES public.tenants(id) ON DELETE CASCADE,
    domain            VARCHAR(255) NOT NULL UNIQUE,
    is_primary        BOOLEAN NOT NULL DEFAULT FALSE,
    created_at        TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS ix_tenant_domains_tenant
    ON public.tenant_domains (tenant_id);