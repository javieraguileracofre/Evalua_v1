-- =============================================================================
-- Evalua (repo Evalua_v1) — esquema mínimo en Supabase (public + fin + plan_cuenta 089)
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
    db_port           INTEGER      NOT NULL DEFAULT 6543,
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

-- --- 089_fin_plan_cuentas.sql (plan de cuentas + seed; mantener alineado con db/psql/089_*.sql) ---

CREATE SCHEMA IF NOT EXISTS fin;

CREATE TABLE IF NOT EXISTS fin.plan_cuenta (
    id                  BIGSERIAL PRIMARY KEY,
    codigo              VARCHAR(30) NOT NULL,
    nombre              VARCHAR(180) NOT NULL,
    nivel               INTEGER NOT NULL DEFAULT 1,
    cuenta_padre_id     BIGINT NULL,
    tipo                VARCHAR(30) NOT NULL,
    clasificacion       VARCHAR(50) NOT NULL,
    naturaleza          VARCHAR(20) NOT NULL,
    acepta_movimiento   BOOLEAN NOT NULL DEFAULT TRUE,
    requiere_centro_costo BOOLEAN NOT NULL DEFAULT FALSE,
    estado              VARCHAR(20) NOT NULL DEFAULT 'ACTIVO',
    descripcion         TEXT NULL,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT now(),

    CONSTRAINT ux_fin_plan_cuenta_codigo UNIQUE (codigo),
    CONSTRAINT fk_fin_plan_cuenta_padre
        FOREIGN KEY (cuenta_padre_id)
        REFERENCES fin.plan_cuenta(id)
        ON DELETE RESTRICT
);

ALTER TABLE fin.plan_cuenta
    ALTER COLUMN created_at SET DEFAULT now(),
    ALTER COLUMN updated_at SET DEFAULT now();

CREATE INDEX IF NOT EXISTS ix_fin_plan_cuenta_padre
    ON fin.plan_cuenta(cuenta_padre_id);

CREATE INDEX IF NOT EXISTS ix_fin_plan_cuenta_tipo
    ON fin.plan_cuenta(tipo);

CREATE INDEX IF NOT EXISTS ix_fin_plan_cuenta_clasificacion
    ON fin.plan_cuenta(clasificacion);

CREATE INDEX IF NOT EXISTS ix_fin_plan_cuenta_estado
    ON fin.plan_cuenta(estado);

CREATE INDEX IF NOT EXISTS ix_fin_plan_cuenta_nivel
    ON fin.plan_cuenta(nivel);

CREATE OR REPLACE FUNCTION fin.fn_set_updated_at_plan_cuenta()
RETURNS trigger AS $$
BEGIN
    NEW.updated_at := now();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_fin_plan_cuenta_updated_at ON fin.plan_cuenta;

CREATE TRIGGER trg_fin_plan_cuenta_updated_at
BEFORE UPDATE ON fin.plan_cuenta
FOR EACH ROW
EXECUTE FUNCTION fin.fn_set_updated_at_plan_cuenta();

INSERT INTO fin.plan_cuenta
(codigo, nombre, nivel, cuenta_padre_id, tipo, clasificacion, naturaleza, acepta_movimiento, requiere_centro_costo, estado, descripcion)
VALUES
('1', 'ACTIVO', 1, NULL, 'ACTIVO', 'ACTIVO', 'DEUDORA', FALSE, FALSE, 'ACTIVO', 'Grupo contable de activos'),
('2', 'PASIVO', 1, NULL, 'PASIVO', 'PASIVO', 'ACREEDORA', FALSE, FALSE, 'ACTIVO', 'Grupo contable de pasivos'),
('3', 'PATRIMONIO', 1, NULL, 'PATRIMONIO', 'PATRIMONIO', 'ACREEDORA', FALSE, FALSE, 'ACTIVO', 'Grupo contable patrimonial'),
('4', 'INGRESOS', 1, NULL, 'INGRESO', 'INGRESOS', 'ACREEDORA', FALSE, FALSE, 'ACTIVO', 'Grupo contable de ingresos'),
('5', 'COSTOS', 1, NULL, 'COSTO', 'COSTOS', 'DEUDORA', FALSE, FALSE, 'ACTIVO', 'Grupo contable de costos'),
('6', 'GASTOS', 1, NULL, 'GASTO', 'GASTOS', 'DEUDORA', FALSE, FALSE, 'ACTIVO', 'Grupo contable de gastos')
ON CONFLICT (codigo) DO NOTHING;

