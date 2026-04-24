-- db/psql/004_migracion_proveedor_fin.sql
-- -*- coding: utf-8 -*-

BEGIN;

CREATE SCHEMA IF NOT EXISTS fin;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM pg_type t
        JOIN pg_namespace n ON n.oid = t.typnamespace
        WHERE n.nspname = 'fin'
          AND t.typname = 'estado_simple'
    ) THEN
        CREATE TYPE fin.estado_simple AS ENUM ('ACTIVO', 'INACTIVO', 'BLOQUEADO');
    END IF;
END $$;

CREATE OR REPLACE FUNCTION public.set_updated_at()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
BEGIN
    NEW.updated_at := NOW();
    RETURN NEW;
END;
$$;

CREATE TABLE IF NOT EXISTS fin.proveedor_fin (
    id BIGSERIAL PRIMARY KEY,
    proveedor_id BIGINT NOT NULL,
    condicion_pago_dias INTEGER NOT NULL DEFAULT 30,
    limite_credito NUMERIC(18,2) NOT NULL DEFAULT 0,
    estado fin.estado_simple NOT NULL DEFAULT 'ACTIVO',
    notas TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT ux_proveedor_fin_proveedor UNIQUE (proveedor_id),
    CONSTRAINT fk_proveedor_fin_proveedor
        FOREIGN KEY (proveedor_id)
        REFERENCES public.proveedor(id)
        ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS ix_proveedor_fin_proveedor
    ON fin.proveedor_fin (proveedor_id);

CREATE INDEX IF NOT EXISTS ix_proveedor_fin_estado
    ON fin.proveedor_fin (estado);

DROP TRIGGER IF EXISTS trg_proveedor_fin_updated_at ON fin.proveedor_fin;

CREATE TRIGGER trg_proveedor_fin_updated_at
BEFORE UPDATE ON fin.proveedor_fin
FOR EACH ROW
EXECUTE FUNCTION public.set_updated_at();

INSERT INTO fin.proveedor_fin (
    proveedor_id,
    condicion_pago_dias,
    limite_credito,
    estado,
    notas,
    created_at,
    updated_at
)
SELECT
    p.id,
    COALESCE(fp.condicion_pago_dias, 30),
    COALESCE(fp.limite_credito, 0),
    COALESCE(fp.estado, 'ACTIVO')::fin.estado_simple,
    fp.notas,
    COALESCE(fp.created_at, NOW()),
    COALESCE(fp.updated_at, NOW())
FROM fin.proveedor fp
JOIN public.proveedor p
  ON COALESCE(p.rut_normalizado, public.fn_normalizar_rut(p.rut))
   = COALESCE(fp.rut_normalizado, public.fn_normalizar_rut(fp.rut))
ON CONFLICT (proveedor_id) DO UPDATE
SET
    condicion_pago_dias = EXCLUDED.condicion_pago_dias,
    limite_credito = EXCLUDED.limite_credito,
    estado = EXCLUDED.estado,
    notas = EXCLUDED.notas,
    updated_at = NOW();

INSERT INTO fin.proveedor_fin (
    proveedor_id,
    condicion_pago_dias,
    limite_credito,
    estado,
    notas
)
SELECT
    p.id,
    COALESCE(p.condicion_pago_dias, 30),
    COALESCE(p.limite_credito, 0),
    CASE
        WHEN COALESCE(p.activo, TRUE) = TRUE THEN 'ACTIVO'::fin.estado_simple
        ELSE 'INACTIVO'::fin.estado_simple
    END,
    p.notas
FROM public.proveedor p
LEFT JOIN fin.proveedor_fin pf
  ON pf.proveedor_id = p.id
WHERE pf.id IS NULL;

COMMIT;