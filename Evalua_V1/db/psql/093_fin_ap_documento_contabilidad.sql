-- db/psql/093_fin_ap_documento_contabilidad.sql
-- Campos de contabilización en documentos AP + seed eventos exentos (opcional)

BEGIN;

ALTER TABLE fin.ap_documento
    ADD COLUMN IF NOT EXISTS tipo_compra_contable VARCHAR(20) NOT NULL DEFAULT 'GASTO';

ALTER TABLE fin.ap_documento
    ADD COLUMN IF NOT EXISTS cuenta_gasto_codigo VARCHAR(30) NULL;

ALTER TABLE fin.ap_documento
    ADD COLUMN IF NOT EXISTS cuenta_proveedores_codigo VARCHAR(30) NULL;

ALTER TABLE fin.ap_documento
    ADD COLUMN IF NOT EXISTS asiento_id BIGINT NULL;

COMMENT ON COLUMN fin.ap_documento.tipo_compra_contable IS 'INVENTARIO | GASTO — define plantilla contable por defecto';
COMMENT ON COLUMN fin.ap_documento.cuenta_gasto_codigo IS 'Cuenta debe principal (compra/gasto); si NULL usa plan por tipo';
COMMENT ON COLUMN fin.ap_documento.cuenta_proveedores_codigo IS 'Cuenta haber proveedores; si NULL usa 210101 del plan seed';
COMMENT ON COLUMN fin.ap_documento.asiento_id IS 'ID en asientos_contables generado al registrar el documento';

-- Eventos exentos (solo primera línea DEBE + HABER proveedor; sin IVA)
INSERT INTO fin.config_contable (codigo_evento, nombre_evento, lado, codigo_cuenta, orden, requiere_centro_costo, requiere_documento, estado, descripcion)
SELECT 'COMPRA_INVENTARIO_EXENTO', 'Compra inventario exenta', 'DEBE', '110401', 1, FALSE, TRUE, 'ACTIVO', 'Ingreso inventario exento'
WHERE NOT EXISTS (SELECT 1 FROM fin.config_contable WHERE codigo_evento = 'COMPRA_INVENTARIO_EXENTO');

INSERT INTO fin.config_contable (codigo_evento, nombre_evento, lado, codigo_cuenta, orden, requiere_centro_costo, requiere_documento, estado, descripcion)
SELECT 'COMPRA_INVENTARIO_EXENTO', 'Compra inventario exenta', 'HABER', '210101', 1, FALSE, TRUE, 'ACTIVO', 'Proveedor por pagar'
WHERE NOT EXISTS (SELECT 1 FROM fin.config_contable WHERE codigo_evento = 'COMPRA_INVENTARIO_EXENTO' AND lado = 'HABER');

INSERT INTO fin.config_contable (codigo_evento, nombre_evento, lado, codigo_cuenta, orden, requiere_centro_costo, requiere_documento, estado, descripcion)
SELECT 'COMPRA_GASTO_EXENTO', 'Compra gasto exenta', 'DEBE', '610104', 1, TRUE, TRUE, 'ACTIVO', 'Gasto exento'
WHERE NOT EXISTS (SELECT 1 FROM fin.config_contable WHERE codigo_evento = 'COMPRA_GASTO_EXENTO');

INSERT INTO fin.config_contable (codigo_evento, nombre_evento, lado, codigo_cuenta, orden, requiere_centro_costo, requiere_documento, estado, descripcion)
SELECT 'COMPRA_GASTO_EXENTO', 'Compra gasto exenta', 'HABER', '210101', 1, FALSE, TRUE, 'ACTIVO', 'Proveedor por pagar'
WHERE NOT EXISTS (SELECT 1 FROM fin.config_contable WHERE codigo_evento = 'COMPRA_GASTO_EXENTO' AND lado = 'HABER');

COMMIT;
