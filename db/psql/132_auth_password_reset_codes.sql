-- 132_auth_password_reset_codes.sql
-- Recuperación de contraseña: códigos de un solo uso (hash HMAC, vencen a los 5 minutos).
-- Idempotente.

CREATE TABLE IF NOT EXISTS auth_password_reset_codes (
    id               BIGSERIAL PRIMARY KEY,
    user_id          BIGINT REFERENCES auth_usuarios (id) ON DELETE CASCADE,
    email_hmac       VARCHAR(64) NOT NULL,
    code_hash        VARCHAR(64) NOT NULL,
    expires_at       TIMESTAMP WITHOUT TIME ZONE NOT NULL,
    used_at          TIMESTAMP WITHOUT TIME ZONE NULL,
    invalidated_at   TIMESTAMP WITHOUT TIME ZONE NULL,
    failed_attempts  INTEGER NOT NULL DEFAULT 0,
    request_ip_hmac  VARCHAR(64) NULL,
    created_at       TIMESTAMP WITHOUT TIME ZONE NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS ix_auth_pwd_reset_email_hmac
    ON auth_password_reset_codes (email_hmac, created_at DESC);

CREATE INDEX IF NOT EXISTS ix_auth_pwd_reset_user_id
    ON auth_password_reset_codes (user_id);

CREATE INDEX IF NOT EXISTS ix_auth_pwd_reset_ip_hmac
    ON auth_password_reset_codes (request_ip_hmac, created_at DESC);

CREATE INDEX IF NOT EXISTS ix_auth_pwd_reset_expires
    ON auth_password_reset_codes (expires_at);

COMMENT ON TABLE auth_password_reset_codes IS
    'Códigos de recuperación: se guarda HMAC del código, nunca el valor en claro.';
COMMENT ON COLUMN auth_password_reset_codes.email_hmac IS
    'HMAC-SHA256 del correo normalizado; permite limitar abuso sin guardar el email en claro.';
COMMENT ON COLUMN auth_password_reset_codes.code_hash IS
    'HMAC-SHA256 del código (con SECRET_KEY). No es reversible.';
