-- db/psql/101_credito_riesgo.sql
-- Módulo Crédito y Riesgo (macro + micro, score 0-1000, decisiones)
-- Idempotente. Requiere public.clientes.

BEGIN;

CREATE TABLE IF NOT EXISTS public.credito_politica (
    id              BIGSERIAL PRIMARY KEY,
    clave           VARCHAR(80) NOT NULL UNIQUE,
    valor_json      JSONB NOT NULL,
    descripcion     TEXT NULL,
    activo          BOOLEAN NOT NULL DEFAULT TRUE,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS ix_credito_politica_activo
    ON public.credito_politica (activo);

INSERT INTO public.credito_politica (clave, valor_json, descripcion)
VALUES
(
    'ponderaciones_v1',
    '{
      "capacidad_pago": 0.25,
      "historial_pago": 0.25,
      "endeudamiento": 0.15,
      "liquidez_flujo": 0.15,
      "antiguedad": 0.10,
      "garantias": 0.05,
      "macro_sectorial": 0.05
    }'::jsonb,
    'Pesos del score 0-1000 (EvaluaERP motor v1).'
),
(
    'macro_referencia_chile_202602',
    '{
      "inflacion_anual_pct": 2.4,
      "pib_crecimiento_pct": 2.5,
      "morosidad_90_mas_pct": 2.35,
      "cartera_deteriorada_pct": 8.45,
      "tpm_referencia_anual_pct": 5.25,
      "nota": "Referencia interna Feb-2026: inflación y PIB BCCh; mora y cartera CMF."
    }'::jsonb,
    'Snapshot macro base (editable desde SQL).'
)
ON CONFLICT (clave) DO NOTHING;

CREATE TABLE IF NOT EXISTS public.credito_solicitud (
    id                          BIGSERIAL PRIMARY KEY,
    cliente_id                  BIGINT NOT NULL REFERENCES public.clientes(id) ON DELETE CASCADE,
    comercial_lf_cotizacion_id  BIGINT NULL,

    codigo                      VARCHAR(40) NULL UNIQUE,
    tipo_persona                VARCHAR(20) NOT NULL DEFAULT 'NATURAL',
    producto                    VARCHAR(40) NOT NULL DEFAULT 'LEASING_FIN',
    sector_actividad            VARCHAR(120) NULL,
    moneda                      VARCHAR(10) NOT NULL DEFAULT 'CLP',

    monto_solicitado            NUMERIC(18, 2) NOT NULL,
    plazo_solicitado            INTEGER NOT NULL,

    ingreso_mensual             NUMERIC(18, 2) NOT NULL DEFAULT 0,
    gastos_mensual              NUMERIC(18, 2) NOT NULL DEFAULT 0,
    deuda_cuotas_mensual        NUMERIC(18, 2) NOT NULL DEFAULT 0,
    cuota_propuesta              NUMERIC(18, 2) NOT NULL DEFAULT 0,

    tipo_contrato               VARCHAR(40) NULL,
    mora_max_dias_12m           INTEGER NOT NULL DEFAULT 0,
    protestos                   INTEGER NOT NULL DEFAULT 0,
    castigos                    INTEGER NOT NULL DEFAULT 0,
    reprogramaciones            INTEGER NOT NULL DEFAULT 0,

    ventas_anual                NUMERIC(18, 2) NOT NULL DEFAULT 0,
    margen_bruto_pct            NUMERIC(9, 4) NOT NULL DEFAULT 0,
    ebitda_anual                NUMERIC(18, 2) NOT NULL DEFAULT 0,
    utilidad_neta_anual         NUMERIC(18, 2) NOT NULL DEFAULT 0,
    flujo_caja_mensual          NUMERIC(18, 2) NOT NULL DEFAULT 0,
    capital_trabajo             NUMERIC(18, 2) NOT NULL DEFAULT 0,

    deuda_total                 NUMERIC(18, 2) NOT NULL DEFAULT 0,
    patrimonio                  NUMERIC(18, 2) NOT NULL DEFAULT 0,
    liquidez_corriente          NUMERIC(12, 4) NULL,

    antiguedad_meses_natural    INTEGER NOT NULL DEFAULT 0,
    anios_operacion_empresa     INTEGER NOT NULL DEFAULT 0,

    garantia_tipo               VARCHAR(80) NULL,
    garantia_valor_comercial    NUMERIC(18, 2) NOT NULL DEFAULT 0,
    garantia_valor_liquidacion  NUMERIC(18, 2) NOT NULL DEFAULT 0,

    exposicion_usd_pct          NUMERIC(6, 2) NOT NULL DEFAULT 0,

    estado                      VARCHAR(30) NOT NULL DEFAULT 'BORRADOR',
    observaciones               TEXT NOT NULL DEFAULT '',

    creado_en                   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    actualizado_en              TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    CONSTRAINT chk_credito_sol_tipo_persona
        CHECK (tipo_persona IN ('NATURAL', 'JURIDICA')),
    CONSTRAINT chk_credito_sol_estado
        CHECK (estado IN (
            'BORRADOR', 'EN_EVALUACION', 'APROBADA', 'RECHAZADA', 'COMITE', 'CONDICIONES', 'ARCHIVADA'
        ))
);

CREATE INDEX IF NOT EXISTS ix_credito_sol_cliente
    ON public.credito_solicitud (cliente_id);
