-- 122_empleados_transferencia_bancaria.sql
-- Datos opcionales para archivos de transferencia masiva (idempotente).

BEGIN;

ALTER TABLE public.empleados ADD COLUMN IF NOT EXISTS transferencia_banco_codigo VARCHAR(12);
ALTER TABLE public.empleados ADD COLUMN IF NOT EXISTS transferencia_numero_cuenta VARCHAR(32);
ALTER TABLE public.empleados ADD COLUMN IF NOT EXISTS transferencia_tipo_cuenta VARCHAR(16);

COMMIT;
