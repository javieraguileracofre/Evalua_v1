-- 133_mail_accounts.sql
-- Cuentas de correo saliente, canales de gestión y auditoría de validación.
-- Idempotente.

CREATE TABLE IF NOT EXISTS mail_accounts (
    id                   BIGSERIAL PRIMARY KEY,
    nombre               VARCHAR(120) NOT NULL,
    from_email           VARCHAR(254) NOT NULL,
    from_name            VARCHAR(160) NOT NULL DEFAULT '',
    provider             VARCHAR(32) NOT NULL DEFAULT 'SMTP',
    host                 VARCHAR(255) NOT NULL,
    port                 INTEGER NOT NULL DEFAULT 465,
    security             VARCHAR(16) NOT NULL DEFAULT 'SSL',
    username             VARCHAR(254) NOT NULL,
    secret_encrypted     TEXT NOT NULL DEFAULT '',
    status               VARCHAR(32) NOT NULL DEFAULT 'pendiente_validacion',
    last_ok_at           TIMESTAMP WITHOUT TIME ZONE NULL,
    last_error           VARCHAR(500) NULL,
    created_by_id        BIGINT NULL REFERENCES auth_usuarios (id) ON DELETE SET NULL,
    created_at           TIMESTAMP WITHOUT TIME ZONE NOT NULL DEFAULT NOW(),
    updated_at           TIMESTAMP WITHOUT TIME ZONE NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS ix_mail_accounts_status ON mail_accounts (status);
CREATE INDEX IF NOT EXISTS ix_mail_accounts_from_email ON mail_accounts (from_email);

CREATE TABLE IF NOT EXISTS mail_channels (
    codigo               VARCHAR(40) PRIMARY KEY,
    nombre               VARCHAR(120) NOT NULL,
    descripcion          TEXT NULL,
    cuenta_principal_id  BIGINT NULL REFERENCES mail_accounts (id) ON DELETE SET NULL,
    cuenta_fallback_id   BIGINT NULL REFERENCES mail_accounts (id) ON DELETE SET NULL,
    updated_at           TIMESTAMP WITHOUT TIME ZONE NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS mail_validations (
    id                   BIGSERIAL PRIMARY KEY,
    account_id           BIGINT NOT NULL REFERENCES mail_accounts (id) ON DELETE CASCADE,
    kind                 VARCHAR(20) NOT NULL DEFAULT 'CONNECT',
    ok                   BOOLEAN NOT NULL DEFAULT FALSE,
    error_code           VARCHAR(40) NULL,
    error_message        VARCHAR(500) NULL,
    latency_ms           INTEGER NULL,
    to_email             VARCHAR(254) NULL,
    created_at           TIMESTAMP WITHOUT TIME ZONE NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS ix_mail_validations_account
    ON mail_validations (account_id, created_at DESC);

INSERT INTO mail_channels (codigo, nombre, descripcion) VALUES
    ('RECUPERACION_CONTRASENA', 'Recuperación de contraseña', 'Códigos de restablecimiento de clave del portal.'),
    ('COBRANZA', 'Cobranza', 'Recordatorios y gestiones de cobranza.'),
    ('POSTVENTA', 'Postventa', 'Comunicaciones de casos CRM / postventa.'),
    ('COMERCIAL', 'Comercial', 'Cotizaciones, aceptación de crédito y avisos comerciales.'),
    ('NOTIFICACIONES', 'Notificaciones', 'Avisos administrativos generales.'),
    ('SOPORTE', 'Soporte / TI', 'Comunicaciones de soporte técnico.'),
    ('SISTEMA', 'Sistema', 'Mensajes internos del ERP.')
ON CONFLICT (codigo) DO NOTHING;
