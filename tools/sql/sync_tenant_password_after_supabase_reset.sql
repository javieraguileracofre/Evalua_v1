-- Ejecutar en Supabase → SQL Editor después de resetear la contraseña del proyecto
-- (Project Settings → Database → Reset database password).
--
-- La app arma la conexión del tenant con public.tenants (db_user, db_password, …).
-- Si solo actualizas Render pero no esta fila, verás: password authentication failed for user "postgres".
--
-- 1) Copia la nueva contraseña del panel de Supabase (no la subas a Git).
-- 2) Sustituye TENANT_CODE y la contraseña en comillas simples (si contiene ', duplícala).
-- 3) Actualiza también DATABASE_URL / PLATFORM_DATABASE_URL en Render con la URI nueva.

UPDATE public.tenants
SET db_password = 'PEGAR_AQUI_LA_NUEVA_CLAVE'
WHERE tenant_code = 'athletic';

-- Verificar (no muestra la clave completa en logs si evitas SELECT * en producción):
-- SELECT tenant_code, db_user, length(db_password) AS pwd_len FROM public.tenants WHERE tenant_code = 'athletic';
