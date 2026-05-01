-- 122_empleados_transferencia_bancaria.sql
-- Datos opcionales para archivos de transferencia masiva (idempotente).
-- Si public.empleados no existe, no falla: ejecute antes 115_empleados_bootstrap.sql
-- o deje que la app corra con create_all / arranque con ensure_empleados_bootstrap.

BEGIN;

DO $$
BEGIN
  IF to_regclass('public.empleados') IS NOT NULL THEN
    EXECUTE 'ALTER TABLE public.empleados ADD COLUMN IF NOT EXISTS transferencia_banco_codigo VARCHAR(12)';
    EXECUTE 'ALTER TABLE public.empleados ADD COLUMN IF NOT EXISTS transferencia_numero_cuenta VARCHAR(32)';
    EXECUTE 'ALTER TABLE public.empleados ADD COLUMN IF NOT EXISTS transferencia_tipo_cuenta VARCHAR(16)';
  ELSE
    RAISE NOTICE '122_empleados_transferencia_bancaria: public.empleados no existe; omitido. Aplique 115_empleados_bootstrap.sql antes.';
  END IF;
END $$;

COMMIT;
