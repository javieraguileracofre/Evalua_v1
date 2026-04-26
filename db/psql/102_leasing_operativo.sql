-- db/psql/102_leasing_operativo.sql
-- Leasing operativo: motor económico CAPEX / residual / collateral / riesgo / pricing
-- Idempotente. Requiere public.clientes.

BEGIN;

CREATE TABLE IF NOT EXISTS public.leasing_op_tipo_activo (
    id                      BIGSERIAL PRIMARY KEY,
    codigo                  VARCHAR(40) NOT NULL UNIQUE,
    nombre                  VARCHAR(160) NOT NULL,
    residual_base_pct       NUMERIC(7, 4) NOT NULL DEFAULT 15,
    residual_max_pct        NUMERIC(7, 4) NOT NULL DEFAULT 45,
    sector                  VARCHAR(120) NULL,
    liquidez_factor         NUMERIC(9, 6) NOT NULL DEFAULT 1,
    obsolescencia_factor    NUMERIC(9, 6) NOT NULL DEFAULT 1,
    desgaste_km_factor      NUMERIC(12, 8) NOT NULL DEFAULT 0.0001,
    desgaste_hora_factor    NUMERIC(12, 8) NOT NULL DEFAULT 0.0005,
    haircut_residual_pct    NUMERIC(7, 4) NOT NULL DEFAULT 5,
    activo                  BOOLEAN NOT NULL DEFAULT TRUE,
    created_at              TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS public.leasing_op_politica (
    id              BIGSERIAL PRIMARY KEY,
    clave           VARCHAR(100) NOT NULL UNIQUE,
    valor_json      JSONB NOT NULL,
    descripcion     TEXT NULL,
    activo          BOOLEAN NOT NULL DEFAULT TRUE,
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS public.leasing_op_costo_plantilla (
    id                      BIGSERIAL PRIMARY KEY,
    tipo_activo_id          BIGINT NOT NULL REFERENCES public.leasing_op_tipo_activo(id) ON DELETE CASCADE,
    codigo                  VARCHAR(60) NOT NULL,
    descripcion             VARCHAR(200) NOT NULL,
    periodicidad            VARCHAR(20) NOT NULL DEFAULT 'MENSUAL',
    monto_mensual_equiv     NUMERIC(18, 4) NOT NULL DEFAULT 0,
    orden                   INTEGER NOT NULL DEFAULT 0,
    UNIQUE (tipo_activo_id, codigo),
    CONSTRAINT chk_lo_costo_period CHECK (periodicidad IN ('MENSUAL', 'ANUAL', 'INICIAL', 'FINAL', 'VAR_KM', 'VAR_HORA'))
);

CREATE TABLE IF NOT EXISTS public.leasing_op_simulacion (
    id                      BIGSERIAL PRIMARY KEY,
    codigo                  VARCHAR(48) NULL UNIQUE,
    cliente_id              BIGINT NULL REFERENCES public.clientes(id) ON DELETE SET NULL,
    tipo_activo_id          BIGINT NOT NULL REFERENCES public.leasing_op_tipo_activo(id),
    nombre                  VARCHAR(200) NOT NULL DEFAULT '',
    plazo_meses             INTEGER NOT NULL,
    escenario               VARCHAR(24) NOT NULL DEFAULT 'BASE',
    metodo_pricing          VARCHAR(24) NOT NULL DEFAULT 'COSTO_SPREAD',
    margen_pct              NUMERIC(9, 6) NULL,
    spread_pct              NUMERIC(9, 6) NULL,
    tir_objetivo_anual      NUMERIC(9, 6) NULL,
    inputs_json             JSONB NOT NULL DEFAULT '{}'::jsonb,
    result_json             JSONB NOT NULL DEFAULT '{}'::jsonb,
    decision_codigo         VARCHAR(20) NOT NULL DEFAULT 'PENDIENTE',
    decision_detalle        TEXT NOT NULL DEFAULT '',
    estado                  VARCHAR(24) NOT NULL DEFAULT 'BORRADOR',
    creado_en               TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    actualizado_en          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT chk_lo_sim_esc CHECK (escenario IN ('CONSERVADOR', 'BASE', 'OPTIMISTA', 'ESTRES')),
    CONSTRAINT chk_lo_sim_met CHECK (metodo_pricing IN ('COSTO_SPREAD', 'MARGEN_VENTA', 'TIR_OBJETIVO')),
    CONSTRAINT chk_lo_sim_dec CHECK (decision_codigo IN ('PENDIENTE', 'APROBAR', 'OBSERVAR', 'RECHAZAR')),
    CONSTRAINT chk_lo_sim_est CHECK (estado IN ('BORRADOR', 'COTIZADO', 'COMITE', 'APROBADO', 'RECHAZADO', 'CONTRATO'))
);

CREATE INDEX IF NOT EXISTS ix_lo_sim_cliente ON public.leasing_op_simulacion (cliente_id);
CREATE INDEX IF NOT EXISTS ix_lo_sim_tipo ON public.leasing_op_simulacion (tipo_activo_id);
CREATE INDEX IF NOT EXISTS ix_lo_sim_estado ON public.leasing_op_simulacion (estado);

CREATE TABLE IF NOT EXISTS public.leasing_op_comite (
    id                      BIGSERIAL PRIMARY KEY,
    simulacion_id           BIGINT NOT NULL REFERENCES public.leasing_op_simulacion(id) ON DELETE CASCADE,
    estado                  VARCHAR(20) NOT NULL DEFAULT 'PENDIENTE',
    resumen                 TEXT NOT NULL DEFAULT '',
    decision                VARCHAR(30) NULL,
    comentario              TEXT NOT NULL DEFAULT '',
    analista                VARCHAR(200) NOT NULL DEFAULT 'sistema',
    fecha_apertura          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    fecha_cierre            TIMESTAMPTZ NULL,
    CONSTRAINT chk_lo_comite_est CHECK (estado IN ('PENDIENTE', 'RESUELTO'))
);

CREATE INDEX IF NOT EXISTS ix_lo_comite_sim ON public.leasing_op_comite (simulacion_id);

CREATE TABLE IF NOT EXISTS public.leasing_op_historial (
    id                      BIGSERIAL PRIMARY KEY,
    simulacion_id           BIGINT NOT NULL REFERENCES public.leasing_op_simulacion(id) ON DELETE CASCADE,
    evento                  VARCHAR(80) NOT NULL,
    detalle_json            JSONB NULL,
    usuario                 VARCHAR(200) NOT NULL DEFAULT 'sistema',
    creado_en               TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS ix_lo_hist_sim ON public.leasing_op_historial (simulacion_id, creado_en DESC);

-- Seed tipos de activo
INSERT INTO public.leasing_op_tipo_activo (codigo, nombre, residual_base_pct, residual_max_pct, sector, liquidez_factor, obsolescencia_factor, desgaste_km_factor, desgaste_hora_factor, haircut_residual_pct)
VALUES
('VEHICULO_PESADO', 'Vehículo pesado / camión', 18, 42, 'TRANSPORTE', 0.95, 1.05, 0.00012, 0.00002, 6),
('MAQUINARIA', 'Maquinaria industrial', 15, 40, 'INDUSTRIA', 0.88, 1.08, 0.00005, 0.0006, 8),
('EQUIPO_IT', 'Equipos TI / oficina', 8, 25, 'TECNOLOGIA', 0.92, 1.15, 0, 0.0001, 10),
('CAMIONETA', 'Camioneta liviana', 22, 48, 'TRANSPORTE', 1.02, 1.02, 0.00015, 0.00003, 5)
ON CONFLICT DO NOTHING;

INSERT INTO public.leasing_op_politica (clave, valor_json, descripcion)
VALUES
(
    'escenarios_v1',
    '{
      "CONSERVADOR": {"residual_mult": 0.92, "costo_mult": 1.08, "riesgo_mult": 1.25, "tasa_fondo_mult": 1.12},
      "BASE": {"residual_mult": 1.0, "costo_mult": 1.0, "riesgo_mult": 1.0, "tasa_fondo_mult": 1.0},
      "OPTIMISTA": {"residual_mult": 1.06, "costo_mult": 0.95, "riesgo_mult": 0.88, "tasa_fondo_mult": 0.95},
      "ESTRES": {"residual_mult": 0.82, "costo_mult": 1.18, "riesgo_mult": 1.45, "tasa_fondo_mult": 1.28}
    }'::jsonb,
    'Multiplicadores por escenario.'
),
(
    'motor_decision_v1',
    '{
      "van_minimo": 0,
      "tir_minima_anual_pct": 10,
      "margen_op_minimo_pct": 5,
      "ltv_max_pct": 92
    }'::jsonb,
    'Umbrales motor de decisión.'
),
(
    'costo_fondo_v1',
    '{
      "costo_deuda_anual_pct": 7.5,
      "costo_capital_anual_pct": 12,
      "peso_deuda": 0.65,
      "peso_capital": 0.35,
      "spread_inversionista_anual_pct": 2.5
    }'::jsonb,
    'WACC simplificado → tasa mensual efectiva.'
),
(
    'riesgo_base_v1',
    '{
      "LGD_base": 0.45,
      "EAD_pct_capex": 1.0,
      "PD_BAJO": 0.012,
      "PD_MEDIO": 0.035,
      "PD_ALTO": 0.09,
      "PD_CRITICO": 0.18
    }'::jsonb,
    'Parámetros riesgo crediticio leasing operativo.'
)
ON CONFLICT DO NOTHING;

