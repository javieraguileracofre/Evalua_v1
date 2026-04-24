BEGIN;

CREATE SCHEMA IF NOT EXISTS fin;

-- KPI Dashboard Finanzas
-- Asume:
--  fin.ap_documento: (id, total, saldo_pendiente, fecha_vencimiento, estado)
--  fin.ap_pago: (id, monto, fecha_pago)
--  fin.gasto: (id, total, fecha, estado)
--
-- Si tus nombres difieren, me pegas el DDL real y lo ajusto 1:1.

CREATE OR REPLACE VIEW fin.vw_kpi_dashboard_fin AS
WITH
ap AS (
  SELECT
    COUNT(*)::bigint AS docs_total,
    COALESCE(SUM(d.total),0)::numeric(18,2) AS monto_total,
    COALESCE(SUM(d.saldo_pendiente),0)::numeric(18,2) AS saldo_pendiente,
    COALESCE(SUM(CASE WHEN d.fecha_vencimiento < CURRENT_DATE AND d.saldo_pendiente > 0 THEN d.saldo_pendiente ELSE 0 END),0)::numeric(18,2) AS saldo_vencido
  FROM fin.ap_documento d
  WHERE COALESCE(d.estado,'') <> 'ANULADO'
),
pagos_mes AS (
  SELECT
    COALESCE(SUM(p.monto),0)::numeric(18,2) AS pagado_mes
  FROM fin.ap_pago p
  WHERE date_trunc('month', p.fecha_pago) = date_trunc('month', CURRENT_DATE)
),
gastos_mes AS (
  SELECT
    COALESCE(SUM(g.total),0)::numeric(18,2) AS gasto_mes
  FROM fin.gasto g
  WHERE COALESCE(g.estado,'') <> 'ANULADO'
    AND date_trunc('month', g.fecha) = date_trunc('month', CURRENT_DATE)
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