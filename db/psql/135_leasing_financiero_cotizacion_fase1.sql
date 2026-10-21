-- 135_leasing_financiero_cotizacion_fase1.sql
-- Tipo de tasa (mensual/anual) para cotización de leasing financiero.
-- Idempotente.

BEGIN;

ALTER TABLE public.comercial_lf_cotizaciones
    ADD COLUMN IF NOT EXISTS tasa_tipo VARCHAR(20) NOT NULL DEFAULT 'ANUAL';

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'chk_lf_tasa_tipo'
    ) THEN
        ALTER TABLE public.comercial_lf_cotizaciones
            ADD CONSTRAINT chk_lf_tasa_tipo
            CHECK (tasa_tipo IN ('ANUAL', 'MENSUAL'));
    END IF;
END $$;

COMMIT;
