-- 126_auth_usuario_modulos_visibles.sql
-- Módulos visibles en el menú lateral por usuario (Evalúa ERP).

CREATE TABLE IF NOT EXISTS auth_usuario_modulo_visible (
    usuario_id   BIGINT NOT NULL REFERENCES auth_usuarios (id) ON DELETE CASCADE,
    module_key   VARCHAR(32) NOT NULL,
    assigned_by_id BIGINT REFERENCES auth_usuarios (id) ON DELETE SET NULL,
    created_at   TIMESTAMP WITHOUT TIME ZONE NOT NULL DEFAULT NOW(),
    PRIMARY KEY (usuario_id, module_key)
);

CREATE INDEX IF NOT EXISTS idx_auth_usuario_modulo_visible_user
    ON auth_usuario_modulo_visible (usuario_id);
