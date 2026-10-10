-- db/psql/138_leasing_operativo_tipos_flota.sql
-- Amplía catálogo LOP: vehículo liviano, gerencial, grúa, furgón (Partner y similares).
-- Idempotente.

BEGIN;

INSERT INTO public.leasing_op_tipo_activo (
    codigo, nombre, residual_base_pct, residual_max_pct, sector,
    liquidez_factor, obsolescencia_factor, desgaste_km_factor, desgaste_hora_factor, haircut_residual_pct
)
VALUES
(
    'VEHICULO_LIVIANO',
    'Vehículo liviano',
    20, 45, 'TRANSPORTE',
    1.04, 1.03, 0.00014, 0.00002, 5
),
(
    'VEHICULO_GERENCIAL',
    'Vehículos gerenciales',
    24, 52, 'TRANSPORTE',
    1.06, 1.04, 0.00011, 0.00002, 6
),
(
    'GRUA',
    'Grúas',
    14, 38, 'INDUSTRIA',
    0.82, 1.10, 0.00002, 0.00075, 10
),
(
    'FURGON',
    'Camioneta tipo furgón (Partner y similares)',
    18, 42, 'TRANSPORTE',
    1.00, 1.04, 0.00016, 0.00003, 6
)
ON CONFLICT (codigo) DO NOTHING;

-- Parámetros comerciales default (105) para tipos nuevos
INSERT INTO public.leasing_op_param_tipo (
    tipo_activo_id, moneda, iva_pct, plazo_default, spread_default_pct, margen_default_pct, tir_default_pct, perfil_json
)
SELECT
    t.id,
    'CLP',
    19,
    CASE t.codigo
        WHEN 'VEHICULO_GERENCIAL' THEN 36
        WHEN 'GRUA' THEN 36
        WHEN 'FURGON' THEN 36
        ELSE 36
    END,
    8,
    12,
    14,
    CASE t.codigo
        WHEN 'VEHICULO_LIVIANO' THEN jsonb_build_object(
            'uso', jsonb_build_object('km_anual', 25000, 'horas_anual', 0),
            'activo', jsonb_build_object('marca_modelo_factor', 1, 'sector_economico_mult', 1, 'inflacion_activo_pct_anual', 3, 'condicion_factor', 1),
            'collateral', jsonb_build_object('descuento_venta_forzada_pct', 12, 'meses_liquidacion', 3, 'tasa_fin_liquidacion_mensual', 0.008, 'costo_repossession', 0, 'costo_legal', 0, 'transporte', 0, 'reacondicionamiento', 0),
            'riesgo', jsonb_build_object('segmento_cliente', 'MEDIO', 'sector_mult', 1, 'activo_mult', 1, 'uso_intensivo_mult', 1, 'liquidez_mult', 1),
            'comercial', jsonb_build_object('comision_vendedor', 0, 'comision_canal', 0, 'costo_adquisicion', 0, 'evaluacion', 0, 'legal', 0, 'onboarding', 0)
        )
        WHEN 'VEHICULO_GERENCIAL' THEN jsonb_build_object(
            'uso', jsonb_build_object('km_anual', 18000, 'horas_anual', 0),
            'activo', jsonb_build_object('marca_modelo_factor', 1.05, 'sector_economico_mult', 1, 'inflacion_activo_pct_anual', 3, 'condicion_factor', 1),
            'collateral', jsonb_build_object('descuento_venta_forzada_pct', 14, 'meses_liquidacion', 3, 'tasa_fin_liquidacion_mensual', 0.008, 'costo_repossession', 0, 'costo_legal', 0, 'transporte', 0, 'reacondicionamiento', 0),
            'riesgo', jsonb_build_object('segmento_cliente', 'MEDIO', 'sector_mult', 1, 'activo_mult', 1, 'uso_intensivo_mult', 0.95, 'liquidez_mult', 0.95),
            'comercial', jsonb_build_object('comision_vendedor', 0, 'comision_canal', 0, 'costo_adquisicion', 0, 'evaluacion', 0, 'legal', 0, 'onboarding', 0)
        )
        WHEN 'GRUA' THEN jsonb_build_object(
            'uso', jsonb_build_object('km_anual', 0, 'horas_anual', 1600),
            'activo', jsonb_build_object('marca_modelo_factor', 1, 'sector_economico_mult', 1.05, 'inflacion_activo_pct_anual', 3, 'condicion_factor', 1),
            'collateral', jsonb_build_object('descuento_venta_forzada_pct', 18, 'meses_liquidacion', 6, 'tasa_fin_liquidacion_mensual', 0.01, 'costo_repossession', 0, 'costo_legal', 0, 'transporte', 0, 'reacondicionamiento', 0),
            'riesgo', jsonb_build_object('segmento_cliente', 'MEDIO', 'sector_mult', 1.1, 'activo_mult', 1.15, 'uso_intensivo_mult', 1.1, 'liquidez_mult', 1.2),
            'comercial', jsonb_build_object('comision_vendedor', 0, 'comision_canal', 0, 'costo_adquisicion', 0, 'evaluacion', 0, 'legal', 0, 'onboarding', 0)
        )
        WHEN 'FURGON' THEN jsonb_build_object(
            'uso', jsonb_build_object('km_anual', 45000, 'horas_anual', 0),
            'activo', jsonb_build_object('marca_modelo_factor', 1, 'sector_economico_mult', 1, 'inflacion_activo_pct_anual', 3, 'condicion_factor', 1),
            'collateral', jsonb_build_object('descuento_venta_forzada_pct', 13, 'meses_liquidacion', 4, 'tasa_fin_liquidacion_mensual', 0.008, 'costo_repossession', 0, 'costo_legal', 0, 'transporte', 0, 'reacondicionamiento', 0),
            'riesgo', jsonb_build_object('segmento_cliente', 'MEDIO', 'sector_mult', 1, 'activo_mult', 1, 'uso_intensivo_mult', 1.05, 'liquidez_mult', 1),
            'comercial', jsonb_build_object('comision_vendedor', 0, 'comision_canal', 0, 'costo_adquisicion', 0, 'evaluacion', 0, 'legal', 0, 'onboarding', 0)
        )
        ELSE '{}'::jsonb
    END
