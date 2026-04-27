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
        ON DELETE RESTRICT,
    CONSTRAINT chk_fin_plan_cuenta_tipo
        CHECK (tipo IN ('ACTIVO', 'PASIVO', 'PATRIMONIO', 'INGRESO', 'COSTO', 'GASTO', 'ORDEN')),
    CONSTRAINT chk_fin_plan_cuenta_naturaleza
        CHECK (naturaleza IN ('DEUDORA', 'ACREEDORA')),
    CONSTRAINT chk_fin_plan_cuenta_estado
        CHECK (estado IN ('ACTIVO', 'INACTIVO'))
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
('100000', 'ACTIVO', 1, NULL, 'ACTIVO', 'ACTIVO', 'DEUDORA', FALSE, FALSE, 'ACTIVO', 'Grupo contable de activos'),
('200000', 'PASIVO', 1, NULL, 'PASIVO', 'PASIVO', 'ACREEDORA', FALSE, FALSE, 'ACTIVO', 'Grupo contable de pasivos'),
('300000', 'PATRIMONIO', 1, NULL, 'PATRIMONIO', 'PATRIMONIO', 'ACREEDORA', FALSE, FALSE, 'ACTIVO', 'Grupo contable patrimonial'),
('400000', 'INGRESOS', 1, NULL, 'INGRESO', 'INGRESOS', 'ACREEDORA', FALSE, FALSE, 'ACTIVO', 'Grupo contable de ingresos'),
('500000', 'COSTOS', 1, NULL, 'COSTO', 'COSTOS', 'DEUDORA', FALSE, FALSE, 'ACTIVO', 'Grupo contable de costos'),
('600000', 'GASTOS', 1, NULL, 'GASTO', 'GASTOS', 'DEUDORA', FALSE, FALSE, 'ACTIVO', 'Grupo contable de gastos')
ON CONFLICT (codigo) DO UPDATE
SET nombre = EXCLUDED.nombre,
    nivel = EXCLUDED.nivel,
    tipo = EXCLUDED.tipo,
    clasificacion = EXCLUDED.clasificacion,
    naturaleza = EXCLUDED.naturaleza,
    acepta_movimiento = EXCLUDED.acepta_movimiento,
    requiere_centro_costo = EXCLUDED.requiere_centro_costo,
    estado = EXCLUDED.estado,
    descripcion = EXCLUDED.descripcion;

INSERT INTO fin.plan_cuenta
(codigo, nombre, nivel, cuenta_padre_id, tipo, clasificacion, naturaleza, acepta_movimiento, requiere_centro_costo, estado, descripcion)
SELECT v.codigo, v.nombre, 2, p.id, v.tipo, v.clasificacion, v.naturaleza, FALSE, FALSE, 'ACTIVO', v.descripcion
FROM (VALUES
    ('110000', 'ACTIVO CORRIENTE', 'ACTIVO', 'ACTIVO_CORRIENTE', 'DEUDORA', 'Activos corrientes'),
    ('120000', 'ACTIVO NO CORRIENTE', 'ACTIVO', 'ACTIVO_NO_CORRIENTE', 'DEUDORA', 'Activos no corrientes'),
    ('210000', 'PASIVO CORRIENTE', 'PASIVO', 'PASIVO_CORRIENTE', 'ACREEDORA', 'Pasivos corrientes'),
    ('220000', 'PASIVO NO CORRIENTE', 'PASIVO', 'PASIVO_NO_CORRIENTE', 'ACREEDORA', 'Pasivos no corrientes'),
    ('310000', 'CAPITAL Y RESERVAS', 'PATRIMONIO', 'PATRIMONIO', 'ACREEDORA', 'Capital, reservas y resultados'),
    ('410000', 'INGRESOS OPERACIONALES', 'INGRESO', 'INGRESO_OPERACIONAL', 'ACREEDORA', 'Ingresos operacionales'),
    ('420000', 'OTROS INGRESOS', 'INGRESO', 'OTROS_INGRESOS', 'ACREEDORA', 'Ingresos no operacionales'),
    ('510000', 'COSTO DE VENTAS', 'COSTO', 'COSTO_VENTA', 'DEUDORA', 'Costos directos de ventas'),
    ('610000', 'GASTOS DE ADMINISTRACION', 'GASTO', 'GASTO_ADMINISTRACION', 'DEUDORA', 'Gastos administrativos'),
    ('620000', 'GASTOS DE VENTA', 'GASTO', 'GASTO_VENTA', 'DEUDORA', 'Gastos de venta'),
    ('630000', 'GASTOS FINANCIEROS', 'GASTO', 'GASTO_FINANCIERO', 'DEUDORA', 'Gastos financieros')
) AS v(codigo, nombre, tipo, clasificacion, naturaleza, descripcion)
JOIN fin.plan_cuenta p ON p.codigo = CASE
    WHEN v.codigo LIKE '11%' OR v.codigo LIKE '12%' THEN '100000'
    WHEN v.codigo LIKE '21%' OR v.codigo LIKE '22%' THEN '200000'
    WHEN v.codigo LIKE '31%' THEN '300000'
    WHEN v.codigo LIKE '41%' OR v.codigo LIKE '42%' THEN '400000'
    WHEN v.codigo LIKE '51%' THEN '500000'
    ELSE '600000'
