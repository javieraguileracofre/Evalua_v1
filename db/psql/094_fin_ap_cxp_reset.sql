-- db/psql/094_fin_ap_cxp_reset.sql
-- ============================================================
-- RESETEO CUENTAS POR PAGAR (AP): elimina datos y tablas AP en fin.
-- Ejecutar contra la base del tenant (psql o tools/apply_fin_sql_file.py).
-- Después: reiniciar la app para que SQLAlchemy create_all recree las tablas,
--   o ejecutar Alembic si su proyecto migra así.
-- ADVERTENCIA: borra todos los documentos AP, líneas, impuestos, pagos y aplicaciones.
-- ============================================================

BEGIN;

DROP VIEW IF EXISTS fin.vw_cxp_resumen CASCADE;

DROP TABLE IF EXISTS fin.ap_pago_aplicacion CASCADE;
DROP TABLE IF EXISTS fin.ap_pago CASCADE;
DROP TABLE IF EXISTS fin.ap_documento_detalle CASCADE;
DROP TABLE IF EXISTS fin.ap_documento_impuesto CASCADE;
DROP TABLE IF EXISTS fin.ap_documento CASCADE;

COMMIT;

-- Después de reiniciar la app (create_all recrea tablas AP), ejecutar:
--   db/psql/097_fin_ap_post_create_all.sql
-- (093 + 095 + 088 en un solo archivo; no mezclar con este script en el mismo pegado).
