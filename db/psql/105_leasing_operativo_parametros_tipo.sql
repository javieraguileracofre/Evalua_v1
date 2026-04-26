-- db/psql/105_leasing_operativo_parametros_tipo.sql
-- Parámetros comerciales por tipo de activo (defaults simulador).

BEGIN;

CREATE TABLE IF NOT EXISTS public.leasing_op_param_tipo (
    id                  BIGSERIAL PRIMARY KEY,
    tipo_activo_id      BIGINT NOT NULL UNIQUE REFERENCES public.leasing_op_tipo_activo(id) ON DELETE CASCADE,
    moneda              VARCHAR(8) NOT NULL DEFAULT 'CLP',
    iva_pct             NUMERIC(7,4) NOT NULL DEFAULT 19,
    plazo_default       INTEGER NOT NULL DEFAULT 36,
    spread_default_pct  NUMERIC(9,6) NOT NULL DEFAULT 8,
    margen_default_pct  NUMERIC(9,6) NOT NULL DEFAULT 12,
    tir_default_pct     NUMERIC(9,6) NOT NULL DEFAULT 14,
    perfil_json         JSONB NOT NULL DEFAULT '{}'::jsonb,
    actualizado_en      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS ix_lo_param_tipo_tipo ON public.leasing_op_param_tipo (tipo_activo_id);

INSERT INTO public.leasing_op_param_tipo (
    tipo_activo_id, moneda, iva_pct, plazo_default, spread_default_pct, margen_default_pct, tir_default_pct, perfil_json
)
SELECT
    t.id,
    'CLP',
    19,
    36,
    8,
    12,
    14,
    jsonb_build_object(
        'uso', jsonb_build_object('km_anual', 80000, 'horas_anual', 0),
        'activo', jsonb_build_object('marca_modelo_factor', 1, 'sector_economico_mult', 1, 'inflacion_activo_pct_anual', 3, 'condicion_factor', 1),
        'collateral', jsonb_build_object(
            'descuento_venta_forzada_pct', 12,
            'meses_liquidacion', 4,
            'tasa_fin_liquidacion_mensual', 0.008,
            'costo_repossession', 0,
            'costo_legal', 0,
            'transporte', 0,
            'reacondicionamiento', 0
        ),
        'riesgo', jsonb_build_object(
            'segmento_cliente', 'MEDIO',
            'sector_mult', 1,
            'activo_mult', 1,
            'uso_intensivo_mult', 1,
            'liquidez_mult', 1
        ),
        'comercial', jsonb_build_object(
            'comision_vendedor', 0,
            'comision_canal', 0,
            'costo_adquisicion', 0,
            'evaluacion', 0,
            'legal', 0,
            'onboarding', 0
        )
    )
FROM public.leasing_op_tipo_activo t
ON CONFLICT (tipo_activo_id) DO NOTHING;

COMMIT;
