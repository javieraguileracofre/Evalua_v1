# Rotación de secretos y endurecimiento operativo

Este documento cubre acciones que el código no puede completar por sí solo.
No copie secretos reales a este archivo ni al repositorio.

## 1. Rotar SECRET_KEY

1. Generar una clave nueva: `openssl rand -hex 32`
2. Actualizar `SECRET_KEY` en `.env` local y en el panel de producción (Render).
3. Reiniciar la aplicación. Las cookies de sesión anteriores quedan inválidas (esperado).
4. Pedir a los usuarios que vuelvan a iniciar sesión.

## 2. Rotar SMTP

1. Cambiar la contraseña de la cuenta SMTP en el proveedor de correo.
2. Actualizar `EVALUA_SMTP_PASSWORD` y, si aplica, `MAIL_CREDENTIALS_KEY`.
3. En Seguridad → Cuentas de correo, volver a guardar cada cuenta cifrada.
4. Enviar un correo de prueba a un buzón controlado.

## 3. Rotar PostgreSQL / Supabase

1. Resetear la contraseña en el panel de Supabase o del Postgres de Render.
2. Actualizar `DATABASE_URL`, `PLATFORM_DATABASE_URL` y, si existe, `ADMIN_POSTGRES_URL`.
3. Si hay fila en `public.tenants.db_password`, sincronizarla (script documentado en el repo).
4. Verificar arranque y `/health`.

## 4. Bootstrap de administrador (sin seed reutilizable)

- Preferido: `python tools/create_admin_user.py --email admin@empresa.cl --password "..." --nombre "Administrador"`
- Bootstrap Supabase: `EVALUA_BOOTSTRAP_ADMIN_EMAIL` + `EVALUA_BOOTSTRAP_ADMIN_PASSWORD`
- SQL Editor: `SET evalua.admin_bootstrap_*` **solo en la sesión**, luego `db/supabase/seed_auth_admin.sql`

Nunca versionar hashes ni contraseñas de admin.

## 5. Sacar `.env` de OneDrive / sync

1. Mover el proyecto o al menos `.env` fuera de carpetas sincronizadas.
2. Confirmar que `.env` está en `.gitignore`.
3. Si OneDrive ya subió `.env`, considerarlo comprometido y rotar todos los secretos de las secciones 1–3.

## 6. Historial Git si hubo secretos

Si alguna vez se commitió `.env`, seeds con `Evalua1234##` o claves SMTP:

1. Rotar esos secretos de inmediato (no basta con borrar el archivo en HEAD).
2. Revisar `git log --all -- db/supabase/seed_auth_admin.sql tools/supabase_bootstrap.py`
3. Si el remoto es privado y el secreto ya rotó, documentar el incidente. `git filter-repo` es decisión del owner (reescribe historia).

## 7. Producción (Render / Docker)

- `APP_ENV=production`
- `APP_DEBUG=false`
- `AUTH_COOKIE_SECURE=true`
- `TRUST_X_FORWARDED_FOR=true` solo detrás del proxy de Render. Si la variable no está definida, la aplicación usa la IP del socket.
- `ALLOWED_HOSTS` con el FQDN real (además de `*.onrender.com` si aplica). El comodín de Starlette es `*.dominio`, no `.dominio`.
- `SECRET_KEY` generado, no el valor de desarrollo
- Imagen Docker corre como usuario no root; no copia `.env`

## 8. Auditoría de dependencias

```
python -m pip install pip-audit
python -m pip_audit -r requirements.txt
```

Ejecutar en CI o antes de cada release. Esta fase actualiza `python-multipart>=0.0.18` y `Jinja2>=3.1.6`.

## 9. CSP estricta (paso siguiente)

La CSP actual permite `'unsafe-inline'` y CDN (Bootstrap) para no romper la UI.

Pasos para CSP estricta:

1. Inventariar scripts y estilos inline en `templates/` y `static/js/`.
2. Servir Bootstrap/iconos desde `/static` (sin CDN).
3. Emitir nonce por request en `SecurityHeadersMiddleware` y pasarlo a las plantillas.
4. Quitar `'unsafe-inline'` de `script-src` y `style-src`.
5. Activar `Content-Security-Policy-Report-Only` una semana y revisar violaciones.
6. Promover la política estricta a enforce.

## 10. WAF / proxy

Si hay reverse proxy, validar que:

- No se confíe `X-Forwarded-For` salvo `TRUST_X_FORWARDED_FOR=true` en el origen del proxy.
- TLS termine en el proxy y `AUTH_COOKIE_SECURE=true`.
- Host header coincida con `ALLOWED_HOSTS`.