FROM public.leasing_op_tipo_activo t
WHERE t.codigo IN ('VEHICULO_LIVIANO', 'VEHICULO_GERENCIAL', 'GRUA', 'FURGON')
ON CONFLICT (tipo_activo_id) DO NOTHING;

-- Plantillas de costo operativo mínimas
INSERT INTO public.leasing_op_costo_plantilla (tipo_activo_id, codigo, descripcion, periodicidad, monto_mensual_equiv, orden)
SELECT t.id, v.codigo, v.descr, v.per, v.monto::numeric, v.ord
FROM public.leasing_op_tipo_activo t
CROSS JOIN (VALUES
  ('VEHICULO_LIVIANO', 'SEGURO', 'Seguro vehículo liviano', 'MENSUAL', 160000, 10),
  ('VEHICULO_LIVIANO', 'MANT_PREV', 'Mantención preventiva', 'MENSUAL', 90000, 20),
  ('VEHICULO_GERENCIAL', 'SEGURO', 'Seguro full gerencial', 'MENSUAL', 280000, 10),
  ('VEHICULO_GERENCIAL', 'MANT_PREV', 'Mantención / neumáticos', 'MENSUAL', 140000, 20),
  ('GRUA', 'SEGURO', 'Seguro grúa / responsabilidad', 'MENSUAL', 650000, 10),
  ('GRUA', 'MANT_PREV', 'Mantención preventiva horas', 'MENSUAL', 480000, 20),
  ('GRUA', 'CERTIF', 'Certificaciones / inspección', 'ANUAL', 1200000, 30),
  ('FURGON', 'SEGURO', 'Seguro furgón comercial', 'MENSUAL', 180000, 10),
  ('FURGON', 'MANT_PREV', 'Mantención flota last-mile', 'MENSUAL', 110000, 20)
) AS v(codigo_tipo, codigo, descr, per, monto, ord)
WHERE t.codigo = v.codigo_tipo
ON CONFLICT DO NOTHING;

COMMIT;
