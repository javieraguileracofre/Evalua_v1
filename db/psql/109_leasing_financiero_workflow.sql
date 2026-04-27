BEGIN;

-- ============================================================
-- Workflow post-cotización Leasing Financiero (idempotente)
-- Etapas: ANALISIS_CREDITO -> ORDEN_COMPRA -> CONTRATO_FIRMADO
--         -> ACTA_RECEPCION -> ACTIVACION_CONTABLE
-- ============================================================

ALTER TABLE IF EXISTS public.comercial_lf_cotizaciones
    ADD COLUMN IF NOT EXISTS workflow_json JSONB NOT NULL DEFAULT '{}'::jsonb;

ALTER TABLE IF EXISTS public.comercial_lf_cotizaciones
    ADD COLUMN IF NOT EXISTS numero_operacion VARCHAR(50),
    ADD COLUMN IF NOT EXISTS numero_contrato VARCHAR(50),
    ADD COLUMN IF NOT EXISTS asiento_id BIGINT,
    ADD COLUMN IF NOT EXISTS fecha_aprobacion DATE,
    ADD COLUMN IF NOT EXISTS fecha_formalizacion DATE,
    ADD COLUMN IF NOT EXISTS fecha_activacion DATE,
    ADD COLUMN IF NOT EXISTS fecha_vigencia_desde DATE,
    ADD COLUMN IF NOT EXISTS fecha_vigencia_hasta DATE;

UPDATE public.comercial_lf_cotizaciones
SET estado = CASE
    WHEN estado = 'PENDIENTE' THEN 'BORRADOR'
    WHEN estado = 'PRE_APROBADA' THEN 'APROBADA_CONDICIONES'
    WHEN estado = 'CONTRATADA' THEN 'DOCUMENTACION_COMPLETA'
    WHEN estado = 'EN_GESTION' THEN 'EN_FORMALIZACION'
    WHEN estado = 'NUEVA' THEN 'BORRADOR'
    WHEN estado = 'APROBADO_CON_OBSERVACIONES' THEN 'APROBADA_CONDICIONES'
    WHEN estado = 'OBSERVACION' THEN 'APROBADA_CONDICIONES'
    ELSE estado
END
WHERE estado IN (
    'PENDIENTE',
    'PRE_APROBADA',
    'CONTRATADA',
    'EN_GESTION',
    'NUEVA',
    'APROBADO_CON_OBSERVACIONES',
    'OBSERVACION'
);

ALTER TABLE IF EXISTS public.comercial_lf_cotizaciones
    DROP CONSTRAINT IF EXISTS chk_comercial_lf_estado;
ALTER TABLE IF EXISTS public.comercial_lf_cotizaciones
    ADD CONSTRAINT chk_comercial_lf_estado CHECK (
        estado IN (
            'BORRADOR',
            'COTIZADA',
            'EN_ANALISIS_COMERCIAL',
            'EN_ANALISIS_CREDITO',
            'APROBADA_CONDICIONES',
            'APROBADA',
            'RECHAZADA',
            'EN_FORMALIZACION',
            'DOCUMENTACION_COMPLETA',
            'ACTIVADA',
            'VIGENTE',
            'ANULADA',
            'PERDIDA_CLIENTE'
        )
    );

CREATE TABLE IF NOT EXISTS public.comercial_lf_documento_proceso (
    id BIGSERIAL PRIMARY KEY,
    cotizacion_id BIGINT NOT NULL
        REFERENCES public.comercial_lf_cotizaciones(id)
        ON DELETE CASCADE,
    modulo VARCHAR(40) NOT NULL,         -- orden_compra | contrato | acta_recepcion | factura_proveedor | pagare | identidad
    version_n INTEGER NOT NULL DEFAULT 1,
    estado VARCHAR(20) NOT NULL DEFAULT 'RECIBIDO',
    payload_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    usuario VARCHAR(200) NOT NULL DEFAULT 'sistema',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_lf_doc_proceso_version UNIQUE (cotizacion_id, modulo, version_n)
);

CREATE INDEX IF NOT EXISTS ix_lf_doc_proceso_cot
    ON public.comercial_lf_documento_proceso (cotizacion_id, modulo, version_n DESC);

ALTER TABLE IF EXISTS public.comercial_lf_analisis_credito
    DROP CONSTRAINT IF EXISTS chk_lf_analisis_recomendacion;

UPDATE public.comercial_lf_analisis_credito
SET recomendacion = CASE
    WHEN UPPER(TRIM(COALESCE(recomendacion, ''))) IN ('OBSERVACION', 'APROBADO_CON_OBSERVACIONES', 'APROBADA_CON_OBSERVACIONES') THEN 'APROBADA_CONDICIONES'
    WHEN UPPER(TRIM(COALESCE(recomendacion, ''))) IN ('APROBADO', 'RECHAZADO', 'APROBADA_CONDICIONES') THEN UPPER(TRIM(recomendacion))
    ELSE 'RECHAZADO'
END
WHERE recomendacion IS NULL
   OR UPPER(TRIM(COALESCE(recomendacion, ''))) NOT IN ('APROBADO', 'RECHAZADO', 'APROBADA_CONDICIONES')
   OR UPPER(TRIM(COALESCE(recomendacion, ''))) IN ('OBSERVACION', 'APROBADO_CON_OBSERVACIONES', 'APROBADA_CON_OBSERVACIONES');

ALTER TABLE IF EXISTS public.comercial_lf_analisis_credito
    ADD CONSTRAINT chk_lf_analisis_recomendacion
        CHECK (recomendacion IN ('APROBADO', 'RECHAZADO', 'APROBADA_CONDICIONES'));

CREATE TABLE IF NOT EXISTS public.comercial_lf_historial (
    id BIGSERIAL PRIMARY KEY,
    cotizacion_id BIGINT NOT NULL
        REFERENCES public.comercial_lf_cotizaciones(id)
        ON DELETE CASCADE,
    tipo_evento VARCHAR(40) NOT NULL,
    estado_desde VARCHAR(40),
    estado_hasta VARCHAR(40),
    comentario TEXT,
    usuario VARCHAR(200) NOT NULL DEFAULT 'sistema',
    metadata_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS ix_lf_historial_cot_fecha
    ON public.comercial_lf_historial (cotizacion_id, created_at DESC);

COMMIT;

