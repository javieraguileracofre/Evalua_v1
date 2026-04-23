Supabase — carga inicial vacía + usuario maestro
================================================

Proyecto API: https://qtrqsdabrpxitmqvqdko.supabase.co
Host PostgreSQL (directo): db.qtrqsdabrpxitmqvqdko.supabase.co  puerto 5432

1) En Supabase Dashboard → Settings → Database, copia la contraseña del usuario postgres.

2) Pon en .env la conexión (una de estas opciones):
   - DATABASE_URL / PLATFORM_DATABASE_URL, o
   - DB_HOST, DB_USER, DB_PASSWORD, DB_NAME (+ DB_SSLMODE=require en la nube), o
   - al menos DB_PASSWORD (usuario postgres por defecto) y SUPABASE_PROJECT_REF si no hay DB_HOST.

   Desde la raíz de Evalua_V1:

   python tools/supabase_bootstrap.py

   (Opcional: --db-password "..." si no quieres guardar la clave en .env.)

   Esto:
   - Ejecuta db/psql/000_platform_registry.sql, 001_tenant_base.sql, 002_tenant_security.sql
   - Inserta/actualiza la fila en public.tenants para el tenant "athletic" apuntando a esta instancia
   - Crea todas las tablas SQLAlchemy (create_all) y roles auth por defecto
   - Crea el usuario maestro:
       email: javier.aguilera@evaluasoluciones.cl
       password: Evalua1234##   (cámbiala en cuanto puedas)

3) Si aún no tienes .env, copia .env.supabase.template a .env y ajusta las mismas credenciales; arranca la app.

Nota: si el script falla por permisos o SQL, revisa el mensaje; puedes ejecutar los .sql manualmente en SQL Editor y luego solo la parte Python (ver --help).
