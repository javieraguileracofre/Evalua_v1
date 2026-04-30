-- 116_remuneraciones_vinculos_y_asiento.sql
-- Vínculo trabajador ↔ usuario portal y asiento de pago de nómina (idempotente).

BEGIN;

ALTER TABLE public.empleados ADD COLUMN IF NOT EXISTS auth_usuario_id BIGINT;

DO $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'fk_empleados_auth_usuario') THEN
    IF to_regclass('public.auth_usuarios') IS NOT NULL THEN
      ALTER TABLE public.empleados
        ADD CONSTRAINT fk_empleados_auth_usuario
        FOREIGN KEY (auth_usuario_id) REFERENCES public.auth_usuarios(id) ON DELETE SET NULL;
    END IF;
  END IF;
END $$;

CREATE INDEX IF NOT EXISTS ix_empleados_auth_usuario_id ON public.empleados(auth_usuario_id);

-- Un mismo usuario portal solo puede enlazarse a un trabajador a la vez.
CREATE UNIQUE INDEX IF NOT EXISTS uq_empleados_auth_usuario_id
  ON public.empleados(auth_usuario_id)
  WHERE auth_usuario_id IS NOT NULL;

ALTER TABLE public.periodos_remuneracion ADD COLUMN IF NOT EXISTS asiento_pago_id BIGINT;

COMMIT;
