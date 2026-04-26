BEGIN;

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
    ('LOP_ACTIVACION', 'Activacion contable leasing operativo', 'DEBE',  '110301', 1, FALSE, TRUE, 'ACTIVO', 'Alta cartera leasing operativo'),
    ('LOP_ACTIVACION', 'Activacion contable leasing operativo', 'HABER', '110401', 1, FALSE, TRUE, 'ACTIVO', 'Reclasificacion de activo arrendado'),
    ('LOP_FACTURACION', 'Facturacion mensual cuota leasing operativo', 'DEBE',  '110301', 1, FALSE, TRUE, 'ACTIVO', 'Cuenta por cobrar cliente cuota LOP'),
    ('LOP_FACTURACION', 'Facturacion mensual cuota leasing operativo', 'HABER', '410101', 1, TRUE,  TRUE, 'ACTIVO', 'Ingreso por renta leasing operativo'),
    ('LOP_FACTURACION', 'Facturacion mensual cuota leasing operativo', 'HABER', '210201', 2, FALSE, TRUE, 'ACTIVO', 'IVA debito fiscal cuota LOP'),
    ('LOP_DEPRECIACION', 'Depreciacion mensual activo leasing operativo', 'DEBE',  '610104', 1, TRUE,  TRUE, 'ACTIVO', 'Gasto depreciacion activo LOP'),
    ('LOP_DEPRECIACION', 'Depreciacion mensual activo leasing operativo', 'HABER', '110401', 1, FALSE, TRUE, 'ACTIVO', 'Disminucion valor activo LOP')
) AS v(codigo_evento,nombre_evento,lado,codigo_cuenta,orden,requiere_centro_costo,requiere_documento,estado,descripcion)
WHERE NOT EXISTS (
    SELECT 1 FROM fin.config_contable c
    WHERE c.codigo_evento = v.codigo_evento
      AND c.lado = v.lado
      AND c.codigo_cuenta = v.codigo_cuenta
      AND c.orden = v.orden
);

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
    ('LEASING_OP', 'ACTIVACION',  'CONTRATO',   'LOP_ACTIVACION',  'Activacion contable LOP', 'DEBE',  '110301', 1, FALSE, TRUE,  TRUE,  FALSE, 'ACTIVO', 'Alta cartera por activacion'),
    ('LEASING_OP', 'ACTIVACION',  'CONTRATO',   'LOP_ACTIVACION',  'Activacion contable LOP', 'HABER', '110401', 1, FALSE, TRUE,  TRUE,  FALSE, 'ACTIVO', 'Reclasificacion activo arrendado'),
    ('LEASING_OP', 'FACTURACION', 'CUOTA',      'LOP_FACTURACION', 'Facturacion cuota LOP',   'DEBE',  '110301', 1, FALSE, TRUE,  TRUE,  FALSE, 'ACTIVO', 'CxC cuota mensual'),
    ('LEASING_OP', 'FACTURACION', 'CUOTA',      'LOP_FACTURACION', 'Facturacion cuota LOP',   'HABER', '410101', 1, TRUE,  TRUE,  TRUE,  FALSE, 'ACTIVO', 'Ingreso por renta'),
    ('LEASING_OP', 'FACTURACION', 'CUOTA',      'LOP_FACTURACION', 'Facturacion cuota LOP',   'HABER', '210201', 2, FALSE, TRUE,  TRUE,  FALSE, 'ACTIVO', 'IVA debito'),
    ('LEASING_OP', 'DEPRECIACION','ACTIVO_FIJO','LOP_DEPRECIACION','Depreciacion activo LOP', 'DEBE',  '610104', 1, TRUE,  TRUE,  FALSE, FALSE, 'ACTIVO', 'Gasto depreciacion'),
    ('LEASING_OP', 'DEPRECIACION','ACTIVO_FIJO','LOP_DEPRECIACION','Depreciacion activo LOP', 'HABER', '110401', 1, FALSE, TRUE,  FALSE, FALSE, 'ACTIVO', 'Baja valor activo')
) AS v(modulo,submodulo,tipo_documento,codigo_evento,nombre_evento,lado,codigo_cuenta,orden,requiere_centro_costo,requiere_documento,requiere_cliente,requiere_proveedor,estado,descripcion)
WHERE NOT EXISTS (
    SELECT 1 FROM fin.config_contable_detalle_modulo d
    WHERE d.modulo = v.modulo
      AND d.submodulo = v.submodulo
      AND d.tipo_documento = v.tipo_documento
      AND d.codigo_evento = v.codigo_evento
      AND d.lado = v.lado
      AND d.codigo_cuenta = v.codigo_cuenta
      AND d.orden = v.orden
);

COMMIT;
