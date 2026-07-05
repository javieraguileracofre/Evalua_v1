-- 128_auth_submodulos_nav.sql
-- Amplía module_key para sub-módulos de navegación (leasing, crédito).

ALTER TABLE auth_usuario_modulo_visible
    ALTER COLUMN module_key TYPE VARCHAR(64);

COMMENT ON COLUMN auth_usuario_modulo_visible.module_key IS
    'Clave de área (COMERCIAL) o sub-módulo (LEASING_FINANCIERO, LEASING_OPERATIVO, CREDITO_RIESGO).';
