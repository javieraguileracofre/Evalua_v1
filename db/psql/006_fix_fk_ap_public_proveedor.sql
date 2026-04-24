-- db/psql/006_fix_fk_ap_public_proveedor.sql
-- -*- coding: utf-8 -*-

BEGIN;

-- ============================================================
-- VALIDACIONES PREVIAS
-- ============================================================

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM information_schema.tables
        WHERE table_schema = 'public'
          AND table_name = 'proveedor'
    ) THEN
        RAISE EXCEPTION 'No existe public.proveedor';
    END IF;

    IF NOT EXISTS (
        SELECT 1
        FROM information_schema.tables
        WHERE table_schema = 'public'
          AND table_name = 'proveedor_banco'
    ) THEN
        RAISE EXCEPTION 'No existe public.proveedor_banco';
    END IF;

    IF NOT EXISTS (
        SELECT 1
        FROM information_schema.tables
        WHERE table_schema = 'fin'
          AND table_name = 'ap_documento'
    ) THEN
        RAISE EXCEPTION 'No existe fin.ap_documento';
    END IF;

    IF NOT EXISTS (
        SELECT 1
        FROM information_schema.tables
        WHERE table_schema = 'fin'
          AND table_name = 'ap_pago'
    ) THEN
        RAISE EXCEPTION 'No existe fin.ap_pago';
    END IF;
END $$;

-- ============================================================
-- LIMPIEZA DE CONSTRAINTS ACTUALES
-- ============================================================

ALTER TABLE fin.ap_documento
    DROP CONSTRAINT IF EXISTS ap_documento_proveedor_id_fkey;

ALTER TABLE fin.ap_pago
    DROP CONSTRAINT IF EXISTS ap_pago_proveedor_id_fkey;

ALTER TABLE fin.ap_pago
    DROP CONSTRAINT IF EXISTS ap_pago_banco_proveedor_id_fkey;

-- ============================================================
-- RECREAR FKs HACIA MAESTROS EN public
-- ============================================================

ALTER TABLE fin.ap_documento
    ADD CONSTRAINT ap_documento_proveedor_id_fkey
    FOREIGN KEY (proveedor_id)
    REFERENCES public.proveedor(id)
    ON DELETE RESTRICT;

ALTER TABLE fin.ap_pago
    ADD CONSTRAINT ap_pago_proveedor_id_fkey
    FOREIGN KEY (proveedor_id)
    REFERENCES public.proveedor(id)
    ON DELETE RESTRICT;

ALTER TABLE fin.ap_pago
    ADD CONSTRAINT ap_pago_banco_proveedor_id_fkey
    FOREIGN KEY (banco_proveedor_id)
    REFERENCES public.proveedor_banco(id)
    ON DELETE SET NULL;

COMMIT;