-- Plantillas de costo operativo (mensual equivalente); se pueden ampliar por SQL
INSERT INTO public.leasing_op_costo_plantilla (tipo_activo_id, codigo, descripcion, periodicidad, monto_mensual_equiv, orden)
SELECT t.id, v.codigo, v.descr, v.per, v.monto::numeric, v.ord
FROM public.leasing_op_tipo_activo t
CROSS JOIN (VALUES
  ('VEHICULO_PESADO', 'SEGURO', 'Seguro todo riesgo', 'MENSUAL', 450000, 10),
  ('VEHICULO_PESADO', 'MANT_PREV', 'Mantención preventiva', 'MENSUAL', 280000, 20),
  ('VEHICULO_PESADO', 'MANT_CORR', 'Mantención correctiva esperada', 'ANUAL', 1800000, 30),
  ('VEHICULO_PESADO', 'ADMIN_FLOTA', 'Administración flota', 'MENSUAL', 120000, 40),
  ('VEHICULO_PESADO', 'COBRANZA', 'Cobranza / gestión', 'MENSUAL', 80000, 50),
  ('MAQUINARIA', 'SEGURO', 'Seguro maquinaria', 'MENSUAL', 380000, 10),
  ('MAQUINARIA', 'MANT_PREV', 'Mantención preventiva', 'MENSUAL', 520000, 20),
  ('MAQUINARIA', 'ENERGIA', 'Energía / consumibles', 'MENSUAL', 200000, 25),
  ('EQUIPO_IT', 'SEGURO', 'Seguro electrónico', 'MENSUAL', 45000, 10),
  ('EQUIPO_IT', 'SOPORTE', 'Soporte / licencias', 'MENSUAL', 90000, 20),
  ('CAMIONETA', 'SEGURO', 'Seguro', 'MENSUAL', 220000, 10),
  ('CAMIONETA', 'MANT_PREV', 'Mantención', 'MENSUAL', 150000, 20)
) AS v(codigo_tipo, codigo, descr, per, monto, ord)
WHERE t.codigo = v.codigo_tipo
ON CONFLICT DO NOTHING;

CREATE OR REPLACE FUNCTION public.trg_lo_sim_set_updated()
RETURNS trigger AS $$
BEGIN
    NEW.actualizado_en := NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_lo_sim_updated ON public.leasing_op_simulacion;
CREATE TRIGGER trg_lo_sim_updated
    BEFORE UPDATE ON public.leasing_op_simulacion
    FOR EACH ROW
    EXECUTE FUNCTION public.trg_lo_sim_set_updated();

COMMIT;
