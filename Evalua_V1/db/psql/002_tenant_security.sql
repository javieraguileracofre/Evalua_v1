-- db/psql/002_tenant_security.sql

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