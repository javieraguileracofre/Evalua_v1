BEGIN;

-- Cuentas específicas de leasing operativo (idempotente).
INSERT INTO fin.plan_cuenta
(
    codigo,
    nombre,
    nivel,
    cuenta_padre_id,
    tipo,
    clasificacion,
    naturaleza,
    acepta_movimiento,
    requiere_centro_costo,
    estado,
    descripcion
)
VALUES
    ('113801', 'CUENTAS POR COBRAR LEASING OPERATIVO', 3, NULL, 'ACTIVO', 'ACTIVO_CORRIENTE', 'DEUDORA', TRUE, FALSE, 'ACTIVO', 'Cartera por cuotas de leasing operativo'),
    ('120801', 'ACTIVO LEASING OPERATIVO', 3, NULL, 'ACTIVO', 'ACTIVO_NO_CORRIENTE', 'DEUDORA', TRUE, FALSE, 'ACTIVO', 'Activos fijos asignados a contratos leasing operativo'),
    ('120899', 'DEPRECIACION ACUMULADA ACTIVO LEASING OPERATIVO', 3, NULL, 'ACTIVO', 'ACTIVO_NO_CORRIENTE', 'ACREEDORA', TRUE, FALSE, 'ACTIVO', 'Contra-cuenta de depreciación acumulada leasing operativo')
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
WHERE h.codigo = '113801'
  AND p.codigo = '110000';

UPDATE fin.plan_cuenta h
SET cuenta_padre_id = p.id
FROM fin.plan_cuenta p
WHERE h.codigo = '120801'
  AND p.codigo = '120000';

UPDATE fin.plan_cuenta h
SET cuenta_padre_id = p.id
FROM fin.plan_cuenta p
WHERE h.codigo = '120899'
  AND p.codigo = '120000';

-- Eventos contables base para Leasing Operativo (idempotente).
INSERT INTO fin.config_contable
(
    codigo_evento,
    nombre_evento,
    lado,
    codigo_cuenta,
    orden,
    requiere_centro_costo,
    requiere_documento,
    estado,
    descripcion
)
SELECT * FROM (
    VALUES
    ('LOP_ACTIVACION', 'Activacion contable leasing operativo', 'DEBE',  '120801', 1, FALSE, TRUE, 'ACTIVO', 'Alta activo fijo leasing operativo'),
    ('LOP_ACTIVACION', 'Activacion contable leasing operativo', 'HABER', '110401', 1, FALSE, TRUE, 'ACTIVO', 'Reclasificacion de activo arrendado'),
    ('LOP_FACTURACION', 'Facturacion mensual cuota leasing operativo', 'DEBE',  '113801', 1, FALSE, TRUE, 'ACTIVO', 'Cuenta por cobrar cliente cuota LOP'),
    ('LOP_FACTURACION', 'Facturacion mensual cuota leasing operativo', 'HABER', '410101', 1, TRUE,  TRUE, 'ACTIVO', 'Ingreso por renta leasing operativo'),
    ('LOP_FACTURACION', 'Facturacion mensual cuota leasing operativo', 'HABER', '210201', 2, FALSE, TRUE, 'ACTIVO', 'IVA debito fiscal cuota LOP'),
    ('LOP_DEPRECIACION', 'Depreciacion mensual activo leasing operativo', 'DEBE',  '610104', 1, TRUE,  TRUE, 'ACTIVO', 'Gasto depreciacion activo LOP'),
    ('LOP_DEPRECIACION', 'Depreciacion mensual activo leasing operativo', 'HABER', '120899', 1, FALSE, TRUE, 'ACTIVO', 'Depreciacion acumulada activo LOP')
) AS v(codigo_evento,nombre_evento,lado,codigo_cuenta,orden,requiere_centro_costo,requiere_documento,estado,descripcion)
ON CONFLICT ON CONSTRAINT uq_fin_config_contable_evento_lado_orden
DO UPDATE SET
    codigo_cuenta = EXCLUDED.codigo_cuenta,
    nombre_evento = EXCLUDED.nombre_evento,
    requiere_centro_costo = EXCLUDED.requiere_centro_costo,
    requiere_documento = EXCLUDED.requiere_documento,
    estado = EXCLUDED.estado,
    descripcion = EXCLUDED.descripcion;

