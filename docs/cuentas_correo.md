# Cuentas de correo saliente

El ERP puede usar **varias casillas SMTP** según el tipo de gestión (cobranza, recuperación de contraseña, comercial, etc.). Un administrador las configura en **menú de usuario → Cuentas de correo**.

## Cómo se envían los correos

1. El flujo indica un **canal** (`RECUPERACION_CONTRASENA`, `COBRANZA`, `POSTVENTA`, `COMERCIAL`, …).
2. Si el canal tiene una cuenta **activa** asignada, se usa esa casilla.
3. Si hay cuenta alternativa y la principal no está usable, se usa el fallback.
4. Si el canal no tiene asignación, se usa el SMTP legado de `.env` (`EVALUA_SMTP_*`) para no romper cobranza existente.
5. Si hay asignación pero la cuenta está inactiva o no validada, el envío falla con un error claro (no se usa el SMTP legado).

## Configurar una cuenta SMTP

1. Entre con un usuario **ADMIN**.
2. Abra **Cuentas de correo** → **Nueva cuenta**.
3. Complete nombre, remitente, proveedor, host, puerto y seguridad:
   - **SSL** en puerto 465, o **STARTTLS** en 587.
   - Gmail / Microsoft 365 rellenan host y puerto si los deja vacíos. Gmail requiere contraseña de aplicación.
4. La contraseña se cifra en la base (`MAIL_CREDENTIALS_KEY` o, si falta, una derivación de `SECRET_KEY`). **Nunca se vuelve a mostrar.**
5. Pulse **Validar** (abre conexión y autentica; **no envía correo**).
6. Opcional: **Enviar prueba** a un destinatario que usted controle.
7. **Activar** la cuenta (exige una validación o prueba exitosa previa).
8. En **Tipos de gestión**, asigne la cuenta principal (y opcionalmente una alternativa).

## Asignaciones recomendadas

| Canal | Uso |
|---|---|
| `RECUPERACION_CONTRASENA` | Códigos de olvido de clave |
| `COBRANZA` | Recordatorios de cobranza |
| `POSTVENTA` | Casos CRM |
| `COMERCIAL` | Aceptación de leasing / avisos comerciales |
| `NOTIFICACIONES` / `SOPORTE` / `SISTEMA` | Reserva para avisos internos |

## Variables de entorno

```env
EVALUA_SMTP_HOST=mail.evaluasoluciones.cl
EVALUA_SMTP_PORT=465
EVALUA_SMTP_USER=...
EVALUA_SMTP_PASSWORD=...
EVALUA_MAIL_FROM_NAME=Evalua ERP
MAIL_CREDENTIALS_KEY=  # openssl rand -hex 32
```

`MAIL_CREDENTIALS_KEY` protege las contraseñas guardadas en el módulo. Si la rota, vuelva a cargar la contraseña de cada cuenta (no se pueden descifrar las anteriores).

## Troubleshooting de conexión

| Síntoma | Qué revisar |
|---|---|
| Tiempo de espera / WinError 10060 | Firewall, antivirus o ISP bloqueando 465/587; host inalcanzable desde este PC |
| Autenticación rechazada | Usuario/clave; en Gmail use contraseña de aplicación |
| Error TLS/SSL | Pruebe el otro modo (SSL 465 vs STARTTLS 587) |
| Host no se resuelve | Nombre SMTP mal escrito |
| Cuenta inactiva | Valide y active; el canal no usará una cuenta en error |
| El usuario ve éxito genérico en recuperación | El OTP se genera igual; si SMTP falla el código se invalida. Revise `logs/uvicorn.err.log` (`evalua.auth.reset`) |

La validación básica **no envía** correo. El envío de prueba sí lo hace, de forma explícita.

## Seguridad

- Secretos cifrados (Fernet); el panel solo permite reemplazarlos.
- Auditoría en `email_log` (canal, cuenta, destinatario, estado, error sanitizado). No se guardan códigos de recuperación ni contraseñas.
- Solo rol **ADMIN**.

## Migración

`db/psql/133_mail_accounts.sql` (también al arrancar vía `ensure_mail_accounts_schema`).
