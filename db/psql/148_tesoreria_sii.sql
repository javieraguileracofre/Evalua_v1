-- 148_tesoreria_sii.sql
-- Tesorería: credencial SII de la empresa (secreto cifrado), ejecuciones y evidencia
-- de archivos. Amplía el libro interno para el detalle que trae el Registro de Compras y Ventas.
-- No crea asientos ni envía documentos al SII.

ALTER TABLE fin.documento_tributario
    ADD COLUMN IF NOT EXISTS exento numeric(18, 2) NOT NULL DEFAULT 0;

ALTER TABLE fin.documento_tributario
    ADD COLUMN IF NOT EXISTS otros numeric(18, 2) NOT NULL DEFAULT 0;

ALTER TABLE fin.documento_tributario
    ADD COLUMN IF NOT EXISTS fecha_recepcion date NULL;

ALTER TABLE fin.documento_tributario
    ADD COLUMN IF NOT EXISTS estado_sii varchar(40) NOT NULL DEFAULT '';

ALTER TABLE fin.documento_tributario
    ADD COLUMN IF NOT EXISTS periodo_anio integer NULL;

ALTER TABLE fin.documento_tributario
    ADD COLUMN IF NOT EXISTS periodo_mes integer NULL;

ALTER TABLE fin.documento_tributario
    ADD COLUMN IF NOT EXISTS ejecucion_sii_id bigint NULL;

CREATE INDEX IF NOT EXISTS ix_documento_tributario_periodo
    ON fin.documento_tributario (direccion, periodo_anio, periodo_mes);

CREATE TABLE IF NOT EXISTS fin.sii_credencial (
    id smallint PRIMARY KEY DEFAULT 1,
    rut varchar(20) NOT NULL,
    usuario varchar(32) NOT NULL,
    secreto_cifrado text NOT NULL DEFAULT '',
    estado varchar(32) NOT NULL DEFAULT 'INCOMPLETA',
    updated_at timestamptz NOT NULL DEFAULT now(),
    updated_by bigint NULL,
    CONSTRAINT ck_sii_credencial_singleton CHECK (id = 1),
    CONSTRAINT ck_sii_credencial_estado CHECK (estado IN ('INCOMPLETA', 'CONFIGURADA'))
);

COMMENT ON COLUMN fin.sii_credencial.secreto_cifrado IS
    'Clave tributaria cifrada. Nunca se lee para mostrarla en pantalla, logs o API.';

ALTER TABLE fin.sii_credencial
    ALTER COLUMN updated_at SET DEFAULT now();

CREATE TABLE IF NOT EXISTS fin.sii_ejecucion (
    id bigserial PRIMARY KEY,
    company_id bigint NOT NULL,
    actor_id bigint NULL,
    actor_email varchar(254) NOT NULL DEFAULT '',
    periodo_anio integer NOT NULL,
    periodo_mes integer NOT NULL,
    tipo_integracion varchar(16) NOT NULL DEFAULT 'SII',
    estado varchar(40) NOT NULL,
    pasos text NOT NULL DEFAULT '[]',
    inicio_at timestamptz NOT NULL DEFAULT now(),
    fin_at timestamptz NULL,
    compras_encontrados integer NOT NULL DEFAULT 0,
    compras_importados integer NOT NULL DEFAULT 0,
    compras_omitidos integer NOT NULL DEFAULT 0,
    compras_errores integer NOT NULL DEFAULT 0,
    ventas_encontrados integer NOT NULL DEFAULT 0,
    ventas_importados integer NOT NULL DEFAULT 0,
    ventas_omitidos integer NOT NULL DEFAULT 0,
    ventas_errores integer NOT NULL DEFAULT 0,
    error_publico text NULL,
    error_tecnico text NULL,
    CONSTRAINT ck_sii_ejecucion_tipo CHECK (tipo_integracion = 'SII'),
    CONSTRAINT ck_sii_ejecucion_mes CHECK (periodo_mes BETWEEN 1 AND 12),
    CONSTRAINT ck_sii_ejecucion_estado CHECK (
        estado IN (
            'PENDIENTE',
            'EN_PROCESO',
            'DESCARGANDO_COMPRAS',
            'DESCARGANDO_VENTAS',
            'PROCESANDO_COMPRAS',
            'PROCESANDO_VENTAS',
            'IMPORTANDO',
            'COMPLETADO',
            'COMPLETADO_CON_OBSERVACIONES',
            'REQUIERE_INTERVENCION_USUARIO',
            'ERROR'
        )
    )
);

CREATE INDEX IF NOT EXISTS ix_sii_ejecucion_empresa
    ON fin.sii_ejecucion (company_id, inicio_at DESC);

CREATE UNIQUE INDEX IF NOT EXISTS ux_sii_ejecucion_activa
    ON fin.sii_ejecucion (company_id)
    WHERE estado IN (
        'PENDIENTE',
        'EN_PROCESO',
        'DESCARGANDO_COMPRAS',
        'DESCARGANDO_VENTAS',
        'PROCESANDO_COMPRAS',
        'PROCESANDO_VENTAS',
        'IMPORTANDO'
    );

CREATE TABLE IF NOT EXISTS fin.sii_archivo (
    id bigserial PRIMARY KEY,
    ejecucion_id bigint NOT NULL REFERENCES fin.sii_ejecucion (id) ON DELETE CASCADE,
    tipo varchar(16) NOT NULL,
    nombre_archivo varchar(255) NOT NULL,
    periodo_anio integer NOT NULL,
    periodo_mes integer NOT NULL,
    company_id bigint NOT NULL,
    descargado_at timestamptz NOT NULL DEFAULT now(),
    sha256 varchar(64) NOT NULL,
    tamano_bytes bigint NOT NULL,
    ruta varchar(500) NOT NULL,
    CONSTRAINT ck_sii_archivo_tipo CHECK (tipo IN ('COMPRAS', 'VENTAS'))
);

CREATE INDEX IF NOT EXISTS ix_sii_archivo_hash
    ON fin.sii_archivo (company_id, sha256);

ALTER TABLE fin.sii_ejecucion ALTER COLUMN actor_email SET DEFAULT '';
ALTER TABLE fin.sii_ejecucion ALTER COLUMN tipo_integracion SET DEFAULT 'SII';
ALTER TABLE fin.sii_ejecucion ALTER COLUMN pasos SET DEFAULT '[]';
ALTER TABLE fin.sii_ejecucion ALTER COLUMN inicio_at SET DEFAULT now();
ALTER TABLE fin.sii_ejecucion ALTER COLUMN compras_encontrados SET DEFAULT 0;
ALTER TABLE fin.sii_ejecucion ALTER COLUMN compras_importados SET DEFAULT 0;
ALTER TABLE fin.sii_ejecucion ALTER COLUMN compras_omitidos SET DEFAULT 0;
ALTER TABLE fin.sii_ejecucion ALTER COLUMN compras_errores SET DEFAULT 0;
ALTER TABLE fin.sii_ejecucion ALTER COLUMN ventas_encontrados SET DEFAULT 0;
ALTER TABLE fin.sii_ejecucion ALTER COLUMN ventas_importados SET DEFAULT 0;
ALTER TABLE fin.sii_ejecucion ALTER COLUMN ventas_omitidos SET DEFAULT 0;
ALTER TABLE fin.sii_ejecucion ALTER COLUMN ventas_errores SET DEFAULT 0;

ALTER TABLE fin.sii_archivo
    ALTER COLUMN descargado_at SET DEFAULT now();
