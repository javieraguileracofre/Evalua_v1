-- 119_remuneraciones_horas_periodo.sql
-- Entrada mensual de horas para calculo automatico de horas extras/nocturnas (idempotente).

BEGIN;

CREATE TABLE IF NOT EXISTS public.remuneracion_horas_periodo (
  id BIGSERIAL PRIMARY KEY,
  periodo_remuneracion_id BIGINT NOT NULL,
  empleado_id BIGINT NOT NULL,
  horas_ordinarias NUMERIC(12,2) NOT NULL DEFAULT 0,
  horas_extras NUMERIC(12,2) NOT NULL DEFAULT 0,
  horas_nocturnas NUMERIC(12,2) NOT NULL DEFAULT 0,
  es_ajuste_manual BOOLEAN NOT NULL DEFAULT FALSE,
  motivo_ajuste TEXT,
  usuario_ajuste_id BIGINT,
  updated_at TIMESTAMP WITHOUT TIME ZONE NOT NULL DEFAULT NOW()
);

CREATE UNIQUE INDEX IF NOT EXISTS uq_rem_horas_periodo_empleado
  ON public.remuneracion_horas_periodo (periodo_remuneracion_id, empleado_id);
CREATE INDEX IF NOT EXISTS ix_rem_horas_periodo_periodo
  ON public.remuneracion_horas_periodo (periodo_remuneracion_id);

DO $$
BEGIN
  IF to_regclass('public.periodos_remuneracion') IS NOT NULL THEN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'fk_rem_horas_periodo') THEN
      ALTER TABLE public.remuneracion_horas_periodo
        ADD CONSTRAINT fk_rem_horas_periodo
        FOREIGN KEY (periodo_remuneracion_id) REFERENCES public.periodos_remuneracion(id) ON DELETE CASCADE;
    END IF;
  END IF;
  IF to_regclass('public.empleados') IS NOT NULL THEN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'fk_rem_horas_empleado') THEN
      ALTER TABLE public.remuneracion_horas_periodo
        ADD CONSTRAINT fk_rem_horas_empleado
        FOREIGN KEY (empleado_id) REFERENCES public.empleados(id) ON DELETE RESTRICT;
    END IF;
  END IF;
  IF to_regclass('public.auth_usuarios') IS NOT NULL THEN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'fk_rem_horas_usuario_ajuste') THEN
      ALTER TABLE public.remuneracion_horas_periodo
        ADD CONSTRAINT fk_rem_horas_usuario_ajuste
        FOREIGN KEY (usuario_ajuste_id) REFERENCES public.auth_usuarios(id) ON DELETE SET NULL;
    END IF;
  END IF;
END $$;

COMMIT;
