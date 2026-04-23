-- db/psql/092_fin_ventas_costo_venta_premium.sql
-- ============================================================
-- VENTAS + COSTO DE VENTA + SALIDA DE INVENTARIO
-- CAMINO DORADO PREMIUM
-- ============================================================

BEGIN;

-- ============================================================
-- 1) CUENTA CONTABLE DE COSTO DE VENTA
-- ============================================================
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
(
    '510101',
    'COSTO DE VENTAS',
    3,
    NULL,
    'COSTO',
    'COSTO_VENTA',
    'DEUDORA',
    TRUE,
    TRUE,
    'ACTIVO',
    'Reconocimiento del costo de la mercadería vendida'
)
ON CONFLICT (codigo) DO UPDATE
SET
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
WHERE h.codigo = '510101'
  AND p.codigo = '510000';

-- ============================================================
-- 2) LIMPIEZA SOLO DEL FLUJO COSTO DE VENTA
-- ============================================================
DELETE FROM fin.config_contable
WHERE codigo_evento IN (
    'COSTO_VENTA_CONTADO',
    'COSTO_VENTA_CREDITO'
);

DELETE FROM fin.config_contable_detalle_modulo
WHERE codigo_evento IN (
    'COSTO_VENTA_CONTADO',
    'COSTO_VENTA_CREDITO'
);

-- ============================================================
-- 3) CONFIG SIMPLE
-- ============================================================
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
VALUES
(
    'COSTO_VENTA_CONTADO',
    'Costo de venta contado',
    'DEBE',
    '510101',
    1,
    TRUE,
    TRUE,
    'ACTIVO',
    'Reconocimiento del costo de la venta contado'
),
(
    'COSTO_VENTA_CONTADO',
    'Costo de venta contado',
    'HABER',
    '110401',
    1,
    FALSE,
    TRUE,
    'ACTIVO',
    'Salida de inventario por venta contado'
),
(
    'COSTO_VENTA_CREDITO',
    'Costo de venta crédito',
    'DEBE',
    '510101',
    1,
    TRUE,
    TRUE,
    'ACTIVO',
    'Reconocimiento del costo de la venta crédito'
),
(
    'COSTO_VENTA_CREDITO',
    'Costo de venta crédito',
    'HABER',
    '110401',
    1,
    FALSE,
    TRUE,
    'ACTIVO',
    'Salida de inventario por venta crédito'
);

-- ============================================================
-- 4) CONFIG AVANZADA POR MÓDULO
-- ============================================================
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
VALUES
(
    'VENTAS',
    'NOTA_VENTA',
    'CONTADO',
    'COSTO_VENTA_CONTADO',
    'Costo de venta contado',
    'DEBE',
    '510101',
    1,
    TRUE,
    TRUE,
    TRUE,
    FALSE,
    'ACTIVO',
    'Costo de venta asociado a la nota de venta contado'
),
(
    'VENTAS',
    'NOTA_VENTA',
    'CONTADO',
    'COSTO_VENTA_CONTADO',
    'Costo de venta contado',
    'HABER',
    '110401',
    1,
    FALSE,
    TRUE,
    TRUE,
    FALSE,
    'ACTIVO',
    'Salida de inventario de mercadería vendida contado'
),
(
    'VENTAS',
    'NOTA_VENTA',
    'CREDITO',
    'COSTO_VENTA_CREDITO',
    'Costo de venta crédito',
    'DEBE',
    '510101',
    1,
    TRUE,
    TRUE,
    TRUE,
    FALSE,
    'ACTIVO',
    'Costo de venta asociado a la nota de venta crédito'
),
(
    'VENTAS',
    'NOTA_VENTA',
    'CREDITO',
    'COSTO_VENTA_CREDITO',
    'Costo de venta crédito',
    'HABER',
    '110401',
    1,
    FALSE,
    TRUE,
    TRUE,
    FALSE,
    'ACTIVO',
    'Salida de inventario de mercadería vendida crédito'
);

COMMIT;