BEGIN;

CREATE TABLE IF NOT EXISTS public.leasing_op_documento_proceso (
    id BIGSERIAL PRIMARY KEY,
    simulacion_id BIGINT NOT NULL REFERENCES public.leasing_op_simulacion(id) ON DELETE CASCADE,
    modulo VARCHAR(40) NOT NULL,
    version_n INTEGER NOT NULL DEFAULT 1,
    estado VARCHAR(20) NOT NULL DEFAULT 'VIGENTE',
    payload_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    usuario VARCHAR(200) NOT NULL DEFAULT 'sistema',
    creado_en TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS ix_leasing_op_doc_proc_sim_mod_creado
    ON public.leasing_op_documento_proceso (simulacion_id, modulo, creado_en DESC);

CREATE UNIQUE INDEX IF NOT EXISTS uq_leasing_op_doc_proc_sim_mod_ver
    ON public.leasing_op_documento_proceso (simulacion_id, modulo, version_n);

COMMIT;
