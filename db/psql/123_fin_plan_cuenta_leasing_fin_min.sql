-- 123_fin_plan_cuenta_leasing_fin_min.sql
-- Cuentas mínimas para workflow leasing financiero (activación contable).
-- Requeridas en crud/comercial/leasing_fin.py: 113701, 210701, 210702, 410701, 110201.
-- Idempotente; apto para Supabase / producción.

INSERT INTO fin.plan_cuenta (
    codigo, nombre, nivel, cuenta_padre_id, tipo, clasificacion, naturaleza,
    acepta_movimiento, requiere_centro_costo, estado, descripcion
) VALUES
('110000', 'ACTIVO CORRIENTE', 2, NULL, 'ACTIVO', 'ACTIVO_CORRIENTE', 'DEUDORA', FALSE, FALSE, 'ACTIVO', 'Agrupador activos corrientes'),
('110201', 'CAJA Y BANCOS', 3, NULL, 'ACTIVO', 'ACTIVO_CORRIENTE', 'DEUDORA', TRUE, FALSE, 'ACTIVO', 'Fondos disponibles'),
('210000', 'PASIVOS CORRIENTES', 2, NULL, 'PASIVO', 'PASIVO_CORRIENTE', 'ACREEDORA', FALSE, FALSE, 'ACTIVO', 'Agrupador pasivos corrientes'),
('410000', 'INGRESOS OPERACIONALES', 2, NULL, 'INGRESO', 'INGRESO_OPERACIONAL', 'ACREEDORA', FALSE, FALSE, 'ACTIVO', 'Agrupador ingresos operacionales'),
('113701', 'CUENTAS POR COBRAR LEASING FINANCIERO', 3, NULL, 'ACTIVO', 'ACTIVO_CORRIENTE', 'DEUDORA', TRUE, FALSE, 'ACTIVO', 'Principal leasing financiero'),
('210701', 'OBLIGACIONES LEASING FINANCIERO', 3, NULL, 'PASIVO', 'PASIVO_CORRIENTE', 'ACREEDORA', TRUE, FALSE, 'ACTIVO', 'Pasivo leasing financiero'),
('210702', 'INTERESES DIFERIDOS LEASING FINANCIERO', 3, NULL, 'PASIVO', 'PASIVO_CORRIENTE', 'ACREEDORA', TRUE, FALSE, 'ACTIVO', 'Intereses financieros por devengar de leasing financiero'),
('410701', 'INGRESOS FINANCIEROS LEASING', 3, NULL, 'INGRESO', 'INGRESO_OPERACIONAL', 'ACREEDORA', TRUE, FALSE, 'ACTIVO', 'Intereses leasing financiero')
ON CONFLICT (codigo) DO UPDATE SET
    nombre = EXCLUDED.nombre,
    nivel = EXCLUDED.nivel,
    tipo = EXCLUDED.tipo,
    clasificacion = EXCLUDED.clasificacion,
    naturaleza = EXCLUDED.naturaleza,
    acepta_movimiento = EXCLUDED.acepta_movimiento,
    requiere_centro_costo = EXCLUDED.requiere_centro_costo,
    estado = EXCLUDED.estado,
    descripcion = EXCLUDED.descripcion;

UPDATE fin.plan_cuenta h
   SET cuenta_padre_id = p.id
  FROM fin.plan_cuenta p
 WHERE h.codigo = '110201'
   AND p.codigo = '110000';

UPDATE fin.plan_cuenta h
   SET cuenta_padre_id = p.id
  FROM fin.plan_cuenta p
 WHERE h.codigo = '113701'
   AND p.codigo = '110000';

UPDATE fin.plan_cuenta h
   SET cuenta_padre_id = p.id
  FROM fin.plan_cuenta p
 WHERE h.codigo = '210701'
   AND p.codigo = '210000';

UPDATE fin.plan_cuenta h
   SET cuenta_padre_id = p.id
  FROM fin.plan_cuenta p
 WHERE h.codigo = '210702'
   AND p.codigo = '210000';

UPDATE fin.plan_cuenta h
   SET cuenta_padre_id = p.id
  FROM fin.plan_cuenta p
 WHERE h.codigo = '410701'
   AND p.codigo = '410000';
