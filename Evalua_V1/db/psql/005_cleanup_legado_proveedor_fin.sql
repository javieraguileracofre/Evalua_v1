-- db/psql/005_cleanup_legado_proveedor_fin.sql
-- -*- coding: utf-8 -*-

BEGIN;

-- Solo si ya migraste y validaste
DROP TABLE IF EXISTS fin.proveedor_banco CASCADE;
DROP TABLE IF EXISTS fin.proveedor_contacto CASCADE;
DROP TABLE IF EXISTS fin.proveedor_direccion CASCADE;
DROP TABLE IF EXISTS fin.proveedor CASCADE;

COMMIT;