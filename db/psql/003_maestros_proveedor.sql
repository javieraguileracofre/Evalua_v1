-- db/psql/003_maestros_proveedor.sql
-- -*- coding: utf-8 -*-
BEGIN;

CREATE TABLE IF NOT EXISTS public.proveedor (
    id                    BIGSERIAL PRIMARY KEY,
    rut                   VARCHAR(20) NOT NULL,
    rut_normalizado       VARCHAR(20),
    razon_social          VARCHAR(180) NOT NULL,
    nombre_fantasia       VARCHAR(180),
    giro                  VARCHAR(180),
    email                 VARCHAR(180),
    telefono              VARCHAR(50),
    sitio_web             VARCHAR(180),
    condicion_pago_dias   INTEGER NOT NULL DEFAULT 30,
    limite_credito        NUMERIC(18,2) NOT NULL DEFAULT 0,
    activo                BOOLEAN NOT NULL DEFAULT TRUE,
    notas                 TEXT,
    created_at            TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at            TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS ix_proveedor_razon_social
    ON public.proveedor (razon_social);

CREATE UNIQUE INDEX IF NOT EXISTS ux_proveedor_rut_normalizado
    ON public.proveedor (rut_normalizado);


CREATE TABLE IF NOT EXISTS public.proveedor_banco (
    id                BIGSERIAL PRIMARY KEY,
    proveedor_id      BIGINT NOT NULL REFERENCES public.proveedor(id) ON DELETE CASCADE,
    banco             VARCHAR(120) NOT NULL,
    tipo_cuenta       VARCHAR(60) NOT NULL,
    numero_cuenta     VARCHAR(60) NOT NULL,
    titular           VARCHAR(180),
    rut_titular       VARCHAR(20),
    email_pago        VARCHAR(180),
    es_principal      BOOLEAN NOT NULL DEFAULT FALSE,
    activo            BOOLEAN NOT NULL DEFAULT TRUE,
    created_at        TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at        TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS ix_prov_banco_proveedor
    ON public.proveedor_banco (proveedor_id);

CREATE UNIQUE INDEX IF NOT EXISTS ux_prov_banco_unique
    ON public.proveedor_banco (proveedor_id, banco, tipo_cuenta, numero_cuenta);


CREATE TABLE IF NOT EXISTS public.proveedor_contacto (
    id                BIGSERIAL PRIMARY KEY,
    proveedor_id      BIGINT NOT NULL REFERENCES public.proveedor(id) ON DELETE CASCADE,
    nombre            VARCHAR(120) NOT NULL,
    cargo             VARCHAR(120),
    email             VARCHAR(180),
    telefono          VARCHAR(50),
    es_principal      BOOLEAN NOT NULL DEFAULT FALSE,
    activo            BOOLEAN NOT NULL DEFAULT TRUE,
    created_at        TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at        TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS ix_prov_contacto_proveedor
    ON public.proveedor_contacto (proveedor_id);


CREATE TABLE IF NOT EXISTS public.proveedor_direccion (
    id                BIGSERIAL PRIMARY KEY,
    proveedor_id      BIGINT NOT NULL REFERENCES public.proveedor(id) ON DELETE CASCADE,
    linea1            VARCHAR(180) NOT NULL,
    linea2            VARCHAR(180),
    comuna            VARCHAR(120),
    ciudad            VARCHAR(120),
    region            VARCHAR(120),
    pais              VARCHAR(120) NOT NULL DEFAULT 'Chile',
    codigo_postal     VARCHAR(20),
    es_principal      BOOLEAN NOT NULL DEFAULT FALSE,
    activo            BOOLEAN NOT NULL DEFAULT TRUE,
    created_at        TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at        TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS ix_prov_direccion_proveedor
    ON public.proveedor_direccion (proveedor_id);

-- ============================================================
-- NORMALIZADOR RUT
-- ============================================================

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

-- ============================================================
-- TRIGGER updated_at
-- ============================================================

CREATE OR REPLACE FUNCTION public.set_updated_at()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS trg_proveedor_updated_at ON public.proveedor;
CREATE TRIGGER trg_proveedor_updated_at
BEFORE UPDATE ON public.proveedor
FOR EACH ROW
EXECUTE FUNCTION public.set_updated_at();

DROP TRIGGER IF EXISTS trg_proveedor_banco_updated_at ON public.proveedor_banco;
CREATE TRIGGER trg_proveedor_banco_updated_at
BEFORE UPDATE ON public.proveedor_banco
FOR EACH ROW
EXECUTE FUNCTION public.set_updated_at();

DROP TRIGGER IF EXISTS trg_proveedor_contacto_updated_at ON public.proveedor_contacto;
CREATE TRIGGER trg_proveedor_contacto_updated_at
BEFORE UPDATE ON public.proveedor_contacto
FOR EACH ROW
EXECUTE FUNCTION public.set_updated_at();

DROP TRIGGER IF EXISTS trg_proveedor_direccion_updated_at ON public.proveedor_direccion;
CREATE TRIGGER trg_proveedor_direccion_updated_at
BEFORE UPDATE ON public.proveedor_direccion
FOR EACH ROW
EXECUTE FUNCTION public.set_updated_at();

-- ============================================================
-- TRIGGER rut_normalizado
-- Compatible tanto si la columna es normal como si luego la cambias.
-- Si tu BD la tiene GENERATED ALWAYS, entonces simplemente NO
-- la escribiremos desde Python y este trigger no estorba.
-- ============================================================

CREATE OR REPLACE FUNCTION public.trg_proveedor_set_rut_normalizado()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
BEGIN
    NEW.rut_normalizado := public.fn_normalizar_rut(NEW.rut);
    RETURN NEW;
END;
$$;

DO $$
BEGIN
    IF EXISTS (
        SELECT 1
        FROM information_schema.columns
        WHERE table_schema = 'public'
          AND table_name = 'proveedor'
          AND column_name = 'rut_normalizado'
          AND is_generated = 'NEVER'
    ) THEN
        DROP TRIGGER IF EXISTS trg_proveedor_set_rut_normalizado ON public.proveedor;
        CREATE TRIGGER trg_proveedor_set_rut_normalizado
        BEFORE INSERT OR UPDATE OF rut
        ON public.proveedor
        FOR EACH ROW
        EXECUTE FUNCTION public.trg_proveedor_set_rut_normalizado();
    END IF;
END $$;

COMMIT;