INSERT INTO fin.plan_cuenta
(codigo, nombre, nivel, cuenta_padre_id, tipo, clasificacion, naturaleza, acepta_movimiento, requiere_centro_costo, estado, descripcion)
SELECT '1.1', 'ACTIVO CORRIENTE', 2, id, 'ACTIVO', 'ACTIVO_CORRIENTE', 'DEUDORA', FALSE, FALSE, 'ACTIVO', 'Activo corriente'
FROM fin.plan_cuenta
WHERE codigo = '1'
ON CONFLICT (codigo) DO NOTHING;

INSERT INTO fin.plan_cuenta
(codigo, nombre, nivel, cuenta_padre_id, tipo, clasificacion, naturaleza, acepta_movimiento, requiere_centro_costo, estado, descripcion)
SELECT '2.1', 'PASIVO CORRIENTE', 2, id, 'PASIVO', 'PASIVO_CORRIENTE', 'ACREEDORA', FALSE, FALSE, 'ACTIVO', 'Pasivo corriente'
FROM fin.plan_cuenta
WHERE codigo = '2'
ON CONFLICT (codigo) DO NOTHING;

INSERT INTO fin.plan_cuenta
(codigo, nombre, nivel, cuenta_padre_id, tipo, clasificacion, naturaleza, acepta_movimiento, requiere_centro_costo, estado, descripcion)
SELECT '4.1', 'INGRESOS OPERACIONALES', 2, id, 'INGRESO', 'INGRESO_OPERACIONAL', 'ACREEDORA', FALSE, FALSE, 'ACTIVO', 'Ingresos operacionales'
FROM fin.plan_cuenta
WHERE codigo = '4'
ON CONFLICT (codigo) DO NOTHING;

INSERT INTO fin.plan_cuenta
(codigo, nombre, nivel, cuenta_padre_id, tipo, clasificacion, naturaleza, acepta_movimiento, requiere_centro_costo, estado, descripcion)
SELECT '5.1', 'COSTO DE VENTAS', 2, id, 'COSTO', 'COSTO_VENTA', 'DEUDORA', FALSE, FALSE, 'ACTIVO', 'Costo de ventas'
FROM fin.plan_cuenta
WHERE codigo = '5'
ON CONFLICT (codigo) DO NOTHING;

INSERT INTO fin.plan_cuenta
(codigo, nombre, nivel, cuenta_padre_id, tipo, clasificacion, naturaleza, acepta_movimiento, requiere_centro_costo, estado, descripcion)
SELECT '6.1', 'GASTOS DE ADMINISTRACION', 2, id, 'GASTO', 'GASTO_ADMINISTRACION', 'DEUDORA', FALSE, FALSE, 'ACTIVO', 'Gastos de administración'
FROM fin.plan_cuenta
WHERE codigo = '6'
ON CONFLICT (codigo) DO NOTHING;

INSERT INTO fin.plan_cuenta
(codigo, nombre, nivel, cuenta_padre_id, tipo, clasificacion, naturaleza, acepta_movimiento, requiere_centro_costo, estado, descripcion)
SELECT '1.1.1', 'CAJA', 3, id, 'ACTIVO', 'ACTIVO_CORRIENTE', 'DEUDORA', TRUE, FALSE, 'ACTIVO', 'Caja general'
FROM fin.plan_cuenta
WHERE codigo = '1.1'
ON CONFLICT (codigo) DO NOTHING;

INSERT INTO fin.plan_cuenta
(codigo, nombre, nivel, cuenta_padre_id, tipo, clasificacion, naturaleza, acepta_movimiento, requiere_centro_costo, estado, descripcion)
SELECT '1.1.2', 'BANCOS', 3, id, 'ACTIVO', 'ACTIVO_CORRIENTE', 'DEUDORA', TRUE, FALSE, 'ACTIVO', 'Bancos'
FROM fin.plan_cuenta
WHERE codigo = '1.1'
ON CONFLICT (codigo) DO NOTHING;

