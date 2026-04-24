-- =============================================================================
-- Evalua_V1 — esquema mínimo en Supabase (public + fin)
-- Ejecutar en: Supabase Dashboard → SQL Editor → New query → Run
-- (Aquí no hace falta contraseña en tu PC; el editor ya está autenticado.)
-- Después: en tu máquina, pon DATABASE_URL en .env y ejecuta:
--   python tools/supabase_bootstrap.py --skip-sql
-- =============================================================================

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

-- --- 001_tenant_base.sql ---

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

-- --- 002_tenant_security.sql ---

CREATE TABLE IF NOT EXISTS public.seguridad_roles (
    id                BIGSERIAL PRIMARY KEY,
    codigo            VARCHAR(50)  NOT NULL UNIQUE,
    nombre            VARCHAR(120) NOT NULL,
    descripcion       TEXT,
    activo            BOOLEAN      NOT NULL DEFAULT TRUE,
    created_at        TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    updated_at        TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS public.seguridad_usuarios (
    id                BIGSERIAL PRIMARY KEY,
    email             CITEXT       NOT NULL UNIQUE,
    nombre            VARCHAR(120) NOT NULL,
    password_hash     TEXT         NOT NULL,
    is_superadmin     BOOLEAN      NOT NULL DEFAULT FALSE,
    activo            BOOLEAN      NOT NULL DEFAULT TRUE,
    ultimo_login_at   TIMESTAMPTZ,
    created_at        TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    updated_at        TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS public.seguridad_usuario_roles (
    id                BIGSERIAL PRIMARY KEY,
    usuario_id        BIGINT NOT NULL REFERENCES public.seguridad_usuarios(id) ON DELETE CASCADE,
    rol_id            BIGINT NOT NULL REFERENCES public.seguridad_roles(id) ON DELETE CASCADE,
    created_at        TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (usuario_id, rol_id)
);

CREATE TABLE IF NOT EXISTS public.seguridad_auditoria (
    id                BIGSERIAL PRIMARY KEY,
    usuario_email     CITEXT,
    modulo            VARCHAR(80) NOT NULL,
    accion            VARCHAR(80) NOT NULL,
    entidad           VARCHAR(80),
    entidad_id        BIGINT,
    detalle           JSONB,
    ip_origen         VARCHAR(80),
    created_at        TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS ix_seg_auditoria_modulo_fecha
    ON public.seguridad_auditoria (modulo, created_at);

INSERT INTO public.seguridad_roles (codigo, nombre, descripcion)
VALUES
    ('ADMIN', 'Administrador', 'Acceso total al ERP'),
    ('FINANZAS', 'Finanzas', 'Compras, pagos, periodos, dashboard financiero'),
    ('COBRANZA', 'Cobranza', 'Gestión de cobros y pagos clientes'),
    ('COMERCIAL', 'Comercial', 'Clientes, notas de venta, cotización'),
    ('INVENTARIO', 'Inventario', 'Productos, stock, categorías')
ON CONFLICT (codigo) DO NOTHING;

-- --- 002a_fn_normalizar_rut.sql (columna generada en modelo Proveedor) ---

CREATE OR REPLACE FUNCTION public.fn_normalizar_rut(p_rut TEXT)
RETURNS TEXT
LANGUAGE sql
IMMUTABLE
PARALLEL SAFE
AS $$
    SELECT UPPER(
        REPLACE(REPLACE(REPLACE(COALESCE(TRIM(p_rut), ''), '.', ''), '-', ''), ' ', '')
    );
$$;
