-- db/psql/090_fin_config_contable.sql
-- ============================================================
-- CONFIGURACIÓN CONTABLE PREMIUM · CAMINO DORADO
-- Evalua ERP
-- ============================================================

BEGIN;

-- ============================================================
-- TABLA PRINCIPAL DE CONFIGURACIÓN CONTABLE
-- ============================================================
CREATE TABLE IF NOT EXISTS fin.config_contable (
    id BIGSERIAL PRIMARY KEY,
    codigo_evento VARCHAR(50) NOT NULL,
    nombre_evento VARCHAR(150) NOT NULL,
    lado VARCHAR(10) NOT NULL, -- DEBE / HABER
    codigo_cuenta VARCHAR(30) NOT NULL,
    orden INTEGER NOT NULL DEFAULT 1,
    requiere_centro_costo BOOLEAN NOT NULL DEFAULT FALSE,
    requiere_documento BOOLEAN NOT NULL DEFAULT FALSE,
    estado VARCHAR(20) NOT NULL DEFAULT 'ACTIVO',
    descripcion TEXT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP NOT NULL DEFAULT NOW(),

    CONSTRAINT uq_fin_config_contable_evento_lado_orden
        UNIQUE (codigo_evento, lado, orden),

    CONSTRAINT chk_fin_config_contable_lado
        CHECK (lado IN ('DEBE', 'HABER')),

    CONSTRAINT chk_fin_config_contable_estado
        CHECK (estado IN ('ACTIVO', 'INACTIVO')),

    CONSTRAINT fk_fin_config_contable_plan_cuenta
        FOREIGN KEY (codigo_cuenta)
        REFERENCES fin.plan_cuenta(codigo)
        ON UPDATE CASCADE
        ON DELETE RESTRICT
);

CREATE INDEX IF NOT EXISTS ix_fin_config_contable_evento
    ON fin.config_contable(codigo_evento);

CREATE INDEX IF NOT EXISTS ix_fin_config_contable_cuenta
    ON fin.config_contable(codigo_cuenta);

CREATE INDEX IF NOT EXISTS ix_fin_config_contable_estado
    ON fin.config_contable(estado);

-- ============================================================
-- TABLA AVANZADA POR MÓDULO / DOCUMENTO / ESCENARIO
-- CAMINO A
-- ============================================================
CREATE TABLE IF NOT EXISTS fin.config_contable_detalle_modulo (
    id BIGSERIAL PRIMARY KEY,
    modulo VARCHAR(50) NOT NULL,               -- VENTAS, COBRANZA, CXP, INVENTARIO, CAJA
    submodulo VARCHAR(50) NULL,                -- POS, NOTA_VENTA, RECIBO, FACTURA_COMPRA, etc.
    tipo_documento VARCHAR(50) NULL,           -- CONTADO, CREDITO, FACTURA_AFECTA, etc.
    codigo_evento VARCHAR(50) NOT NULL,        -- referencia funcional
    nombre_evento VARCHAR(150) NOT NULL,
    lado VARCHAR(10) NOT NULL,                 -- DEBE / HABER
    codigo_cuenta VARCHAR(30) NOT NULL,
    orden INTEGER NOT NULL DEFAULT 1,
    requiere_centro_costo BOOLEAN NOT NULL DEFAULT FALSE,
    requiere_documento BOOLEAN NOT NULL DEFAULT FALSE,
    requiere_cliente BOOLEAN NOT NULL DEFAULT FALSE,
    requiere_proveedor BOOLEAN NOT NULL DEFAULT FALSE,
    estado VARCHAR(20) NOT NULL DEFAULT 'ACTIVO',
    descripcion TEXT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP NOT NULL DEFAULT NOW(),

    CONSTRAINT uq_fin_cfg_modulo_evento_lado_orden
        UNIQUE (modulo, submodulo, tipo_documento, codigo_evento, lado, orden),

    CONSTRAINT chk_fin_cfg_modulo_lado
        CHECK (lado IN ('DEBE', 'HABER')),

    CONSTRAINT chk_fin_cfg_modulo_estado
        CHECK (estado IN ('ACTIVO', 'INACTIVO')),

    CONSTRAINT fk_fin_cfg_modulo_plan_cuenta
        FOREIGN KEY (codigo_cuenta)
        REFERENCES fin.plan_cuenta(codigo)
        ON UPDATE CASCADE
        ON DELETE RESTRICT
);

CREATE INDEX IF NOT EXISTS ix_fin_cfg_modulo_modulo
    ON fin.config_contable_detalle_modulo(modulo);

CREATE INDEX IF NOT EXISTS ix_fin_cfg_modulo_submodulo
    ON fin.config_contable_detalle_modulo(submodulo);

