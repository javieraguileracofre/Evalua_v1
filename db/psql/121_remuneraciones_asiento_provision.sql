-- 121_remuneraciones_asiento_provision.sql
-- Asiento de provisión / devengo de nómina (idempotente: solo columna).

BEGIN;

ALTER TABLE public.periodos_remuneracion ADD COLUMN IF NOT EXISTS asiento_provision_id BIGINT;

COMMIT;
