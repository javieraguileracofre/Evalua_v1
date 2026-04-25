-- db/psql/103_leasing_operativo_contrato_cuota.sql
-- Contrato operativo + cuotas de renta (cartera). Idempotente. Requiere leasing_op_simulacion.

BEGIN;

CREATE TABLE IF NOT EXISTS public.leasing_op_contrato (
    id                      BIGSERIAL PRIMARY KEY,
    simulacion_id           BIGINT NOT NULL REFERENCES public.leasing_op_simulacion(id) ON DELETE RESTRICT,
    codigo                  VARCHAR(48) NOT NULL UNIQUE,
    plazo_meses             INTEGER NOT NULL,
    renta_mensual           NUMERIC(18, 4) NOT NULL,
    fecha_inicio            DATE NOT NULL DEFAULT (CURRENT_DATE),
    estado                  VARCHAR(24) NOT NULL DEFAULT 'VIGENTE',
    creado_en               TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (simulacion_id),
    CONSTRAINT chk_lo_ctr_est CHECK (estado IN ('VIGENTE', 'CERRADO', 'LIQUIDADO'))
);

CREATE INDEX IF NOT EXISTS ix_lo_ctr_sim ON public.leasing_op_contrato (simulacion_id);
CREATE INDEX IF NOT EXISTS ix_lo_ctr_est ON public.leasing_op_contrato (estado);

CREATE TABLE IF NOT EXISTS public.leasing_op_cuota (
    id                      BIGSERIAL PRIMARY KEY,
    contrato_id             BIGINT NOT NULL REFERENCES public.leasing_op_contrato(id) ON DELETE CASCADE,
    nro                     INTEGER NOT NULL,
    fecha_vencimiento       DATE NOT NULL,
    monto_renta             NUMERIC(18, 4) NOT NULL,
    estado                  VARCHAR(20) NOT NULL DEFAULT 'PENDIENTE',
    UNIQUE (contrato_id, nro),
    CONSTRAINT chk_lo_cuo_est CHECK (estado IN ('PENDIENTE', 'PAGADA', 'MORA'))
);

CREATE INDEX IF NOT EXISTS ix_lo_cuo_ctr ON public.leasing_op_cuota (contrato_id);
CREATE INDEX IF NOT EXISTS ix_lo_cuo_vcto ON public.leasing_op_cuota (fecha_vencimiento);

COMMIT;
