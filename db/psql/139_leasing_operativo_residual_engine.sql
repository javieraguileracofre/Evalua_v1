-- 139_leasing_operativo_residual_engine.sql
-- Motor profesional de valor residual / snapshots / curvas / overrides (idempotente).

CREATE TABLE IF NOT EXISTS public.leasing_op_residual_value_curve (
    id                  BIGSERIAL PRIMARY KEY,
    asset_type          VARCHAR(60) NOT NULL DEFAULT 'VEHICULO',
    brand               VARCHAR(80) NOT NULL DEFAULT '*',
    segment             VARCHAR(80) NOT NULL DEFAULT '*',
    age_month           INTEGER NOT NULL,
    residual_percentage NUMERIC(9, 4) NOT NULL,
    min_percentage      NUMERIC(9, 4) NOT NULL,
    max_percentage      NUMERIC(9, 4) NOT NULL,
    effective_from      DATE NULL,
    effective_to        DATE NULL,
    activo              BOOLEAN NOT NULL DEFAULT TRUE,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS ix_lo_rvc_lookup
    ON public.leasing_op_residual_value_curve (asset_type, brand, segment, age_month);

CREATE TABLE IF NOT EXISTS public.leasing_op_market_valuation_snapshot (
    id                  BIGSERIAL PRIMARY KEY,
    cotizacion_id       BIGINT NULL REFERENCES public.leasing_op_simulacion(id) ON DELETE SET NULL,
    unidad_id           VARCHAR(64) NOT NULL DEFAULT '',
    model_version       VARCHAR(32) NOT NULL DEFAULT 'RV-2026.10.01',
    fuente              VARCHAR(80) NOT NULL DEFAULT '',
    valor_actual        NUMERIC(18, 4) NOT NULL DEFAULT 0,
    valor_proyectado    NUMERIC(18, 4) NOT NULL DEFAULT 0,
    escenario           VARCHAR(24) NOT NULL DEFAULT 'BASE',
    payload_json        JSONB NOT NULL DEFAULT '{}'::jsonb,
    usuario             VARCHAR(200) NOT NULL DEFAULT 'sistema',
    creado_en           TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS ix_lo_mvs_cotizacion
    ON public.leasing_op_market_valuation_snapshot (cotizacion_id, creado_en DESC);

CREATE TABLE IF NOT EXISTS public.leasing_op_residual_override (
    id                  BIGSERIAL PRIMARY KEY,
    cotizacion_id       BIGINT NULL REFERENCES public.leasing_op_simulacion(id) ON DELETE SET NULL,
    unidad_id           VARCHAR(64) NOT NULL DEFAULT '',
    valor_anterior      NUMERIC(18, 4) NOT NULL DEFAULT 0,
    valor_nuevo         NUMERIC(18, 4) NOT NULL DEFAULT 0,
    motivo              VARCHAR(200) NOT NULL DEFAULT '',
    observacion         TEXT NOT NULL DEFAULT '',
    model_version       VARCHAR(32) NOT NULL DEFAULT '',
    usuario             VARCHAR(200) NOT NULL DEFAULT 'sistema',
    creado_en           TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS ix_lo_rov_cotizacion
    ON public.leasing_op_residual_override (cotizacion_id, creado_en DESC);

-- Política residual_value_v1 (pesos de mercado configurables; no hardcode en runtime)
INSERT INTO public.leasing_op_politica (clave, valor_json, descripcion)
VALUES (
    'residual_value_v1',
    '{
      "model_version": "RV-2026.10.01",
      "market_data_weights": {"chileautos": 0.50, "mercadolibre": 0.30, "yapo": 0.20, "autocosmos": 0.0},
      "uso_factores": {
        "USO_PARTICULAR": 1.00, "USO_EJECUTIVO": 0.98, "USO_COMERCIAL": 0.94,
        "USO_REPARTO": 0.90, "USO_LOGISTICO": 0.88, "USO_CONSTRUCCION": 0.84,
        "USO_MINERO": 0.80, "USO_TERRITORIO_EXTREMO": 0.78, "USO_INTENSIVO": 0.88,
        "URBANO": 1.00, "INTERURBANO": 0.96, "MIXTO": 0.94, "FAENA": 0.84, "MINERO": 0.80
      },
      "conservative_factor": 0.90,
      "base_factor": 1.00,
      "optimistic_factor": 1.08,
      "sale_cost_percentage": 2.0,
      "tipo_contrato_default": "ARRENDAMIENTO_OPERATIVO",
      "max_contract_months": 84,
      "max_km_month": 5000,
      "max_km_contract": 250000,
      "residual_min": 0.20,
      "residual_target": 0.45,
      "residual_max": 0.85,
      "deal_thresholds": {
        "minimum_irr": 10,
        "minimum_npv": 0,
        "minimum_margin": 5,
        "residual_min_pct": 25,
        "maximum_residual_risk": 70,
        "ltv_max_pct": 92
      }
    }'::jsonb,
    'Motor profesional valor residual / mercado / recupero / deal score'
)
ON CONFLICT (clave) DO NOTHING;

-- Semilla curva genérica VEHICULO
INSERT INTO public.leasing_op_residual_value_curve (
    asset_type, brand, segment, age_month, residual_percentage, min_percentage, max_percentage, effective_from
)
SELECT v.asset_type, v.brand, v.segment, v.age_month, v.residual_percentage, v.min_percentage, v.max_percentage, DATE '2026-01-01'
FROM (
    VALUES
        ('VEHICULO', '*', '*', 0, 100.0, 95.0, 100.0),
        ('VEHICULO', '*', '*', 12, 82.0, 76.0, 88.0),
        ('VEHICULO', '*', '*', 24, 72.0, 65.0, 78.0),
        ('VEHICULO', '*', '*', 36, 63.0, 55.0, 70.0),
        ('VEHICULO', '*', '*', 48, 55.0, 47.0, 62.0),
        ('VEHICULO', '*', '*', 60, 48.0, 40.0, 55.0),
        ('VEHICULO', '*', '*', 72, 42.0, 34.0, 50.0),
        ('VEHICULO', '*', '*', 84, 38.0, 30.0, 45.0),
        ('SUV', '*', 'SUV', 36, 66.0, 58.0, 73.0),
        ('PICKUP', '*', 'PICKUP', 36, 64.0, 56.0, 72.0),
        ('SEDAN', '*', 'SEDAN', 36, 58.0, 50.0, 65.0),
        ('FURGON', '*', 'FURGON', 36, 55.0, 47.0, 62.0)
) AS v(asset_type, brand, segment, age_month, residual_percentage, min_percentage, max_percentage)
WHERE NOT EXISTS (
    SELECT 1 FROM public.leasing_op_residual_value_curve c
    WHERE c.asset_type = v.asset_type
      AND c.brand = v.brand
      AND c.segment = v.segment
      AND c.age_month = v.age_month
);
