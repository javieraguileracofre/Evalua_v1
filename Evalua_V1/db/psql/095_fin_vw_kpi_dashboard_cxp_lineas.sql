-- db/psql/095_fin_vw_kpi_dashboard_cxp_lineas.sql
-- Vista KPI finanzas: montos AP desde líneas (neto+iva) + impuestos, no desde cabecera.
-- Pagos del mes: usa fin.ap_pago.monto_total (columna real del modelo).
-- Aplicar tras 094 reset o si la vista 70 sigue usando SUM(d.total).

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
  -- Sin depender de fin.gasto (puede no existir en el tenant); KPI gasto del mes = 0 hasta tener tabla.
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
