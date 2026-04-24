-- db/psql/096_grant_evalua_user_ap_fk.sql
-- Base: EVALUA_V1_DB  |  Rol app: evalua_user (sin comillas en PG = nombre en minúsculas).
-- Ejecutar como superusuario (p. ej. postgres), NO hace falta la clave de evalua_user:
--   psql -h localhost -p 5432 -U postgres -d EVALUA_V1_DB -f db/psql/096_grant_evalua_user_ap_fk.sql
-- Corrige: permiso denegado a la tabla proveedor al recrear fin.ap_documento (FK).

BEGIN;

GRANT USAGE ON SCHEMA public TO evalua_user;
GRANT USAGE ON SCHEMA fin TO evalua_user;

-- Necesario para CREATE TABLE ... REFERENCES public.proveedor(id)
GRANT REFERENCES ON TABLE public.proveedor TO evalua_user;

-- fin.ap_pago.banco_proveedor_id → public.proveedor_banco
GRANT REFERENCES ON TABLE public.proveedor_banco TO evalua_user;

-- fin.ap_documento_detalle → fin.categoria_gasto / fin.centro_costo
GRANT REFERENCES ON TABLE fin.categoria_gasto TO evalua_user;
GRANT REFERENCES ON TABLE fin.centro_costo TO evalua_user;

-- Si al arrancar aún falla create_all por “schema fin” u ownership, revisar con el DBA:
--   GRANT CREATE ON SCHEMA fin TO evalua_user;
--   o crear tablas AP una vez con rol postgres y luego ALTER ... OWNER TO evalua_user;

COMMIT;
