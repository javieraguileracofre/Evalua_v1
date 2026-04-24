-- db/psql/097_fin_ap_post_create_all.sql
-- Requiere que existan fin.ap_documento, ap_documento_detalle, ap_pago, ap_pago_aplicacion, ap_documento_impuesto.
-- Si tras el 094 la app NO creó tablas (permisos), crearlas con postgres:
--   python tools/create_fin_ap_tables.py --database-url "postgresql+psycopg://postgres:...@localhost:5432/EVALUA_V1_DB"
-- Luego ejecutar este archivo.

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

BEGIN;

CREATE OR REPLACE VIEW fin.vw_kpi_dashboard_fin AS
WITH
ap AS (
  SELECT
    COUNT(*)::bigint AS docs_total,
    COALESCE(
      SUM(
        (
          SELECT COALESCE(SUM(det.neto_linea + det.iva_linea), 0)::numeric
          FROM fin.ap_documento_detalle det
          WHERE det.documento_id = d.id
        )
        + (
          SELECT COALESCE(SUM(imp.monto), 0)::numeric
          FROM fin.ap_documento_impuesto imp
          WHERE imp.documento_id = d.id
        )
      ),
      0
    )::numeric(18, 2) AS monto_total,
    COALESCE(
      SUM(
        GREATEST(
          (
            SELECT COALESCE(SUM(det.neto_linea + det.iva_linea), 0)::numeric
            FROM fin.ap_documento_detalle det
            WHERE det.documento_id = d.id
          )
          + (
            SELECT COALESCE(SUM(imp.monto), 0)::numeric
            FROM fin.ap_documento_impuesto imp
            WHERE imp.documento_id = d.id
          )
          - (
            SELECT COALESCE(SUM(a.monto_aplicado), 0)::numeric
            FROM fin.ap_pago_aplicacion a
            WHERE a.documento_id = d.id
          ),
          0::numeric
        )
      ),
      0
    )::numeric(18, 2) AS saldo_pendiente,
    COALESCE(
      SUM(
        CASE
          WHEN d.fecha_vencimiento < CURRENT_DATE
            AND GREATEST(
              (
                SELECT COALESCE(SUM(det.neto_linea + det.iva_linea), 0)::numeric
                FROM fin.ap_documento_detalle det
                WHERE det.documento_id = d.id
              )
              + (
                SELECT COALESCE(SUM(imp.monto), 0)::numeric
                FROM fin.ap_documento_impuesto imp
                WHERE imp.documento_id = d.id
              )
              - (
                SELECT COALESCE(SUM(a.monto_aplicado), 0)::numeric
                FROM fin.ap_pago_aplicacion a
                WHERE a.documento_id = d.id
              ),
              0::numeric
            ) > 0
          THEN GREATEST(
            (
              SELECT COALESCE(SUM(det.neto_linea + det.iva_linea), 0)::numeric
              FROM fin.ap_documento_detalle det
              WHERE det.documento_id = d.id
            )
            + (
              SELECT COALESCE(SUM(imp.monto), 0)::numeric
              FROM fin.ap_documento_impuesto imp
              WHERE imp.documento_id = d.id
            )
            - (
              SELECT COALESCE(SUM(a.monto_aplicado), 0)::numeric
              FROM fin.ap_pago_aplicacion a
              WHERE a.documento_id = d.id
            ),
            0::numeric
          )
          ELSE 0::numeric
        END
      ),
      0
    )::numeric(18, 2) AS saldo_vencido
  FROM fin.ap_documento d
  WHERE COALESCE(d.estado::text, '') <> 'ANULADO'
),
pagos_mes AS (
  SELECT
    COALESCE(SUM(p.monto_total), 0)::numeric(18, 2) AS pagado_mes
  FROM fin.ap_pago p
  WHERE date_trunc('month', p.fecha_pago::timestamp) = date_trunc('month', CURRENT_TIMESTAMP)
),
gastos_mes AS (
  SELECT 0::numeric(18, 2) AS gasto_mes
)
SELECT
  ap.docs_total,
  ap.monto_total,
  ap.saldo_pendiente,
  ap.saldo_vencido,
  pagos_mes.pagado_mes,
  gastos_mes.gasto_mes
FROM ap, pagos_mes, gastos_mes;

COMMIT;

BEGIN;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'fk_fin_ap_pago_banco_proveedor'
    ) THEN
        ALTER TABLE fin.ap_pago
        ADD CONSTRAINT fk_fin_ap_pago_banco_proveedor
        FOREIGN KEY (banco_proveedor_id)
        REFERENCES public.proveedor_banco(id)
        ON UPDATE CASCADE ON DELETE SET NULL;
    END IF;
END $$;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'fk_fin_ap_documento_proveedor'
    ) THEN
        ALTER TABLE fin.ap_documento
        ADD CONSTRAINT fk_fin_ap_documento_proveedor
        FOREIGN KEY (proveedor_id)
        REFERENCES public.proveedor(id)
        ON UPDATE CASCADE ON DELETE RESTRICT;
    END IF;
END $$;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'fk_fin_ap_pago_proveedor'
    ) THEN
        ALTER TABLE fin.ap_pago
        ADD CONSTRAINT fk_fin_ap_pago_proveedor
        FOREIGN KEY (proveedor_id)
        REFERENCES public.proveedor(id)
        ON UPDATE CASCADE ON DELETE RESTRICT;
    END IF;
END $$;

CREATE INDEX IF NOT EXISTS ix_fin_ap_pago_proveedor_fecha
    ON fin.ap_pago (proveedor_id, fecha_pago);
CREATE INDEX IF NOT EXISTS ix_fin_ap_pago_aplicacion_documento
    ON fin.ap_pago_aplicacion (documento_id);
CREATE INDEX IF NOT EXISTS ix_fin_ap_documento_saldo_estado
    ON fin.ap_documento (estado, saldo_pendiente);

CREATE OR REPLACE VIEW fin.vw_cxp_resumen AS
SELECT
    d.id,
    d.uuid,
    d.proveedor_id,
    p.rut,
    p.razon_social,
    p.nombre_fantasia,
    d.tipo,
    d.estado,
    d.folio,
    d.fecha_emision,
    d.fecha_recepcion,
    d.fecha_vencimiento,
    d.moneda,
    d.tipo_cambio,
    d.neto,
    d.exento,
    d.iva,
    d.otros_impuestos,
    d.total,
    d.saldo_pendiente,
    d.referencia,
    d.observaciones,
    CASE
        WHEN d.saldo_pendiente <= 0 THEN 'PAGADO'
        WHEN d.fecha_vencimiento < CURRENT_DATE THEN 'VENCIDO'
        WHEN d.fecha_vencimiento <= CURRENT_DATE + 7 THEN 'POR_VENCER'
        ELSE 'AL_DIA'
    END AS estado_visual,
    GREATEST((CURRENT_DATE - d.fecha_vencimiento), 0) AS dias_mora,
    COALESCE((
        SELECT SUM(a.monto_aplicado)
        FROM fin.ap_pago_aplicacion a
        WHERE a.documento_id = d.id
    ), 0)::numeric(18,2) AS monto_pagado
FROM fin.ap_documento d
JOIN public.proveedor p
  ON p.id = d.proveedor_id;

COMMIT;