CREATE INDEX IF NOT EXISTS ix_fin_cfg_modulo_tipo_doc
    ON fin.config_contable_detalle_modulo(tipo_documento);

CREATE INDEX IF NOT EXISTS ix_fin_cfg_modulo_evento
    ON fin.config_contable_detalle_modulo(codigo_evento);

CREATE INDEX IF NOT EXISTS ix_fin_cfg_modulo_estado
    ON fin.config_contable_detalle_modulo(estado);

-- ============================================================
-- LIMPIEZA CONTROLADA DE SEED
-- ============================================================
DELETE FROM fin.config_contable;
DELETE FROM fin.config_contable_detalle_modulo;

-- ============================================================
-- SEED BÁSICO
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
('VENTA_CONTADO', 'Venta contado', 'DEBE',  '110201', 1, FALSE, TRUE,  'ACTIVO', 'Ingreso por venta contado'),
('VENTA_CONTADO', 'Venta contado', 'HABER', '410101', 1, TRUE,  TRUE,  'ACTIVO', 'Reconocimiento de ventas'),
('VENTA_CONTADO', 'Venta contado', 'HABER', '210201', 2, FALSE, TRUE,  'ACTIVO', 'IVA débito fiscal'),

('VENTA_CREDITO', 'Venta crédito', 'DEBE',  '110301', 1, FALSE, TRUE,  'ACTIVO', 'Cuenta por cobrar a clientes'),
('VENTA_CREDITO', 'Venta crédito', 'HABER', '410101', 1, TRUE,  TRUE,  'ACTIVO', 'Reconocimiento de ventas'),
('VENTA_CREDITO', 'Venta crédito', 'HABER', '210201', 2, FALSE, TRUE,  'ACTIVO', 'IVA débito fiscal'),

('COBRANZA_CLIENTE', 'Cobranza de cliente', 'DEBE',  '110201', 1, FALSE, TRUE, 'ACTIVO', 'Ingreso a caja o banco'),
('COBRANZA_CLIENTE', 'Cobranza de cliente', 'HABER', '110301', 1, FALSE, TRUE, 'ACTIVO', 'Disminución de cuenta por cobrar'),

('COMPRA_AFECTA', 'Compra afecta', 'DEBE',  '110401', 1, FALSE, TRUE, 'ACTIVO', 'Ingreso a inventario'),
('COMPRA_AFECTA', 'Compra afecta', 'DEBE',  '110501', 2, FALSE, TRUE, 'ACTIVO', 'IVA crédito fiscal'),
('COMPRA_AFECTA', 'Compra afecta', 'HABER', '210101', 1, FALSE, TRUE, 'ACTIVO', 'Proveedor por pagar'),

('COMPRA_GASTO_AFECTA', 'Compra de gasto afecta', 'DEBE',  '610104', 1, TRUE,  TRUE, 'ACTIVO', 'Registro de gasto'),
('COMPRA_GASTO_AFECTA', 'Compra de gasto afecta', 'DEBE',  '110501', 2, FALSE, TRUE, 'ACTIVO', 'IVA crédito fiscal'),
('COMPRA_GASTO_AFECTA', 'Compra de gasto afecta', 'HABER', '210101', 1, FALSE, TRUE, 'ACTIVO', 'Proveedor por pagar'),

('PAGO_PROVEEDOR', 'Pago a proveedor', 'DEBE',  '210101', 1, FALSE, TRUE, 'ACTIVO', 'Cancelación proveedor'),
('PAGO_PROVEEDOR', 'Pago a proveedor', 'HABER', '110201', 1, FALSE, TRUE, 'ACTIVO', 'Salida de caja o banco');

-- ============================================================
-- SEED AVANZADO POR MÓDULO
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
('VENTAS', 'NOTA_VENTA', 'CONTADO', 'VENTA_CONTADO', 'Venta contado', 'DEBE',  '110201', 1, FALSE, TRUE,  TRUE,  FALSE, 'ACTIVO', 'Caja / banco por venta contado'),
('VENTAS', 'NOTA_VENTA', 'CONTADO', 'VENTA_CONTADO', 'Venta contado', 'HABER', '410101', 1, TRUE,  TRUE,  TRUE,  FALSE, 'ACTIVO', 'Ingreso por ventas'),
('VENTAS', 'NOTA_VENTA', 'CONTADO', 'VENTA_CONTADO', 'Venta contado', 'HABER', '210201', 2, FALSE, TRUE,  TRUE,  FALSE, 'ACTIVO', 'IVA débito'),

