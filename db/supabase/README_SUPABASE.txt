Supabase — tablas vacías hasta que cargues el esquema (y la clave del panel)
============================================================================

Proyecto (API): https://qtrqsdabrpxitmqvqdko.supabase.co
Referencia app / scripts: pooler transacción *.pooler.supabase.com puerto 6543, usuario postgres.qtrqsdabrpxitmqvqdko (copiar URI exacta del panel Connect). Directo db.* :5432 solo para casos puntuales del panel.

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
      db/supabase/bootstrap_public_schema.sql
   Copia TODO el contenido, pégalo en el editor y pulsa RUN.
3) Table Editor → schema public → tenants, seguridad_roles, etc.; en schema fin → plan_cuenta (plan base ya sembrado).

Luego, para fila tenant + tablas SQLAlchemy + usuario maestro desde tu máquina:

4) Dashboard → Settings → Database → copia la contraseña actual (o resetéala).
5) En la raíz del repo, .env con DATABASE_URL, PLATFORM_DATABASE_URL y ADMIN_POSTGRES_URL (misma URI pooler :6543 del panel; ?sslmode=require).
   Parte de .env.supabase.template.
6) En la raíz del repositorio:
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

──────────────────────────────────────────────────────────────────────────────
Plan de cuentas vacío (fin.plan_cuenta sin filas o error al insertar)
──────────────────────────────────────────────────────────────────────────────
En SQL Editor pegue y ejecute TODO el archivo:
  db/supabase/seed_plan_cuentas_supabase.sql
(es idempotente; corrige DEFAULT en created_at/updated_at si la tabla la creó la app).

──────────────────────────────────────────────────────────────────────────────
Alta solo en Supabase (SQL Editor), sin ejecutar Python en Render
──────────────────────────────────────────────────────────────────────────────
1) Abre el archivo local:  db/supabase/seed_auth_admin.sql
2) Edita en el propio editor de Supabase el correo, nombre y la contraseña dentro de crypt('...', gen_salt('bf')).
3) Run. El hash es compatible con el login de la app (bcrypt vía pgcrypto).

Leasing financiero (área comercial) — producción / Supabase
------------------------------------------------------------
Tras tener la tabla public.clientes (bootstrap + app o migraciones), en SQL Editor ejecute
TODO el archivo (idempotente):

  db/psql/100_comercial_leasing_financiero.sql

Crea comercial_lf_cotizaciones, comercial_lf_proyeccion_linea, cuentas 113701/210701/410701 y
reglas en fin.config_contable* para LEASING_FIN_*. La app también intenta aplicar este parche
al arrancar si falta la config COMERCIAL/LEASING_FIN.

Si algo falla
-------------
- "password authentication failed": la clave no es la del proyecto en la nube; reset en Database.
- "debe ser dueño de la tabla tenants": conectas con un usuario sin permisos; usa postgres en URL o SQL Editor.
- Si cambias db/psql/000, 001, 002 o 089_fin_plan_cuentas.sql, actualiza también bootstrap_public_schema.sql para mantenerlos alineados.
