# Recuperación de contraseña

Flujo para usuarios que olvidaron su clave: código de un solo uso enviado por correo, con vigencia de **5 minutos**.

## Flujo

1. En `/login`, el usuario elige **Olvidé mi contraseña**.
2. Ingresa el correo de la cuenta.
3. El sistema responde siempre el mismo mensaje genérico:
   *«Si el correo está registrado, recibirás un código de recuperación.»*
   No se revela si el correo existe. Si la cuenta está activa, se envía un código de 8 dígitos.
4. El usuario pega el código. Si es válido y no expiró, puede definir una nueva contraseña (dos veces).
5. Tras el cambio, el código queda invalidado y puede iniciar sesión con la clave nueva.

Pantallas HTML: `/login/recuperar` → `/login/recuperar/codigo` → `/login/recuperar/clave` → `/login/recuperar/exito`.

## API JSON (misma lógica)

Las rutas son públicas (sin sesión) y no enumeran cuentas.

| Método | Ruta | Cuerpo |
|--------|------|--------|
| POST | `/auth/forgot-password` | `{ "email": "..." }` |
| POST | `/auth/verify-reset-code` | `{ "email": "...", "code": "12345678" }` |
| POST | `/auth/reset-password` | `{ "email": "...", "code": "...", "new_password": "...", "confirm_password": "..." }` |

`forgot-password` responde **siempre HTTP 200** con un mensaje genérico (o de límite de solicitudes).

## Variables de entorno (SMTP)

Reutiliza el servicio de correo existente (`services/comunicaciones/email_service.py`):

```env
EVALUA_SMTP_HOST=mail.evaluasoluciones.cl
EVALUA_SMTP_PORT=465
EVALUA_SMTP_USER=notificaciones@su-dominio.cl
EVALUA_SMTP_PASSWORD=********
EVALUA_MAIL_FROM_NAME=Evalua ERP
EVALUA_MAIL_REPLY_TO=soporte@su-dominio.cl
```

Sin `EVALUA_SMTP_PASSWORD` el envío falla de forma silenciosa para el usuario final (sigue el mensaje genérico). El código generado se invalida si el correo no pudo enviarse.

Las cuentas SMTP administrables (una casilla por tipo de gestión) se documentan en `docs/cuentas_correo.md`. Recuperación de contraseña usa el canal `RECUPERACION_CONTRASENA` si está asignado.

`SECRET_KEY` se usa como pimienta HMAC del código. En producción debe ser aleatoria y de al menos 32 caracteres.

## Migración

El proyecto no usa Alembic: los parches viven en `db/psql/` y se aplican al arrancar (PostgreSQL).

- Archivo: `db/psql/132_auth_password_reset_codes.sql`
- Arranque: `ensure_auth_password_reset_codes` en `db/startup_schema.py` (también corre `Base.metadata.create_all` en desarrollo).

Aplicación manual (SQL Editor de Supabase o `psql`):

```sql
-- pegar el contenido de db/psql/132_auth_password_reset_codes.sql
```

## Política de contraseña

Se reutiliza y refuerza la validación de `crud.auth.usuarios.validar_politica_password`:

- mínimo 10 caracteres
- al menos una letra y un número
- hash bcrypt (`hash_password` / `establecer_password`)

## Seguridad

- El código **nunca** se guarda en claro: HMAC-SHA256 con `SECRET_KEY`.
- Un solo uso; un código nuevo invalida los anteriores del mismo usuario.
- Vence exactamente a los 5 minutos (`expires_at > now`; al cumplirse los 5 minutos ya no es válido).
- Máximo 5 intentos fallidos por código, luego se invalida.
- Límite de solicitudes: 3 por correo y 10 por IP en 15 minutos.
- Mensajes no enumerativos (existencia de cuenta, código inválido vs expirado).
- No se registran códigos ni contraseñas en logs.
- Correos de dummy (cuentas inexistentes o inactivas) no se envían; sí cuentan para el rate limit.

## Tests

Desde la raíz del repositorio:

```bash
python -m pytest tests/test_password_reset.py tests/test_module_access.py tests/test_security_startup_tenant_rbac.py
```

La suite completa:

```bash
python -m pytest
```