END
ON CONFLICT (codigo) DO UPDATE
SET nombre = EXCLUDED.nombre,
    cuenta_padre_id = EXCLUDED.cuenta_padre_id,
    tipo = EXCLUDED.tipo,
    clasificacion = EXCLUDED.clasificacion,
    naturaleza = EXCLUDED.naturaleza,
    acepta_movimiento = EXCLUDED.acepta_movimiento,
    requiere_centro_costo = EXCLUDED.requiere_centro_costo,
    estado = EXCLUDED.estado,
    descripcion = EXCLUDED.descripcion;

INSERT INTO fin.plan_cuenta
(codigo, nombre, nivel, cuenta_padre_id, tipo, clasificacion, naturaleza, acepta_movimiento, requiere_centro_costo, estado, descripcion)
SELECT v.codigo, v.nombre, 3, p.id, v.tipo, v.clasificacion, v.naturaleza, TRUE, v.requiere_cc, 'ACTIVO', v.descripcion
FROM (VALUES
    ('110101', 'CAJA GENERAL', 'ACTIVO', 'ACTIVO_CORRIENTE', 'DEUDORA', FALSE, 'Caja general'),
    ('110201', 'BANCOS', 'ACTIVO', 'ACTIVO_CORRIENTE', 'DEUDORA', FALSE, 'Bancos'),
    ('110301', 'CLIENTES / CUENTAS POR COBRAR', 'ACTIVO', 'ACTIVO_CORRIENTE', 'DEUDORA', FALSE, 'Clientes por cobrar'),
    ('110401', 'INVENTARIO / MERCADERIAS', 'ACTIVO', 'ACTIVO_CORRIENTE', 'DEUDORA', FALSE, 'Inventario valorizado'),
    ('110501', 'IVA CREDITO FISCAL', 'ACTIVO', 'ACTIVO_CORRIENTE', 'DEUDORA', FALSE, 'IVA crédito fiscal'),
    ('110601', 'ANTICIPOS A RENDIR / FONDOS POR RENDIR', 'ACTIVO', 'ACTIVO_CORRIENTE', 'DEUDORA', FALSE, 'Fondos por rendir'),
    ('113701', 'CUENTAS POR COBRAR LEASING FINANCIERO', 'ACTIVO', 'ACTIVO_CORRIENTE', 'DEUDORA', FALSE, 'Principal leasing financiero'),
    ('113801', 'CUENTAS POR COBRAR LEASING OPERATIVO', 'ACTIVO', 'ACTIVO_CORRIENTE', 'DEUDORA', FALSE, 'Cartera leasing operativo'),
    ('120801', 'ACTIVO LEASING OPERATIVO', 'ACTIVO', 'ACTIVO_NO_CORRIENTE', 'DEUDORA', FALSE, 'Activo fijo leasing operativo'),
    ('120899', 'DEPRECIACION ACUMULADA LEASING OPERATIVO', 'ACTIVO', 'ACTIVO_NO_CORRIENTE', 'ACREEDORA', FALSE, 'Contra-cuenta depreciación acumulada leasing operativo'),
    ('210101', 'PROVEEDORES', 'PASIVO', 'PASIVO_CORRIENTE', 'ACREEDORA', FALSE, 'Proveedores por pagar'),
    ('210110', 'PROVEEDORES POR FACTURAR', 'PASIVO', 'PASIVO_CORRIENTE', 'ACREEDORA', FALSE, 'Mercadería recibida y pendiente de factura'),
    ('210201', 'IVA DEBITO FISCAL', 'PASIVO', 'PASIVO_CORRIENTE', 'ACREEDORA', FALSE, 'IVA débito fiscal'),
    ('210701', 'OBLIGACIONES LEASING FINANCIERO', 'PASIVO', 'PASIVO_CORRIENTE', 'ACREEDORA', FALSE, 'Obligaciones leasing financiero'),
    ('310101', 'CAPITAL', 'PATRIMONIO', 'PATRIMONIO', 'ACREEDORA', FALSE, 'Capital social'),
    ('310201', 'RESULTADOS ACUMULADOS', 'PATRIMONIO', 'PATRIMONIO', 'ACREEDORA', FALSE, 'Resultados acumulados'),
    ('310301', 'RESULTADO DEL EJERCICIO', 'PATRIMONIO', 'PATRIMONIO', 'ACREEDORA', FALSE, 'Resultado del ejercicio'),
    ('410101', 'VENTAS', 'INGRESO', 'INGRESO_OPERACIONAL', 'ACREEDORA', TRUE, 'Ventas operacionales'),
    ('410701', 'INGRESOS FINANCIEROS LEASING', 'INGRESO', 'INGRESO_OPERACIONAL', 'ACREEDORA', FALSE, 'Intereses leasing financiero'),
    ('510101', 'COSTO DE VENTAS', 'COSTO', 'COSTO_VENTA', 'DEUDORA', TRUE, 'Costo directo de ventas'),
    ('610104', 'GASTOS GENERALES / ADMINISTRATIVOS', 'GASTO', 'GASTO_ADMINISTRACION', 'DEUDORA', TRUE, 'Gastos administrativos'),
    ('610201', 'DEPRECIACION DEL EJERCICIO', 'GASTO', 'GASTO_ADMINISTRACION', 'DEUDORA', TRUE, 'Depreciación del ejercicio'),
    ('630101', 'INTERESES Y GASTOS FINANCIEROS', 'GASTO', 'GASTO_FINANCIERO', 'DEUDORA', TRUE, 'Intereses y gastos financieros')
) AS v(codigo, nombre, tipo, clasificacion, naturaleza, requiere_cc, descripcion)
JOIN fin.plan_cuenta p ON p.codigo = CASE
    WHEN v.codigo LIKE '11%' THEN '110000'
    WHEN v.codigo LIKE '12%' THEN '120000'
    WHEN v.codigo LIKE '21%' THEN '210000'
    WHEN v.codigo LIKE '31%' THEN '310000'
    WHEN v.codigo LIKE '41%' THEN '410000'
    WHEN v.codigo LIKE '51%' THEN '510000'
    WHEN v.codigo LIKE '61%' THEN '610000'
    ELSE '630000'
END
ON CONFLICT (codigo) DO UPDATE
SET nombre = EXCLUDED.nombre,
    cuenta_padre_id = EXCLUDED.cuenta_padre_id,
    tipo = EXCLUDED.tipo,
    clasificacion = EXCLUDED.clasificacion,
    naturaleza = EXCLUDED.naturaleza,
    acepta_movimiento = EXCLUDED.acepta_movimiento,
    requiere_centro_costo = EXCLUDED.requiere_centro_costo,
    estado = EXCLUDED.estado,
    descripcion = EXCLUDED.descripcion;
