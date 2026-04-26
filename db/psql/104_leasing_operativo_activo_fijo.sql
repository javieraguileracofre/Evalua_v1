-- db/psql/104_leasing_operativo_activo_fijo.sql
-- Activos fijos para leasing operativo y depreciación mensual.

BEGIN;

CREATE TABLE IF NOT EXISTS public.leasing_op_activo_fijo (
    id                          BIGSERIAL PRIMARY KEY,
    codigo                      VARCHAR(48) NOT NULL UNIQUE,
    tipo_activo_id              BIGINT NULL REFERENCES public.leasing_op_tipo_activo(id) ON DELETE SET NULL,
    marca                       VARCHAR(120) NOT NULL DEFAULT '',
    modelo                      VARCHAR(120) NOT NULL DEFAULT '',
    anio                        INTEGER NOT NULL,
    vin_serie                   VARCHAR(120) NULL,
    fecha_compra                DATE NOT NULL DEFAULT CURRENT_DATE,
    costo_compra                NUMERIC(18,4) NOT NULL,
    valor_residual_esperado     NUMERIC(18,4) NOT NULL DEFAULT 0,
    vida_util_meses_sii         INTEGER NOT NULL DEFAULT 60,
    depreciacion_mensual_sii    NUMERIC(18,4) NOT NULL DEFAULT 0,
    valor_libro                 NUMERIC(18,4) NOT NULL,
    estado                      VARCHAR(24) NOT NULL DEFAULT 'DISPONIBLE',
    creado_en                   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT chk_lo_af_estado CHECK (estado IN ('DISPONIBLE', 'ARRENDADO', 'MANTENCION', 'BAJA'))
);

CREATE INDEX IF NOT EXISTS ix_lo_af_tipo ON public.leasing_op_activo_fijo (tipo_activo_id);
CREATE INDEX IF NOT EXISTS ix_lo_af_estado ON public.leasing_op_activo_fijo (estado);

CREATE TABLE IF NOT EXISTS public.leasing_op_activo_depreciacion (
    id                          BIGSERIAL PRIMARY KEY,
    activo_id                   BIGINT NOT NULL REFERENCES public.leasing_op_activo_fijo(id) ON DELETE CASCADE,
    periodo_yyyymm              VARCHAR(6) NOT NULL,
    depreciacion_mes            NUMERIC(18,4) NOT NULL,
    valor_libro_cierre          NUMERIC(18,4) NOT NULL,
    asiento_ref                 VARCHAR(80) NULL,
    creado_en                   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE(activo_id, periodo_yyyymm)
);

CREATE INDEX IF NOT EXISTS ix_lo_af_dep_activo ON public.leasing_op_activo_depreciacion (activo_id, periodo_yyyymm DESC);

COMMIT;
