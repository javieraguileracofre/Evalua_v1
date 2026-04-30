-- 118_remuneraciones_parametros_periodo.sql
-- Snapshot mensual de parametros de calculo por periodo de remuneracion (idempotente).

BEGIN;

CREATE TABLE IF NOT EXISTS public.remuneracion_parametros_periodo (
  id BIGSERIAL PRIMARY KEY,
  periodo_remuneracion_id BIGINT NOT NULL,
  clave VARCHAR(80) NOT NULL,
  valor_numerico NUMERIC(18,6),
  valor_texto VARCHAR(500),
  descripcion VARCHAR(255),
  updated_at TIMESTAMP WITHOUT TIME ZONE NOT NULL DEFAULT NOW()
);

CREATE UNIQUE INDEX IF NOT EXISTS uq_rem_param_periodo_clave
  ON public.remuneracion_parametros_periodo (periodo_remuneracion_id, clave);
CREATE INDEX IF NOT EXISTS ix_rem_param_periodo_periodo
  ON public.remuneracion_parametros_periodo (periodo_remuneracion_id);

DO $$
BEGIN
  IF to_regclass('public.periodos_remuneracion') IS NOT NULL THEN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'fk_rem_param_periodo') THEN
      ALTER TABLE public.remuneracion_parametros_periodo
        ADD CONSTRAINT fk_rem_param_periodo
        FOREIGN KEY (periodo_remuneracion_id) REFERENCES public.periodos_remuneracion(id) ON DELETE CASCADE;
    END IF;
  END IF;
END $$;

COMMIT;
