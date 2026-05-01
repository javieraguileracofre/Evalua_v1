-- 120_remuneraciones_auditoria.sql
-- Trazabilidad de acciones en nómina (ajustes manuales, recálculos referenciados desde app).
-- Idempotente.

BEGIN;

CREATE TABLE IF NOT EXISTS public.remuneracion_audit_log (
  id BIGSERIAL PRIMARY KEY,
  periodo_remuneracion_id BIGINT NOT NULL,
  empleado_id BIGINT,
  actor_usuario_id BIGINT,
  accion VARCHAR(80) NOT NULL,
  detalle TEXT,
  created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS ix_rem_audit_periodo ON public.remuneracion_audit_log (periodo_remuneracion_id);
CREATE INDEX IF NOT EXISTS ix_rem_audit_created ON public.remuneracion_audit_log (created_at DESC);

DO $$
BEGIN
  IF to_regclass('public.periodos_remuneracion') IS NOT NULL THEN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'fk_rem_audit_periodo') THEN
      ALTER TABLE public.remuneracion_audit_log
        ADD CONSTRAINT fk_rem_audit_periodo
        FOREIGN KEY (periodo_remuneracion_id) REFERENCES public.periodos_remuneracion(id) ON DELETE CASCADE;
    END IF;
  END IF;
  IF to_regclass('public.empleados') IS NOT NULL THEN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'fk_rem_audit_empleado') THEN
      ALTER TABLE public.remuneracion_audit_log
        ADD CONSTRAINT fk_rem_audit_empleado
        FOREIGN KEY (empleado_id) REFERENCES public.empleados(id) ON DELETE SET NULL;
    END IF;
  END IF;
  IF to_regclass('public.auth_usuarios') IS NOT NULL THEN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'fk_rem_audit_actor') THEN
      ALTER TABLE public.remuneracion_audit_log
        ADD CONSTRAINT fk_rem_audit_actor
        FOREIGN KEY (actor_usuario_id) REFERENCES public.auth_usuarios(id) ON DELETE SET NULL;
    END IF;
  END IF;
END $$;

COMMIT;
