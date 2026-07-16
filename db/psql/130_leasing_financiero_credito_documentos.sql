-- 130_leasing_financiero_credito_documentos.sql
-- Documentos del cliente para análisis de crédito leasing + ratios extendidos.
-- Idempotente.

BEGIN;

-- ============================================================
-- Análisis: campos de balance / IVA / ratios calculados
-- ============================================================
ALTER TABLE public.comercial_lf_analisis_credito
    ADD COLUMN IF NOT EXISTS activo_corriente NUMERIC(18, 2) NOT NULL DEFAULT 0,
    ADD COLUMN IF NOT EXISTS pasivo_corriente NUMERIC(18, 2) NOT NULL DEFAULT 0,
    ADD COLUMN IF NOT EXISTS activo_total NUMERIC(18, 2) NOT NULL DEFAULT 0,
    ADD COLUMN IF NOT EXISTS pasivo_total NUMERIC(18, 2) NOT NULL DEFAULT 0,
    ADD COLUMN IF NOT EXISTS utilidad_neta_anual NUMERIC(18, 2) NOT NULL DEFAULT 0,
    ADD COLUMN IF NOT EXISTS gastos_financieros_anual NUMERIC(18, 2) NOT NULL DEFAULT 0,
    ADD COLUMN IF NOT EXISTS ventas_12m_iva NUMERIC(18, 2) NOT NULL DEFAULT 0,
    ADD COLUMN IF NOT EXISTS iva_debito_12m NUMERIC(18, 2) NOT NULL DEFAULT 0,
    ADD COLUMN IF NOT EXISTS iva_credito_12m NUMERIC(18, 2) NOT NULL DEFAULT 0,
    ADD COLUMN IF NOT EXISTS liquidez_corriente NUMERIC(9, 4) NULL,
    ADD COLUMN IF NOT EXISTS margen_ebitda_pct NUMERIC(9, 4) NULL,
    ADD COLUMN IF NOT EXISTS endeudamiento_pct NUMERIC(9, 4) NULL,
    ADD COLUMN IF NOT EXISTS capital_trabajo NUMERIC(18, 2) NULL,
    ADD COLUMN IF NOT EXISTS cobertura_gastos_fin NUMERIC(9, 4) NULL,
    ADD COLUMN IF NOT EXISTS rentabilidad_neta_pct NUMERIC(9, 4) NULL,
    ADD COLUMN IF NOT EXISTS ratios_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    ADD COLUMN IF NOT EXISTS documentos_resumen_json JSONB NOT NULL DEFAULT '{}'::jsonb;

-- ============================================================
-- Documentos cargados por cotización (carpeta tributaria, IVA, balance)
-- ============================================================
CREATE TABLE IF NOT EXISTS public.comercial_lf_credito_documento (
    id                  BIGSERIAL PRIMARY KEY,
    cotizacion_id       BIGINT NOT NULL
                            REFERENCES public.comercial_lf_cotizaciones(id) ON DELETE CASCADE,
    cliente_id          BIGINT NOT NULL
                            REFERENCES public.clientes(id) ON DELETE CASCADE,
    tipo_documento      VARCHAR(40) NOT NULL,
    nombre_archivo      VARCHAR(255) NOT NULL,
    mime_type           VARCHAR(120) NOT NULL DEFAULT 'application/octet-stream',
    storage_path        VARCHAR(500) NOT NULL,
    hash_sha256         VARCHAR(64) NULL,
    tamano_bytes        BIGINT NOT NULL DEFAULT 0,
    estado              VARCHAR(20) NOT NULL DEFAULT 'RECIBIDO',
    periodo_desde       DATE NULL,
    periodo_hasta       DATE NULL,
    datos_extraidos     JSONB NOT NULL DEFAULT '{}'::jsonb,
    observaciones       TEXT NOT NULL DEFAULT '',
    cargado_por         VARCHAR(200) NOT NULL DEFAULT 'sistema',
    creado_en           TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    actualizado_en      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT chk_lf_credito_doc_tipo CHECK (
        tipo_documento IN (
            'CARPETA_TRIBUTARIA',
            'CERTIFICADO_IVA',
            'BALANCE_GENERAL',
            'OTRO'
        )
    ),
    CONSTRAINT chk_lf_credito_doc_estado CHECK (
        estado IN ('PENDIENTE', 'RECIBIDO', 'VALIDADO', 'RECHAZADO', 'OBSOLETO')
    )
);

CREATE INDEX IF NOT EXISTS ix_lf_credito_doc_cotizacion
    ON public.comercial_lf_credito_documento (cotizacion_id, tipo_documento, creado_en DESC);

CREATE INDEX IF NOT EXISTS ix_lf_credito_doc_cliente
    ON public.comercial_lf_credito_documento (cliente_id);

CREATE OR REPLACE FUNCTION public.trg_lf_credito_doc_set_updated()
RETURNS trigger AS $$
BEGIN
    NEW.actualizado_en := NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_lf_credito_doc_updated ON public.comercial_lf_credito_documento;
CREATE TRIGGER trg_lf_credito_doc_updated
    BEFORE UPDATE ON public.comercial_lf_credito_documento
    FOR EACH ROW
    EXECUTE FUNCTION public.trg_lf_credito_doc_set_updated();

COMMIT;
