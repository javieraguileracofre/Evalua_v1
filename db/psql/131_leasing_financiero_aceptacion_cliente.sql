-- 131_leasing_financiero_aceptacion_cliente.sql
-- GPS / gastos administrativos + aceptación del cliente post-crédito.
-- Idempotente.

BEGIN;

ALTER TABLE public.comercial_lf_cotizaciones
    ADD COLUMN IF NOT EXISTS gps_monto NUMERIC(18, 2) NULL,
    ADD COLUMN IF NOT EXISTS financia_gps BOOLEAN NOT NULL DEFAULT FALSE,
    ADD COLUMN IF NOT EXISTS gastos_administrativos NUMERIC(18, 2) NULL,
    ADD COLUMN IF NOT EXISTS financia_gastos_admin BOOLEAN NOT NULL DEFAULT FALSE,
    ADD COLUMN IF NOT EXISTS aceptada_en TIMESTAMPTZ NULL,
    ADD COLUMN IF NOT EXISTS aceptada_por VARCHAR(200) NULL,
    ADD COLUMN IF NOT EXISTS condiciones_aceptadas TEXT NOT NULL DEFAULT '',
    ADD COLUMN IF NOT EXISTS snapshot_aceptacion_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    ADD COLUMN IF NOT EXISTS pdf_aceptacion_path VARCHAR(500) NULL,
    ADD COLUMN IF NOT EXISTS email_aceptacion_enviado_en TIMESTAMPTZ NULL,
    ADD COLUMN IF NOT EXISTS email_aceptacion_destino VARCHAR(255) NULL;

CREATE INDEX IF NOT EXISTS ix_lf_cot_aceptada_en
    ON public.comercial_lf_cotizaciones (aceptada_en DESC)
    WHERE aceptada_en IS NOT NULL;

COMMIT;
