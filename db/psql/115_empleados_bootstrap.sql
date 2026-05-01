-- 115_empleados_bootstrap.sql
-- Tabla public.empleados (trabajadores: fondos por rendir, transporte, nómina).
-- En bases provisionadas solo con SQL parcial (p. ej. Supabase) puede faltar; 113/117
-- referencian esta tabla pero no la crean. Idempotente.

BEGIN;

CREATE TABLE IF NOT EXISTS public.empleados (
  id BIGSERIAL PRIMARY KEY,
  rut VARCHAR(16) NOT NULL,
  nombre_completo VARCHAR(200) NOT NULL,
  cargo VARCHAR(120),
  email VARCHAR(120),
  telefono VARCHAR(32),
  activo BOOLEAN NOT NULL DEFAULT TRUE,
  created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMP WITHOUT TIME ZONE NOT NULL DEFAULT NOW()
);

CREATE UNIQUE INDEX IF NOT EXISTS uq_empleados_rut ON public.empleados (rut);
CREATE INDEX IF NOT EXISTS ix_empleados_rut ON public.empleados (rut);
CREATE INDEX IF NOT EXISTS ix_empleados_activo ON public.empleados (activo);

COMMIT;
