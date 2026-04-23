-- db/psql/091_fin_inventario_recepcion_premium.sql
-- ============================================================
-- INVENTARIO + RECEPCIÓN SIN FACTURA + FACTURA DESDE RECEPCIÓN
-- CAMINO DORADO PREMIUM
-- ============================================================

BEGIN;

-- ============================================================
-- 1) CUENTA CONTABLE NUEVA
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
    '210110',
    'PROVEEDORES POR FACTURAR',
    3,
    NULL,
    'PASIVO',
    'PASIVO_CORRIENTE',
    'ACREEDORA',
    TRUE,
    FALSE,
    'ACTIVO',
    'Mercadería recibida y pendiente de factura'
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

-- ============================================================
-- 2) AJUSTE PADRE DE LA CUENTA NUEVA
-- ============================================================
UPDATE fin.plan_cuenta h
SET cuenta_padre_id = p.id
FROM fin.plan_cuenta p
WHERE h.codigo = '210110'
  AND p.codigo = '210000';

-- ============================================================
-- 3) LIMPIEZA DE CONFIGURACIÓN ANTERIOR SOLO DE ESTE FLUJO
-- ============================================================
DELETE FROM fin.config_contable
WHERE codigo_evento IN (
    'INGRESO_COMPRA_SIN_FACTURA',
    'FACTURA_PROVEEDOR_DESDE_RECEPCION'
);

DELETE FROM fin.config_contable_detalle_modulo
WHERE codigo_evento IN (
    'INGRESO_COMPRA_SIN_FACTURA',
    'FACTURA_PROVEEDOR_DESDE_RECEPCION'
);

-- ============================================================
-- 4) CONFIG CONTABLE SIMPLE
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
    'INGRESO_COMPRA_SIN_FACTURA',
    'Ingreso físico de mercadería sin factura',
    'DEBE',
    '110401',
    1,
    FALSE,
    TRUE,
    'ACTIVO',
    'Ingreso valorizado a inventario'
),
(
    'INGRESO_COMPRA_SIN_FACTURA',
    'Ingreso físico de mercadería sin factura',
    'HABER',
    '210110',
    1,
    FALSE,
    TRUE,
    'ACTIVO',
    'Reconocimiento de proveedor por facturar'
),
(
    'FACTURA_PROVEEDOR_DESDE_RECEPCION',
    'Factura proveedor desde recepción previa',
    'DEBE',
    '210110',
    1,
    FALSE,
    TRUE,
    'ACTIVO',
    'Reverso de cuenta transitoria de recepción'
),
(
    'FACTURA_PROVEEDOR_DESDE_RECEPCION',
    'Factura proveedor desde recepción previa',
    'DEBE',
    '110501',
    2,
    FALSE,
    TRUE,
    'ACTIVO',
    'IVA crédito fiscal'
),
(
    'FACTURA_PROVEEDOR_DESDE_RECEPCION',
    'Factura proveedor desde recepción previa',
    'HABER',
    '210101',
    1,
    FALSE,
    TRUE,
    'ACTIVO',
    'Proveedor formalmente facturado'
);

-- ============================================================
-- 5) CONFIG CONTABLE AVANZADA POR MÓDULO
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
    'INVENTARIO',
    'RECEPCION',
    'COMPRA_SIN_FACTURA',
    'INGRESO_COMPRA_SIN_FACTURA',
    'Ingreso físico de mercadería sin factura',
    'DEBE',
    '110401',
    1,
    FALSE,
    TRUE,
    FALSE,
    TRUE,
    'ACTIVO',
    'Ingreso valorizado al inventario'
),
(
    'INVENTARIO',
    'RECEPCION',
    'COMPRA_SIN_FACTURA',
    'INGRESO_COMPRA_SIN_FACTURA',
    'Ingreso físico de mercadería sin factura',
    'HABER',
    '210110',
    1,
    FALSE,
    TRUE,
    FALSE,
    TRUE,
    'ACTIVO',
    'Proveedor por facturar por mercadería recibida'
),
(
    'CXP',
    'FACTURA_RECEPCIONADA',
    'AFECTA',
    'FACTURA_PROVEEDOR_DESDE_RECEPCION',
    'Factura proveedor desde recepción previa',
    'DEBE',
    '210110',
    1,
    FALSE,
    TRUE,
    FALSE,
    TRUE,
    'ACTIVO',
    'Cancelación de cuenta transitoria'
),
(
    'CXP',
    'FACTURA_RECEPCIONADA',
    'AFECTA',
    'FACTURA_PROVEEDOR_DESDE_RECEPCION',
    'Factura proveedor desde recepción previa',
    'DEBE',
    '110501',
    2,
    FALSE,
    TRUE,
    FALSE,
    TRUE,
    'ACTIVO',
    'Reconocimiento de IVA crédito'
),
(
    'CXP',
    'FACTURA_RECEPCIONADA',
    'AFECTA',
    'FACTURA_PROVEEDOR_DESDE_RECEPCION',
    'Factura proveedor desde recepción previa',
    'HABER',
    '210101',
    1,
    FALSE,
    TRUE,
    FALSE,
    TRUE,
    'ACTIVO',
    'Reconocimiento de deuda formal con proveedor'
);

COMMIT;