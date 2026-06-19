-- Supabase SQL Editor: ejecutar RUN (idempotente).
-- LOP Comercial v2: política de decisión ampliada + metadatos motor 2.0.
-- Requiere parches leasing operativo 102–109 ya aplicados.

BEGIN;

UPDATE public.leasing_op_politica
SET valor_json = valor_json || '{
  "spread_minimo_sobre_costo_pct": 3,
  "payback_max_meses": 48,
  "recovery_min_pct": 35
}'::jsonb,
    descripcion = 'Umbrales motor de decisión LOP v2 (VAN, TIR, margen, LTV, spread, payback, recovery).'
WHERE clave = 'motor_decision_v1';

INSERT INTO public.leasing_op_politica (clave, valor_json, descripcion)
VALUES (
    'lop_comercial_v2',
    '{"engine_version": "2.0", "indexacion_habilitada": true, "pie_opcion_habilitado": true, "sensibilidad_habilitada": true}'::jsonb,
    'Feature flag y metadatos LOP Comercial v2.'
)
ON CONFLICT (clave) DO UPDATE
SET valor_json = EXCLUDED.valor_json,
    descripcion = EXCLUDED.descripcion;

COMMIT;
