-- 134_auth_usuario_session_version.sql
-- Versión de sesión por usuario: incrementa al desactivar, cambiar roles o clave.

ALTER TABLE public.auth_usuarios
    ADD COLUMN IF NOT EXISTS session_version INTEGER NOT NULL DEFAULT 1;

COMMENT ON COLUMN public.auth_usuarios.session_version IS
    'Incrementar para invalidar cookies de sesión firmadas anteriores.';
