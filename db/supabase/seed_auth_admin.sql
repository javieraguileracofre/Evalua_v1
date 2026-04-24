-- =============================================================================
-- Usuario administrador desde Supabase → SQL Editor (sin Python).
-- Requiere extensión pgcrypto (ya la crea 000_platform_registry / bootstrap).
-- La contraseña se guarda con crypt(..., 'bf') — misma familia que bcrypt en la app.
-- =============================================================================
-- 1) Cambie EMAIL, NOMBRE y la cadena entre comillas en crypt('...', ...) (mín. 10 caracteres).
-- 2) Run en el proyecto correcto (misma base donde corre la app).
-- =============================================================================

CREATE EXTENSION IF NOT EXISTS pgcrypto;

INSERT INTO public.auth_roles (codigo, nombre, descripcion) VALUES
    ('ADMIN', 'Administrador', 'Acceso completo a la suite ERP.'),
    ('OPERACIONES', 'Operaciones', 'Ventas, taller, inventario y maestros operativos.'),
    ('FINANZAS', 'Finanzas', 'Cobranza, cuentas por pagar y contabilidad.'),
    ('CONSULTA', 'Consulta', 'Rol base para políticas de solo lectura (evolución futura).')
ON CONFLICT (codigo) DO NOTHING;

-- Usuario: ajuste email, nombre visible y contraseña en claro (solo en este editor; no suba esto a Git con datos reales).
WITH datos AS (
    SELECT
        lower('javier.aguilera@evaluasoluciones.cl'::text) AS email,
        'Javier Aguilera'::text AS nombre_completo,
        crypt('Evalua1234##', gen_salt('bf')) AS password_hash
),
ins AS (
    INSERT INTO public.auth_usuarios (email, password_hash, nombre_completo, activo)
    SELECT email, password_hash, nombre_completo, true FROM datos
    ON CONFLICT (email) DO UPDATE SET
        password_hash = EXCLUDED.password_hash,
        nombre_completo = EXCLUDED.nombre_completo,
        activo = true,
        updated_at = now()
    RETURNING id
)
INSERT INTO public.auth_usuario_rol (usuario_id, rol_id)
SELECT ins.id, r.id
FROM ins
CROSS JOIN public.auth_roles r
WHERE r.codigo = 'ADMIN'
ON CONFLICT (usuario_id, rol_id) DO NOTHING;

-- Comprobar (sin mostrar hash completo):
-- SELECT id, email, activo, left(password_hash, 7) AS hash_prefijo FROM public.auth_usuarios WHERE email = lower('javier.aguilera@evaluasoluciones.cl');
-- SELECT u.email, r.codigo FROM public.auth_usuarios u JOIN public.auth_usuario_rol ur ON ur.usuario_id = u.id JOIN public.auth_roles r ON r.id = ur.rol_id WHERE u.email = lower('javier.aguilera@evaluasoluciones.cl');
