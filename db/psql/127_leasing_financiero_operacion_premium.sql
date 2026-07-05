-- 127_leasing_financiero_operacion_premium.sql
-- Campos operativos, tributarios y métricas para leasing financiero premium.
-- Idempotente: seguro ejecutar más de una vez.

BEGIN;

ALTER TABLE public.comercial_lf_cotizaciones
    ADD COLUMN IF NOT EXISTS bien_descripcion VARCHAR(500) NULL,
    ADD COLUMN IF NOT EXISTS bien_tipo VARCHAR(80) NULL,
    ADD COLUMN IF NOT EXISTS fecha_primera_cuota DATE NULL,
    ADD COLUMN IF NOT EXISTS periodicidad VARCHAR(20) NOT NULL DEFAULT 'MENSUAL',
    ADD COLUMN IF NOT EXISTS comision_apertura NUMERIC(18, 2) NULL,
    ADD COLUMN IF NOT EXISTS comision_apertura_tipo VARCHAR(20) NULL,
    ADD COLUMN IF NOT EXISTS financia_comision BOOLEAN NOT NULL DEFAULT FALSE,
    ADD COLUMN IF NOT EXISTS gastos_operacionales NUMERIC(18, 2) NULL,
    ADD COLUMN IF NOT EXISTS iva_aplica BOOLEAN NOT NULL DEFAULT FALSE,
    ADD COLUMN IF NOT EXISTS iva_tasa NUMERIC(7, 4) NULL,
    ADD COLUMN IF NOT EXISTS iva_recuperable BOOLEAN NOT NULL DEFAULT TRUE,
    ADD COLUMN IF NOT EXISTS observaciones TEXT NULL,
    ADD COLUMN IF NOT EXISTS tir_anual_pct NUMERIC(9, 4) NULL,
    ADD COLUMN IF NOT EXISTS cae_anual_pct NUMERIC(9, 4) NULL,
    ADD COLUMN IF NOT EXISTS metadata_tributaria JSONB NOT NULL DEFAULT '{}'::jsonb;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'chk_lf_periodicidad'
    ) THEN
        ALTER TABLE public.comercial_lf_cotizaciones
            ADD CONSTRAINT chk_lf_periodicidad
            CHECK (periodicidad IN ('MENSUAL', 'TRIMESTRAL', 'SEMESTRAL', 'ANUAL'));
    END IF;
END $$;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'chk_lf_comision_tipo'
    ) THEN
        ALTER TABLE public.comercial_lf_cotizaciones
            ADD CONSTRAINT chk_lf_comision_tipo
            CHECK (
                comision_apertura_tipo IS NULL
                OR comision_apertura_tipo IN ('PORCENTAJE', 'MONTO')
            );
    END IF;
END $$;

COMMIT;
