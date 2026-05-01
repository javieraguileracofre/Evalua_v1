-- 116_remuneraciones_vinculos_y_asiento.sql
-- Vínculo trabajador ↔ usuario portal y asiento de pago de nómina (idempotente).
-- Nota: el bootstrap completo de tablas está en 117_remuneraciones_bootstrap.sql (aplicado en arranque vía ensure_remuneraciones_bootstrap).

BEGIN;

DO $$
BEGIN
  IF to_regclass('public.empleados') IS NULL THEN
    RAISE NOTICE '116_remuneraciones_vinculos: public.empleados no existe; omitido (aplique 115_empleados_bootstrap.sql).';
    RETURN;
  END IF;

  ALTER TABLE public.empleados ADD COLUMN IF NOT EXISTS auth_usuario_id BIGINT;

  IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'fk_empleados_auth_usuario') THEN
    IF to_regclass('public.auth_usuarios') IS NOT NULL THEN
      ALTER TABLE public.empleados
        ADD CONSTRAINT fk_empleados_auth_usuario
        FOREIGN KEY (auth_usuario_id) REFERENCES public.auth_usuarios(id) ON DELETE SET NULL;
    END IF;
  END IF;

  EXECUTE 'CREATE INDEX IF NOT EXISTS ix_empleados_auth_usuario_id ON public.empleados(auth_usuario_id)';
  EXECUTE 'CREATE UNIQUE INDEX IF NOT EXISTS uq_empleados_auth_usuario_id ON public.empleados(auth_usuario_id) WHERE auth_usuario_id IS NOT NULL';
END $$;

ALTER TABLE public.periodos_remuneracion ADD COLUMN IF NOT EXISTS asiento_pago_id BIGINT;

COMMIT;