('VENTAS', 'NOTA_VENTA', 'CREDITO', 'VENTA_CREDITO', 'Venta crédito', 'DEBE',  '110301', 1, FALSE, TRUE,  TRUE,  FALSE, 'ACTIVO', 'Clientes'),
('VENTAS', 'NOTA_VENTA', 'CREDITO', 'VENTA_CREDITO', 'Venta crédito', 'HABER', '410101', 1, TRUE,  TRUE,  TRUE,  FALSE, 'ACTIVO', 'Ingreso por ventas'),
('VENTAS', 'NOTA_VENTA', 'CREDITO', 'VENTA_CREDITO', 'Venta crédito', 'HABER', '210201', 2, FALSE, TRUE,  TRUE,  FALSE, 'ACTIVO', 'IVA débito'),

('COBRANZA', 'RECIBO', 'NORMAL', 'COBRANZA_CLIENTE', 'Cobranza cliente', 'DEBE',  '110201', 1, FALSE, TRUE, TRUE,  FALSE, 'ACTIVO', 'Ingreso de fondos'),
('COBRANZA', 'RECIBO', 'NORMAL', 'COBRANZA_CLIENTE', 'Cobranza cliente', 'HABER', '110301', 1, FALSE, TRUE, TRUE,  FALSE, 'ACTIVO', 'Baja de CxC'),

('CXP', 'FACTURA_COMPRA', 'AFECTA', 'COMPRA_AFECTA', 'Compra afecta', 'DEBE',  '110401', 1, FALSE, TRUE, FALSE, TRUE, 'ACTIVO', 'Ingreso a inventario'),
('CXP', 'FACTURA_COMPRA', 'AFECTA', 'COMPRA_AFECTA', 'Compra afecta', 'DEBE',  '110501', 2, FALSE, TRUE, FALSE, TRUE, 'ACTIVO', 'IVA crédito'),
('CXP', 'FACTURA_COMPRA', 'AFECTA', 'COMPRA_AFECTA', 'Compra afecta', 'HABER', '210101', 1, FALSE, TRUE, FALSE, TRUE, 'ACTIVO', 'Proveedor'),

('CXP', 'FACTURA_GASTO', 'AFECTA', 'COMPRA_GASTO_AFECTA', 'Compra gasto afecta', 'DEBE',  '610104', 1, TRUE,  TRUE, FALSE, TRUE, 'ACTIVO', 'Gasto'),
('CXP', 'FACTURA_GASTO', 'AFECTA', 'COMPRA_GASTO_AFECTA', 'Compra gasto afecta', 'DEBE',  '110501', 2, FALSE, TRUE, FALSE, TRUE, 'ACTIVO', 'IVA crédito'),
('CXP', 'FACTURA_GASTO', 'AFECTA', 'COMPRA_GASTO_AFECTA', 'Compra gasto afecta', 'HABER', '210101', 1, FALSE, TRUE, FALSE, TRUE, 'ACTIVO', 'Proveedor'),

('TESORERIA', 'PAGO_PROVEEDOR', 'NORMAL', 'PAGO_PROVEEDOR', 'Pago a proveedor', 'DEBE',  '210101', 1, FALSE, TRUE, FALSE, TRUE, 'ACTIVO', 'Baja proveedor'),
('TESORERIA', 'PAGO_PROVEEDOR', 'NORMAL', 'PAGO_PROVEEDOR', 'Pago a proveedor', 'HABER', '110201', 1, FALSE, TRUE, FALSE, TRUE, 'ACTIVO', 'Salida de fondos');

-- ============================================================
-- VISTAS
-- ============================================================
CREATE OR REPLACE VIEW fin.vw_config_contable AS
SELECT
    cc.id,
    cc.codigo_evento,
    cc.nombre_evento,
    cc.lado,
    cc.codigo_cuenta,
    pc.nombre AS nombre_cuenta,
    pc.tipo,
    pc.clasificacion,
    cc.orden,
    cc.requiere_centro_costo,
    cc.requiere_documento,
    cc.estado,
    cc.descripcion
FROM fin.config_contable cc
INNER JOIN fin.plan_cuenta pc
    ON pc.codigo = cc.codigo_cuenta;

CREATE OR REPLACE VIEW fin.vw_config_contable_modulo AS
SELECT
    c.id,
    c.modulo,
    c.submodulo,
    c.tipo_documento,
    c.codigo_evento,
    c.nombre_evento,
    c.lado,
    c.codigo_cuenta,
    pc.nombre AS nombre_cuenta,
    pc.tipo,
    pc.clasificacion,
    c.orden,
    c.requiere_centro_costo,
    c.requiere_documento,
    c.requiere_cliente,
    c.requiere_proveedor,
    c.estado,
    c.descripcion
FROM fin.config_contable_detalle_modulo c
INNER JOIN fin.plan_cuenta pc
    ON pc.codigo = c.codigo_cuenta;

COMMIT;