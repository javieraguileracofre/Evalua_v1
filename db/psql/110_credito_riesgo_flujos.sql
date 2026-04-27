BEGIN;

-- ============================================================
-- Crédito y Riesgo: flujos RAPIDO / PROFUNDO + decisión clara
-- Idempotente
-- ============================================================

ALTER TABLE IF EXISTS public.credito_solicitud
    ADD COLUMN IF NOT EXISTS concentracion_ingresos_pct NUMERIC(6,2) NOT NULL DEFAULT 0;

ALTER TABLE IF EXISTS public.credito_solicitud
    ADD COLUMN IF NOT EXISTS historial_tributario VARCHAR(20) NOT NULL DEFAULT 'SIN_INFO';

ALTER TABLE IF EXISTS public.credito_evaluacion
    ADD COLUMN IF NOT EXISTS flujo_evaluacion VARCHAR(20) NOT NULL DEFAULT 'PROFUNDO';

ALTER TABLE IF EXISTS public.credito_evaluacion
    ADD COLUMN IF NOT EXISTS decision_motor VARCHAR(20) NOT NULL DEFAULT 'PENDIENTE';

ALTER TABLE IF EXISTS public.credito_evaluacion
    ADD COLUMN IF NOT EXISTS log_reglas_json JSONB NOT NULL DEFAULT '{}'::jsonb;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM pg_constraint
        WHERE conname = 'chk_credito_sol_historial_tributario'
    ) THEN
        ALTER TABLE public.credito_solicitud
            ADD CONSTRAINT chk_credito_sol_historial_tributario
            CHECK (historial_tributario IN ('SIN_INFO', 'AL_DIA', 'OBSERVADO', 'IRREGULAR'));
    END IF;
END $$;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM pg_constraint
        WHERE conname = 'chk_credito_eval_flujo'
    ) THEN
        ALTER TABLE public.credito_evaluacion
            ADD CONSTRAINT chk_credito_eval_flujo
            CHECK (flujo_evaluacion IN ('RAPIDO', 'PROFUNDO'));
    END IF;
END $$;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM pg_constraint
        WHERE conname = 'chk_credito_eval_decision_motor'
    ) THEN
        ALTER TABLE public.credito_evaluacion
            ADD CONSTRAINT chk_credito_eval_decision_motor
            CHECK (decision_motor IN ('APROBAR', 'CONDICIONES', 'RECHAZAR', 'PENDIENTE'));
    END IF;
END $$;

CREATE INDEX IF NOT EXISTS ix_credito_eval_flujo
    ON public.credito_evaluacion (flujo_evaluacion, creado_en DESC);

INSERT INTO public.credito_politica (clave, valor_json, descripcion)
VALUES
(
    'reglas_flujos_credito_v1',
    '{
      "rapido_score_aprobacion": 300,
      "rapido_endeudamiento_max_pct": 45,
      "rapido_antiguedad_min_anios": 1,
      "profundo_dscr_aprobacion_min": 1.15,
      "profundo_dscr_rechazo_max": 1.00,
      "profundo_dscr_alerta_min": 1.10,
      "profundo_dscr_fuerte_min": 1.30,
      "profundo_garantia_aprobacion_min_pct": 80,
      "profundo_garantia_rechazo_max_pct": 70,
      "profundo_garantia_fuerte_min_pct": 120,
      "profundo_concentracion_alta_pct": 60,
      "profundo_concentracion_baja_pct": 35
    }'::jsonb,
    'Umbrales editables para flujos RAPIDO y PROFUNDO del motor de credito.'
)
ON CONFLICT (clave) DO NOTHING;

COMMIT;