INSERT INTO fin.plan_cuenta
(codigo, nombre, nivel, cuenta_padre_id, tipo, clasificacion, naturaleza, acepta_movimiento, requiere_centro_costo, estado, descripcion)
SELECT '1.1.3', 'CLIENTES', 3, id, 'ACTIVO', 'ACTIVO_CORRIENTE', 'DEUDORA', TRUE, FALSE, 'ACTIVO', 'Clientes por cobrar'
FROM fin.plan_cuenta
WHERE codigo = '1.1'
ON CONFLICT (codigo) DO NOTHING;

INSERT INTO fin.plan_cuenta
(codigo, nombre, nivel, cuenta_padre_id, tipo, clasificacion, naturaleza, acepta_movimiento, requiere_centro_costo, estado, descripcion)
SELECT '2.1.1', 'PROVEEDORES', 3, id, 'PASIVO', 'PASIVO_CORRIENTE', 'ACREEDORA', TRUE, FALSE, 'ACTIVO', 'Proveedores por pagar'
FROM fin.plan_cuenta
WHERE codigo = '2.1'
ON CONFLICT (codigo) DO NOTHING;

INSERT INTO fin.plan_cuenta
(codigo, nombre, nivel, cuenta_padre_id, tipo, clasificacion, naturaleza, acepta_movimiento, requiere_centro_costo, estado, descripcion)
SELECT '4.1.1', 'VENTAS', 3, id, 'INGRESO', 'INGRESO_OPERACIONAL', 'ACREEDORA', TRUE, TRUE, 'ACTIVO', 'Ventas netas'
FROM fin.plan_cuenta
WHERE codigo = '4.1'
ON CONFLICT (codigo) DO NOTHING;

INSERT INTO fin.plan_cuenta
(codigo, nombre, nivel, cuenta_padre_id, tipo, clasificacion, naturaleza, acepta_movimiento, requiere_centro_costo, estado, descripcion)
SELECT '4.1.2', 'IVA DEBITO FISCAL', 3, id, 'PASIVO', 'PASIVO_CORRIENTE', 'ACREEDORA', TRUE, FALSE, 'ACTIVO', 'IVA débito fiscal'
FROM fin.plan_cuenta
WHERE codigo = '4.1'
ON CONFLICT (codigo) DO NOTHING;

INSERT INTO fin.plan_cuenta
(codigo, nombre, nivel, cuenta_padre_id, tipo, clasificacion, naturaleza, acepta_movimiento, requiere_centro_costo, estado, descripcion)
SELECT '5.1.1', 'COSTO DE VENTA', 3, id, 'COSTO', 'COSTO_VENTA', 'DEUDORA', TRUE, TRUE, 'ACTIVO', 'Costo directo de ventas'
FROM fin.plan_cuenta
WHERE codigo = '5.1'
ON CONFLICT (codigo) DO NOTHING;

INSERT INTO fin.plan_cuenta
(codigo, nombre, nivel, cuenta_padre_id, tipo, clasificacion, naturaleza, acepta_movimiento, requiere_centro_costo, estado, descripcion)
SELECT '6.1.1', 'GASTOS DE ADMINISTRACION', 3, id, 'GASTO', 'GASTO_ADMINISTRACION', 'DEUDORA', TRUE, TRUE, 'ACTIVO', 'Gastos administrativos'
FROM fin.plan_cuenta
WHERE codigo = '6.1'
ON CONFLICT (codigo) DO NOTHING;

INSERT INTO fin.plan_cuenta
(codigo, nombre, nivel, cuenta_padre_id, tipo, clasificacion, naturaleza, acepta_movimiento, requiere_centro_costo, estado, descripcion)
SELECT '1.1.4', 'IVA CREDITO FISCAL', 3, id, 'ACTIVO', 'ACTIVO_CORRIENTE', 'DEUDORA', TRUE, FALSE, 'ACTIVO', 'IVA crédito fiscal'
FROM fin.plan_cuenta
WHERE codigo = '1.1'
ON CONFLICT (codigo) DO NOTHING;
