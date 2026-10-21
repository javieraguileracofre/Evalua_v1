-- 147_auth_login_attempts.sql
-- Cupo de login compartido entre procesos. Solo HMAC, nunca correo ni IP en claro.
-- Idempotente.

CREATE TABLE IF NOT EXISTS auth_login_attempts (
    id           BIGSERIAL PRIMARY KEY,
    email_hmac   VARCHAR(64) NOT NULL,
    ip_hmac      VARCHAR(64) NULL,
    created_at   TIMESTAMP WITHOUT TIME ZONE NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS ix_auth_login_attempts_email
    ON auth_login_attempts (email_hmac, created_at DESC);

CREATE INDEX IF NOT EXISTS ix_auth_login_attempts_ip
    ON auth_login_attempts (ip_hmac, created_at DESC);

COMMENT ON TABLE auth_login_attempts IS
    'Fallos de login recientes para el cupo. HMAC del correo y de la IP; no guarda PII.';
