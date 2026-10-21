-- =============================================================================
-- Usuario administrador desde Supabase → SQL Editor (sin Python).
-- Requiere extensión pgcrypto (ya la crea 000_platform_registry / bootstrap).
-- =============================================================================
-- NO commitear contraseñas reales. En el editor, ejecute ANTES:
--   SET evalua.admin_bootstrap_email = 'admin@empresa.cl';
--   SET evalua.admin_bootstrap_name = 'Administrador';
--   SET evalua.admin_bootstrap_password = 'una-clave-temporal-fuerte';
-- Luego ejecute este script y rote la clave al primer ingreso.
-- =============================================================================

CREATE EXTENSION IF NOT EXISTS pgcrypto;

INSERT INTO public.auth_roles (codigo, nombre, descripcion) VALUES
    ('ADMIN', 'Administrador', 'Acceso completo a la suite ERP.'),
    ('OPERACIONES', 'Operaciones', 'Ventas, taller, inventario y maestros operativos.'),
    ('FINANZAS', 'Finanzas', 'Cobranza, cuentas por pagar y contabilidad.'),
    ('RRHH', 'Recursos humanos', 'Nómina, contratos laborales y remuneraciones.'),
    ('CONSULTA', 'Consulta', 'Rol base para políticas de solo lectura (evolución futura).')
ON CONFLICT (codigo) DO NOTHING;

WITH datos AS (
    SELECT
        lower(current_setting('evalua.admin_bootstrap_email')::text) AS email,
        current_setting('evalua.admin_bootstrap_name')::text AS nombre_completo,
        crypt(current_setting('evalua.admin_bootstrap_password'), gen_salt('bf')) AS password_hash
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