INSERT INTO fin.config_contable_detalle_modulo
(
    modulo,
    submodulo,
    tipo_documento,
    codigo_evento,
    nombre_evento,
    lado,
    codigo_cuenta,
    orden,
    requiere_centro_costo,
    requiere_documento,
    requiere_cliente,
    requiere_proveedor,
    estado,
    descripcion
)
SELECT * FROM (
    VALUES
    ('LEASING_OP', 'ACTIVACION',  'CONTRATO',   'LOP_ACTIVACION',  'Activacion contable LOP', 'DEBE',  '120801', 1, FALSE, TRUE,  TRUE,  FALSE, 'ACTIVO', 'Alta activo fijo por activacion'),
    ('LEASING_OP', 'ACTIVACION',  'CONTRATO',   'LOP_ACTIVACION',  'Activacion contable LOP', 'HABER', '110401', 1, FALSE, TRUE,  TRUE,  FALSE, 'ACTIVO', 'Reclasificacion activo arrendado'),
    ('LEASING_OP', 'FACTURACION', 'CUOTA',      'LOP_FACTURACION', 'Facturacion cuota LOP',   'DEBE',  '113801', 1, FALSE, TRUE,  TRUE,  FALSE, 'ACTIVO', 'CxC cuota mensual'),
    ('LEASING_OP', 'FACTURACION', 'CUOTA',      'LOP_FACTURACION', 'Facturacion cuota LOP',   'HABER', '410101', 1, TRUE,  TRUE,  TRUE,  FALSE, 'ACTIVO', 'Ingreso por renta'),
    ('LEASING_OP', 'FACTURACION', 'CUOTA',      'LOP_FACTURACION', 'Facturacion cuota LOP',   'HABER', '210201', 2, FALSE, TRUE,  TRUE,  FALSE, 'ACTIVO', 'IVA debito'),
    ('LEASING_OP', 'DEPRECIACION','ACTIVO_FIJO','LOP_DEPRECIACION','Depreciacion activo LOP', 'DEBE',  '610104', 1, TRUE,  TRUE,  FALSE, FALSE, 'ACTIVO', 'Gasto depreciacion'),
    ('LEASING_OP', 'DEPRECIACION','ACTIVO_FIJO','LOP_DEPRECIACION','Depreciacion activo LOP', 'HABER', '120899', 1, FALSE, TRUE,  FALSE, FALSE, 'ACTIVO', 'Depreciacion acumulada activo')
) AS v(modulo,submodulo,tipo_documento,codigo_evento,nombre_evento,lado,codigo_cuenta,orden,requiere_centro_costo,requiere_documento,requiere_cliente,requiere_proveedor,estado,descripcion)
ON CONFLICT ON CONSTRAINT uq_fin_cfg_modulo_evento_lado_orden
DO UPDATE SET
    codigo_cuenta = EXCLUDED.codigo_cuenta,
    nombre_evento = EXCLUDED.nombre_evento,
    requiere_centro_costo = EXCLUDED.requiere_centro_costo,
    requiere_documento = EXCLUDED.requiere_documento,
    requiere_cliente = EXCLUDED.requiere_cliente,
    requiere_proveedor = EXCLUDED.requiere_proveedor,
    estado = EXCLUDED.estado,
    descripcion = EXCLUDED.descripcion;

-- Correcciones en instalaciones existentes.
UPDATE fin.config_contable
SET codigo_cuenta = CASE
    WHEN codigo_evento = 'LOP_ACTIVACION' AND lado = 'DEBE' THEN '120801'
    WHEN codigo_evento = 'LOP_FACTURACION' AND lado = 'DEBE' THEN '113801'
    WHEN codigo_evento = 'LOP_DEPRECIACION' AND lado = 'HABER' THEN '120899'
    ELSE codigo_cuenta
END
WHERE codigo_evento IN ('LOP_ACTIVACION', 'LOP_FACTURACION', 'LOP_DEPRECIACION');

UPDATE fin.config_contable_detalle_modulo
SET codigo_cuenta = CASE
    WHEN codigo_evento = 'LOP_ACTIVACION' AND submodulo = 'ACTIVACION' AND lado = 'DEBE' THEN '120801'
    WHEN codigo_evento = 'LOP_FACTURACION' AND submodulo = 'FACTURACION' AND lado = 'DEBE' THEN '113801'
    WHEN codigo_evento = 'LOP_DEPRECIACION' AND submodulo = 'DEPRECIACION' AND lado = 'HABER' THEN '120899'
    ELSE codigo_cuenta
END
WHERE modulo = 'LEASING_OP'
  AND codigo_evento IN ('LOP_ACTIVACION', 'LOP_FACTURACION', 'LOP_DEPRECIACION');

COMMIT;