CREATE INDEX IF NOT EXISTS ix_credito_sol_estado
    ON public.credito_solicitud (estado);
CREATE INDEX IF NOT EXISTS ix_credito_sol_cotizacion
    ON public.credito_solicitud (comercial_lf_cotizacion_id);

CREATE TABLE IF NOT EXISTS public.credito_evaluacion (
    id                          BIGSERIAL PRIMARY KEY,
    solicitud_id                BIGINT NOT NULL REFERENCES public.credito_solicitud(id) ON DELETE CASCADE,

    score_total                 NUMERIC(7, 2) NOT NULL,
    categoria                   CHAR(1) NOT NULL,
    clasificacion_riesgo        VARCHAR(20) NOT NULL,

    monto_maximo_sugerido       NUMERIC(18, 2) NOT NULL,
    plazo_maximo_sugerido       INTEGER NOT NULL,
    tasa_sugerida_anual         NUMERIC(9, 6) NOT NULL,

    recomendacion               VARCHAR(30) NOT NULL,
    explicacion                 TEXT NOT NULL DEFAULT '',
    desglose_json               JSONB NOT NULL DEFAULT '{}'::jsonb,
    macro_json                  JSONB NOT NULL DEFAULT '{}'::jsonb,
    stress_cuotas_json          JSONB NOT NULL DEFAULT '{}'::jsonb,
    motor_version               VARCHAR(20) NOT NULL DEFAULT 'v1',

    creado_en                   TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    CONSTRAINT chk_credito_eval_cat CHECK (categoria IN ('A', 'B', 'C', 'D', 'E')),
    CONSTRAINT chk_credito_eval_clasif CHECK (clasificacion_riesgo IN ('BAJO', 'MEDIO', 'ALTO', 'RECHAZADO')),
    CONSTRAINT chk_credito_eval_rec CHECK (recomendacion IN ('APROBAR', 'CONDICIONES', 'COMITE', 'RECHAZAR'))
);

CREATE INDEX IF NOT EXISTS ix_credito_eval_solicitud
    ON public.credito_evaluacion (solicitud_id, creado_en DESC);

CREATE TABLE IF NOT EXISTS public.credito_garantia (
    id                          BIGSERIAL PRIMARY KEY,
    solicitud_id                BIGINT NOT NULL REFERENCES public.credito_solicitud(id) ON DELETE CASCADE,
    tipo                        VARCHAR(80) NOT NULL,
    descripcion                 TEXT NULL,
    valor_comercial             NUMERIC(18, 2) NOT NULL DEFAULT 0,
    valor_liquidacion           NUMERIC(18, 2) NOT NULL DEFAULT 0,
    cobertura_pct               NUMERIC(9, 4) NULL,
    creado_en                   TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS ix_credito_gar_solicitud ON public.credito_garantia (solicitud_id);

CREATE TABLE IF NOT EXISTS public.credito_documento (
    id                          BIGSERIAL PRIMARY KEY,
    solicitud_id                BIGINT NOT NULL REFERENCES public.credito_solicitud(id) ON DELETE CASCADE,
    tipo_documento              VARCHAR(80) NOT NULL,
    referencia                  VARCHAR(255) NOT NULL DEFAULT '',
    creado_en                   TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS ix_credito_doc_solicitud ON public.credito_documento (solicitud_id);

CREATE TABLE IF NOT EXISTS public.credito_comite (
    id                          BIGSERIAL PRIMARY KEY,
    solicitud_id                BIGINT NOT NULL REFERENCES public.credito_solicitud(id) ON DELETE CASCADE,
    estado                      VARCHAR(20) NOT NULL DEFAULT 'PENDIENTE',
    resumen                     TEXT NOT NULL DEFAULT '',
    decision                    VARCHAR(30) NULL,
    comentario                  TEXT NOT NULL DEFAULT '',
    analista                    VARCHAR(200) NOT NULL DEFAULT 'sistema',
    fecha_apertura              TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    fecha_cierre                TIMESTAMPTZ NULL,

    CONSTRAINT chk_credito_comite_estado CHECK (estado IN ('PENDIENTE', 'RESUELTO'))
);

CREATE INDEX IF NOT EXISTS ix_credito_comite_sol ON public.credito_comite (solicitud_id);

CREATE TABLE IF NOT EXISTS public.credito_historial (
    id                          BIGSERIAL PRIMARY KEY,
    solicitud_id                BIGINT NOT NULL REFERENCES public.credito_solicitud(id) ON DELETE CASCADE,
    evento                      VARCHAR(80) NOT NULL,
    detalle_json                JSONB NULL,
    usuario                     VARCHAR(200) NOT NULL DEFAULT 'sistema',
    creado_en                   TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS ix_credito_hist_sol ON public.credito_historial (solicitud_id, creado_en DESC);

CREATE OR REPLACE FUNCTION public.trg_credito_solicitud_set_updated()
RETURNS trigger AS $$
BEGIN
    NEW.actualizado_en := NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_credito_solicitud_updated ON public.credito_solicitud;
CREATE TRIGGER trg_credito_solicitud_updated
    BEFORE UPDATE ON public.credito_solicitud
    FOR EACH ROW
    EXECUTE FUNCTION public.trg_credito_solicitud_set_updated();

COMMIT;
