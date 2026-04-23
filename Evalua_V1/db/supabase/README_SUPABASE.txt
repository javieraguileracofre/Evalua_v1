Supabase — tablas vacías hasta que cargues el esquema (y la clave del panel)
============================================================================

Proyecto (API): https://qtrqsdabrpxitmqvqdko.supabase.co
Host PostgreSQL:  db.qtrqsdabrpxitmqvqdko.supabase.co  puerto 5432  base postgres  usuario postgres

Aclaración importante
---------------------
- Las tablas en el Table Editor están vacías hasta que ejecutes SQL o el bootstrap: eso es normal.
- El proyecto Supabase SIEMPRE tiene una "Database password" para el rol postgres desde que creas
  el proyecto (o tras resetearla). No "aparece" al cargar datos: la defines o reseteas en el panel.
- Si hiciste ALTER ROLE postgres ... en pgAdmin contra localhost, eso NO cambia la contraseña
  en la nube. En la nube usa la clave del panel o resetéala ahí.

──────────────────────────────────────────────────────────────────────────────
OPCIÓN A — Ver tablas YA sin pelear con la clave en tu PC (recomendada primero)
──────────────────────────────────────────────────────────────────────────────
1) Supabase → SQL Editor → New query.
2) Abre el archivo local:
      Evalua_V1/db/supabase/bootstrap_public_schema.sql
   Copia TODO el contenido, pégalo en el editor y pulsa RUN.
3) Table Editor → schema public → deberías ver tenants, seguridad_roles, etc.

Luego, para fila tenant + tablas SQLAlchemy + usuario maestro desde tu máquina:

4) Dashboard → Settings → Database → copia la contraseña actual (o resetéala).
5) En Evalua_V1, .env con DATABASE_URL y PLATFORM_DATABASE_URL (usuario postgres y esa clave),
   host db.qtrqsdabrpxitmqvqdko.supabase.co, ?sslmode=require
   (puedes partir de .env.supabase.template).
6) En la raíz de Evalua_V1:
      python tools/supabase_bootstrap.py --skip-sql

──────────────────────────────────────────────────────────────────────────────
OPCIÓN B — Todo desde Python (sin pegar SQL en el panel)
──────────────────────────────────────────────────────────────────────────────
Necesitas la contraseña del panel para el usuario postgres en Supabase.

  python tools/supabase_bootstrap.py --db-password "CLAVE_DEL_PANEL"

O en .env (solo si NO tienes DATABASE_URL todavía):

  SUPABASE_POSTGRES_PASSWORD=CLAVE_DEL_PANEL
  SUPABASE_PROJECT_REF=qtrqsdabrpxitmqvqdko

  python tools/supabase_bootstrap.py

Usuario maestro tras bootstrap exitoso
---------------------------------------
  email:    javier.aguilera@evaluasoluciones.cl
  password: Evalua1234##   (cámbiala en cuanto puedas)

Si algo falla
-------------
- "password authentication failed": la clave no es la del proyecto en la nube; reset en Database.
- "debe ser dueño de la tabla tenants": conectas con un usuario sin permisos; usa postgres en URL o SQL Editor.
- Si cambias db/psql/000, 001 o 002, actualiza también bootstrap_public_schema.sql para mantenerlos alineados.
