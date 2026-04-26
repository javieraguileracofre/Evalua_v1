BEGIN;

-- ============================================================
-- Workflow post-cotización Leasing Financiero (idempotente)
-- Etapas: ANALISIS_CREDITO -> ORDEN_COMPRA -> CONTRATO_FIRMADO
--         -> ACTA_RECEPCION -> ACTIVACION_CONTABLE
-- ============================================================

ALTER TABLE IF EXISTS public.comercial_lf_cotizaciones
    ADD COLUMN IF NOT EXISTS workflow_json JSONB NOT NULL DEFAULT '{}'::jsonb;

CREATE TABLE IF NOT EXISTS public.comercial_lf_documento_proceso (
    id BIGSERIAL PRIMARY KEY,
    cotizacion_id BIGINT NOT NULL
        REFERENCES public.comercial_lf_cotizaciones(id)
        ON DELETE CASCADE,
    modulo VARCHAR(40) NOT NULL,         -- orden_compra | contrato | acta_recepcion
    version_n INTEGER NOT NULL DEFAULT 1,
    estado VARCHAR(20) NOT NULL DEFAULT 'VIGENTE',
    payload_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    usuario VARCHAR(200) NOT NULL DEFAULT 'sistema',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_lf_doc_proceso_version UNIQUE (cotizacion_id, modulo, version_n)
);

CREATE INDEX IF NOT EXISTS ix_lf_doc_proceso_cot
    ON public.comercial_lf_documento_proceso (cotizacion_id, modulo, version_n DESC);

COMMIT;

