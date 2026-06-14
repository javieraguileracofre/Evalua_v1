-- db/psql/108_leasing_operativo_mejoras.sql
-- Mejoras LOP: indexación renta, vínculo activo-contrato, estado cuota FACTURADA, renovaciones.
-- Idempotente. Requiere tablas 102-104.

BEGIN;

-- Contrato: moneda e indexación de renta
ALTER TABLE public.leasing_op_contrato
    ADD COLUMN IF NOT EXISTS moneda VARCHAR(8) NOT NULL DEFAULT 'CLP',
    ADD COLUMN IF NOT EXISTS indexacion_tipo VARCHAR(12) NOT NULL DEFAULT 'NINGUNA',
    ADD COLUMN IF NOT EXISTS indexacion_pct NUMERIC(9, 6) NOT NULL DEFAULT 0,
    ADD COLUMN IF NOT EXISTS contrato_origen_id BIGINT NULL REFERENCES public.leasing_op_contrato(id) ON DELETE SET NULL;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'chk_lo_ctr_idx_tipo'
    ) THEN
        ALTER TABLE public.leasing_op_contrato
            ADD CONSTRAINT chk_lo_ctr_idx_tipo
            CHECK (indexacion_tipo IN ('NINGUNA', 'UF', 'IPC'));
    END IF;
END $$;

-- Cuota: monto base, referencia CxC, fecha facturación
ALTER TABLE public.leasing_op_cuota
    ADD COLUMN IF NOT EXISTS monto_renta_base NUMERIC(18, 4) NULL,
    ADD COLUMN IF NOT EXISTS cxc_id BIGINT NULL,
    ADD COLUMN IF NOT EXISTS facturado_en TIMESTAMPTZ NULL;

-- Ampliar estados de cuota (PENDIENTE, FACTURADA, PAGADA, MORA)
ALTER TABLE public.leasing_op_cuota DROP CONSTRAINT IF EXISTS chk_lo_cuo_est;
ALTER TABLE public.leasing_op_contrato DROP CONSTRAINT IF EXISTS chk_lo_ctr_est;

ALTER TABLE public.leasing_op_contrato
    ADD CONSTRAINT chk_lo_ctr_est CHECK (estado IN ('VIGENTE', 'CERRADO', 'LIQUIDADO', 'RENOVADO'));

ALTER TABLE public.leasing_op_cuota
    ADD CONSTRAINT chk_lo_cuo_est CHECK (estado IN ('PENDIENTE', 'FACTURADA', 'PAGADA', 'MORA'));

-- Activos vinculados a operación/contrato/cliente
ALTER TABLE public.leasing_op_activo_fijo
    ADD COLUMN IF NOT EXISTS simulacion_id BIGINT NULL REFERENCES public.leasing_op_simulacion(id) ON DELETE SET NULL,
    ADD COLUMN IF NOT EXISTS contrato_id BIGINT NULL REFERENCES public.leasing_op_contrato(id) ON DELETE SET NULL,
    ADD COLUMN IF NOT EXISTS cliente_id BIGINT NULL REFERENCES public.clientes(id) ON DELETE SET NULL;

CREATE INDEX IF NOT EXISTS ix_lo_af_sim ON public.leasing_op_activo_fijo (simulacion_id);
CREATE INDEX IF NOT EXISTS ix_lo_af_ctr ON public.leasing_op_activo_fijo (contrato_id);
CREATE INDEX IF NOT EXISTS ix_lo_af_cli ON public.leasing_op_activo_fijo (cliente_id);

-- Tabla de renovaciones / extensiones
CREATE TABLE IF NOT EXISTS public.leasing_op_renovacion (
    id                  BIGSERIAL PRIMARY KEY,
    contrato_origen_id  BIGINT NOT NULL REFERENCES public.leasing_op_contrato(id) ON DELETE RESTRICT,
    contrato_nuevo_id   BIGINT NULL REFERENCES public.leasing_op_contrato(id) ON DELETE SET NULL,
    simulacion_nueva_id BIGINT NULL REFERENCES public.leasing_op_simulacion(id) ON DELETE SET NULL,
    plazo_meses         INTEGER NOT NULL,
    renta_mensual       NUMERIC(18, 4) NOT NULL,
    indexacion_tipo     VARCHAR(12) NOT NULL DEFAULT 'NINGUNA',
    indexacion_pct      NUMERIC(9, 6) NOT NULL DEFAULT 0,
    motivo              TEXT NOT NULL DEFAULT '',
    usuario             VARCHAR(200) NOT NULL DEFAULT 'sistema',
    creado_en           TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT chk_lo_ren_idx CHECK (indexacion_tipo IN ('NINGUNA', 'UF', 'IPC'))
);

CREATE INDEX IF NOT EXISTS ix_lo_ren_origen ON public.leasing_op_renovacion (contrato_origen_id);

COMMIT;
