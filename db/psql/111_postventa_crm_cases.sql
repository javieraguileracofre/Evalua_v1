-- 111_postventa_crm_cases.sql
-- Evolución idempotente de Postventa hacia CRM de casos.

BEGIN;

ALTER TABLE public.postventa_solicitudes ADD COLUMN IF NOT EXISTS numero_caso VARCHAR(24);
ALTER TABLE public.postventa_solicitudes ADD COLUMN IF NOT EXISTS asignado_a_id BIGINT;
ALTER TABLE public.postventa_solicitudes ADD COLUMN IF NOT EXISTS creado_por_id BIGINT;
ALTER TABLE public.postventa_solicitudes ADD COLUMN IF NOT EXISTS origen VARCHAR(20);
ALTER TABLE public.postventa_solicitudes ADD COLUMN IF NOT EXISTS fecha_primer_respuesta TIMESTAMP NULL;
ALTER TABLE public.postventa_solicitudes ADD COLUMN IF NOT EXISTS fecha_vencimiento_sla TIMESTAMP NULL;
ALTER TABLE public.postventa_solicitudes ADD COLUMN IF NOT EXISTS fecha_resolucion TIMESTAMP NULL;
ALTER TABLE public.postventa_solicitudes ADD COLUMN IF NOT EXISTS sla_estado VARCHAR(20);
ALTER TABLE public.postventa_solicitudes ADD COLUMN IF NOT EXISTS ultimo_movimiento_at TIMESTAMP NULL;

DO $$
BEGIN
  IF NOT EXISTS (
      SELECT 1
      FROM information_schema.table_constraints
      WHERE table_schema = 'public'
        AND table_name = 'postventa_solicitudes'
        AND constraint_name = 'fk_postventa_solicitudes_asignado_a_id_auth_usuarios'
  ) THEN
    ALTER TABLE public.postventa_solicitudes
      ADD CONSTRAINT fk_postventa_solicitudes_asignado_a_id_auth_usuarios
      FOREIGN KEY (asignado_a_id) REFERENCES public.auth_usuarios(id) ON DELETE SET NULL;
  END IF;

  IF NOT EXISTS (
      SELECT 1
      FROM information_schema.table_constraints
      WHERE table_schema = 'public'
        AND table_name = 'postventa_solicitudes'
        AND constraint_name = 'fk_postventa_solicitudes_creado_por_id_auth_usuarios'
  ) THEN
    ALTER TABLE public.postventa_solicitudes
      ADD CONSTRAINT fk_postventa_solicitudes_creado_por_id_auth_usuarios
      FOREIGN KEY (creado_por_id) REFERENCES public.auth_usuarios(id) ON DELETE SET NULL;
  END IF;
END $$;

ALTER TABLE public.email_log
  ADD COLUMN IF NOT EXISTS caso_id BIGINT NULL REFERENCES public.postventa_solicitudes(id);

CREATE TABLE IF NOT EXISTS public.postventa_caso_eventos (
  id BIGSERIAL PRIMARY KEY,
  caso_id BIGINT NOT NULL REFERENCES public.postventa_solicitudes(id) ON DELETE CASCADE,
  cliente_id BIGINT NOT NULL REFERENCES public.clientes(id) ON DELETE RESTRICT,
  usuario_id BIGINT NULL REFERENCES public.auth_usuarios(id) ON DELETE SET NULL,
  tipo VARCHAR(30) NOT NULL DEFAULT 'COMENTARIO',
  visibilidad VARCHAR(20) NOT NULL DEFAULT 'INTERNA',
  contenido TEXT NOT NULL DEFAULT '',
  metadata_json TEXT NULL,
  created_at TIMESTAMP NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS ix_pv_sol_cliente_estado ON public.postventa_solicitudes (cliente_id, estado);
CREATE INDEX IF NOT EXISTS ix_pv_sol_fecha ON public.postventa_solicitudes (fecha_apertura);
CREATE INDEX IF NOT EXISTS ix_pv_sol_asignado ON public.postventa_solicitudes (asignado_a_id);
CREATE INDEX IF NOT EXISTS ix_pv_sol_ultimo_mov ON public.postventa_solicitudes (ultimo_movimiento_at);
CREATE INDEX IF NOT EXISTS ix_pv_sol_numero_caso ON public.postventa_solicitudes (numero_caso);
CREATE UNIQUE INDEX IF NOT EXISTS uq_pv_sol_numero_caso ON public.postventa_solicitudes (numero_caso);

CREATE INDEX IF NOT EXISTS ix_pv_evt_caso_created ON public.postventa_caso_eventos (caso_id, created_at);
CREATE INDEX IF NOT EXISTS ix_pv_evt_cliente_created ON public.postventa_caso_eventos (cliente_id, created_at);
CREATE INDEX IF NOT EXISTS ix_pv_evt_tipo ON public.postventa_caso_eventos (tipo);

UPDATE public.postventa_solicitudes
SET numero_caso = 'PV-' || EXTRACT(YEAR FROM COALESCE(fecha_apertura, now()))::text || '-' || LPAD(id::text, 6, '0')
WHERE numero_caso IS NULL OR btrim(numero_caso) = '';

UPDATE public.postventa_solicitudes
SET origen = 'INTERNO'
WHERE origen IS NULL OR btrim(origen) = '';

UPDATE public.postventa_solicitudes
SET sla_estado = 'OK'
WHERE sla_estado IS NULL OR btrim(sla_estado) = '';

UPDATE public.postventa_solicitudes
SET ultimo_movimiento_at = COALESCE(ultimo_movimiento_at, fecha_actualizacion, fecha_apertura, now())
WHERE ultimo_movimiento_at IS NULL;

-- Soporte de estados legacy + CRM en check constraint.
DO $$
DECLARE
  rec RECORD;
BEGIN
  FOR rec IN
    SELECT c.conname
    FROM pg_constraint c
    JOIN pg_class t ON t.oid = c.conrelid
    JOIN pg_namespace n ON n.oid = t.relnamespace
    WHERE n.nspname = 'public'
      AND t.relname = 'postventa_solicitudes'
      AND c.contype = 'c'
      AND pg_get_constraintdef(c.oid) ILIKE '%estado%'
  LOOP
    EXECUTE format('ALTER TABLE public.postventa_solicitudes DROP CONSTRAINT IF EXISTS %I', rec.conname);
  END LOOP;
END $$;

ALTER TABLE public.postventa_solicitudes
  ADD CONSTRAINT ck_postventa_solicitudes_estado_crm
  CHECK (
    estado IN (
      'ABIERTA', 'EN_PROCESO', 'ESPERA_CLIENTE', 'RESUELTA', 'DESCARTADA',
      'NUEVO', 'ABIERTO', 'EN_GESTION', 'ESPERANDO_CLIENTE', 'CERRADO'
    )
  );

COMMIT;
