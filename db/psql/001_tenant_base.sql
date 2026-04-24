-- db/psql/001_tenant_base.sql

CREATE EXTENSION IF NOT EXISTS pgcrypto;
CREATE EXTENSION IF NOT EXISTS citext;

CREATE SCHEMA IF NOT EXISTS fin;

CREATE TABLE IF NOT EXISTS public.app_metadata (
    id                BIGSERIAL PRIMARY KEY,
    tenant_code       VARCHAR(60)  NOT NULL UNIQUE,
    tenant_name       VARCHAR(160) NOT NULL,
    app_version       VARCHAR(30)  NOT NULL DEFAULT '1.0.0',
    installed_at      TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    updated_at        TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS public.empresa (
    id                BIGSERIAL PRIMARY KEY,
    rut               VARCHAR(20),
    razon_social      VARCHAR(200) NOT NULL,
    nombre_fantasia   VARCHAR(200),
    giro              VARCHAR(200),
    direccion         VARCHAR(250),
    comuna            VARCHAR(100),
    ciudad            VARCHAR(100),
    region            VARCHAR(100),
    pais              VARCHAR(100) NOT NULL DEFAULT 'Chile',
    telefono          VARCHAR(50),
    email             VARCHAR(150),
    sitio_web         VARCHAR(180),
    activo            BOOLEAN      NOT NULL DEFAULT TRUE,
    created_at        TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    updated_at        TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);