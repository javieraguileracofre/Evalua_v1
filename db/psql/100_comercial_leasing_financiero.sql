-- db/psql/100_comercial_leasing_financiero.sql
-- Módulo comercial: cotizaciones leasing financiero + proyección contable + cuentas dedicadas
-- Idempotente: seguro ejecutar más de una vez.

BEGIN;

-- ============================================================
-- CUENTAS PROPIAS LEASING FINANCIERO (fin.plan_cuenta)
-- ============================================================
INSERT INTO fin.plan_cuenta (
    codigo, nombre, nivel, cuenta_padre_id, tipo, clasificacion, naturaleza,
    acepta_movimiento, requiere_centro_costo, estado, descripcion
)
SELECT
    v.codigo, v.nombre, 3, p.id, v.tipo, v.clasificacion, v.naturaleza,
    TRUE, FALSE, 'ACTIVO', v.descripcion
FROM (VALUES
    ('113701', 'CUENTAS POR COBRAR LEASING FINANCIERO', 'ACTIVO', 'ACTIVO_CORRIENTE', 'DEUDORA',
     'Principal / saldo arrendamiento financiero por cobrar al cliente.'),
    ('210701', 'OBLIGACIONES LEASING FINANCIERO', 'PASIVO', 'PASIVO_CORRIENTE', 'ACREEDORA',
     'Reconocimiento inicial (espejo contable) / ajustes de pasivo según política interna.'),
    ('410701', 'INGRESOS FINANCIEROS LEASING', 'INGRESO', 'INGRESO_OPERACIONAL', 'ACREEDORA',
     'Intereses devengados / cobrados en operaciones de leasing financiero.')
) AS v(codigo, nombre, tipo, clasificacion, naturaleza, descripcion)
JOIN fin.plan_cuenta p ON p.codigo = '1.1'
WHERE NOT EXISTS (SELECT 1 FROM fin.plan_cuenta x WHERE x.codigo = v.codigo);

-- Si aún no existe agrupador 1.1, insertar cuentas sin padre (no debería ocurrir en instalación estándar)
INSERT INTO fin.plan_cuenta (
    codigo, nombre, nivel, cuenta_padre_id, tipo, clasificacion, naturaleza,
    acepta_movimiento, requiere_centro_costo, estado, descripcion
)
SELECT '113701', 'CUENTAS POR COBRAR LEASING FINANCIERO', 3, NULL, 'ACTIVO', 'ACTIVO_CORRIENTE', 'DEUDORA',
       TRUE, FALSE, 'ACTIVO', 'Principal leasing financiero'
WHERE NOT EXISTS (SELECT 1 FROM fin.plan_cuenta WHERE codigo = '113701');

INSERT INTO fin.plan_cuenta (
    codigo, nombre, nivel, cuenta_padre_id, tipo, clasificacion, naturaleza,
    acepta_movimiento, requiere_centro_costo, estado, descripcion
)
SELECT '210701', 'OBLIGACIONES LEASING FINANCIERO', 3, NULL, 'PASIVO', 'PASIVO_CORRIENTE', 'ACREEDORA',
       TRUE, FALSE, 'ACTIVO', 'Obligaciones leasing financiero'
WHERE NOT EXISTS (SELECT 1 FROM fin.plan_cuenta WHERE codigo = '210701');

INSERT INTO fin.plan_cuenta (
    codigo, nombre, nivel, cuenta_padre_id, tipo, clasificacion, naturaleza,
    acepta_movimiento, requiere_centro_costo, estado, descripcion
)
SELECT '410701', 'INGRESOS FINANCIEROS LEASING', 3, NULL, 'INGRESO', 'INGRESO_OPERACIONAL', 'ACREEDORA',
       TRUE, FALSE, 'ACTIVO', 'Intereses leasing financiero'
WHERE NOT EXISTS (SELECT 1 FROM fin.plan_cuenta WHERE codigo = '410701');

-- ============================================================
-- CONFIGURACIÓN CONTABLE (eventos estándar del módulo)
-- Usa 110201 (caja/bancos seed) para cobros.
-- ============================================================
INSERT INTO fin.config_contable (
    codigo_evento, nombre_evento, lado, codigo_cuenta, orden,
    requiere_centro_costo, requiere_documento, estado, descripcion
)
SELECT 'LEASING_FIN_ORIGINACION', 'Originación leasing financiero', 'DEBE', '113701', 1,
       FALSE, TRUE, 'ACTIVO', 'Activo por cobrar leasing'
WHERE EXISTS (SELECT 1 FROM fin.plan_cuenta WHERE codigo = '113701')
ON CONFLICT (codigo_evento, lado, orden) DO NOTHING;

INSERT INTO fin.config_contable (
    codigo_evento, nombre_evento, lado, codigo_cuenta, orden,
    requiere_centro_costo, requiere_documento, estado, descripcion
)
SELECT 'LEASING_FIN_ORIGINACION', 'Originación leasing financiero', 'HABER', '210701', 1,
       FALSE, TRUE, 'ACTIVO', 'Contrapartida obligación / ingreso diferido'
WHERE EXISTS (SELECT 1 FROM fin.plan_cuenta WHERE codigo = '210701')
ON CONFLICT (codigo_evento, lado, orden) DO NOTHING;

INSERT INTO fin.config_contable (
    codigo_evento, nombre_evento, lado, codigo_cuenta, orden,
    requiere_centro_costo, requiere_documento, estado, descripcion
)
SELECT 'LEASING_FIN_COBRO_CUOTA', 'Cobro cuota leasing', 'DEBE', '110201', 1,
       FALSE, TRUE, 'ACTIVO', 'Ingreso efectivo / banco'
WHERE EXISTS (SELECT 1 FROM fin.plan_cuenta WHERE codigo = '110201')
ON CONFLICT (codigo_evento, lado, orden) DO NOTHING;

INSERT INTO fin.config_contable (
    codigo_evento, nombre_evento, lado, codigo_cuenta, orden,
    requiere_centro_costo, requiere_documento, estado, descripcion
)
SELECT 'LEASING_FIN_COBRO_CUOTA', 'Cobro cuota leasing', 'HABER', '113701', 1,
       FALSE, TRUE, 'ACTIVO', 'Baja CxC principal'
WHERE EXISTS (SELECT 1 FROM fin.plan_cuenta WHERE codigo = '113701')
ON CONFLICT (codigo_evento, lado, orden) DO NOTHING;

INSERT INTO fin.config_contable (
    codigo_evento, nombre_evento, lado, codigo_cuenta, orden,
    requiere_centro_costo, requiere_documento, estado, descripcion
)
SELECT 'LEASING_FIN_COBRO_CUOTA', 'Cobro cuota leasing', 'HABER', '410701', 2,
       FALSE, TRUE, 'ACTIVO', 'Reconocimiento intereses'
WHERE EXISTS (SELECT 1 FROM fin.plan_cuenta WHERE codigo = '410701')
ON CONFLICT (codigo_evento, lado, orden) DO NOTHING;

INSERT INTO fin.config_contable_detalle_modulo (
    modulo, submodulo, tipo_documento, codigo_evento, nombre_evento, lado, codigo_cuenta, orden,
    requiere_centro_costo, requiere_documento, requiere_cliente, requiere_proveedor, estado, descripcion
)
SELECT 'COMERCIAL', 'LEASING_FIN', 'ORIGINACION', 'LEASING_FIN_ORIGINACION', 'Originación leasing', 'DEBE', '113701', 1,
       FALSE, TRUE, TRUE, FALSE, 'ACTIVO', 'Debe activo leasing'
WHERE EXISTS (SELECT 1 FROM fin.plan_cuenta WHERE codigo = '113701')
ON CONFLICT (modulo, submodulo, tipo_documento, codigo_evento, lado, orden) DO NOTHING;

INSERT INTO fin.config_contable_detalle_modulo (
    modulo, submodulo, tipo_documento, codigo_evento, nombre_evento, lado, codigo_cuenta, orden,
    requiere_centro_costo, requiere_documento, requiere_cliente, requiere_proveedor, estado, descripcion
)
SELECT 'COMERCIAL', 'LEASING_FIN', 'ORIGINACION', 'LEASING_FIN_ORIGINACION', 'Originación leasing', 'HABER', '210701', 1,
       FALSE, TRUE, TRUE, FALSE, 'ACTIVO', 'Haber pasivo leasing'
WHERE EXISTS (SELECT 1 FROM fin.plan_cuenta WHERE codigo = '210701')
ON CONFLICT (modulo, submodulo, tipo_documento, codigo_evento, lado, orden) DO NOTHING;

INSERT INTO fin.config_contable_detalle_modulo (
    modulo, submodulo, tipo_documento, codigo_evento, nombre_evento, lado, codigo_cuenta, orden,
    requiere_centro_costo, requiere_documento, requiere_cliente, requiere_proveedor, estado, descripcion
)
SELECT 'COMERCIAL', 'LEASING_FIN', 'COBRO_CUOTA', 'LEASING_FIN_COBRO_CUOTA', 'Cobro cuota leasing', 'DEBE', '110201', 1,
       FALSE, TRUE, TRUE, FALSE, 'ACTIVO', 'Entrada tesorería'
WHERE EXISTS (SELECT 1 FROM fin.plan_cuenta WHERE codigo = '110201')
ON CONFLICT (modulo, submodulo, tipo_documento, codigo_evento, lado, orden) DO NOTHING;

INSERT INTO fin.config_contable_detalle_modulo (
    modulo, submodulo, tipo_documento, codigo_evento, nombre_evento, lado, codigo_cuenta, orden,
    requiere_centro_costo, requiere_documento, requiere_cliente, requiere_proveedor, estado, descripcion
)
SELECT 'COMERCIAL', 'LEASING_FIN', 'COBRO_CUOTA', 'LEASING_FIN_COBRO_CUOTA', 'Cobro cuota leasing', 'HABER', '113701', 1,
       FALSE, TRUE, TRUE, FALSE, 'ACTIVO', 'Baja principal'
WHERE EXISTS (SELECT 1 FROM fin.plan_cuenta WHERE codigo = '113701')
ON CONFLICT (modulo, submodulo, tipo_documento, codigo_evento, lado, orden) DO NOTHING;

INSERT INTO fin.config_contable_detalle_modulo (
    modulo, submodulo, tipo_documento, codigo_evento, nombre_evento, lado, codigo_cuenta, orden,
    requiere_centro_costo, requiere_documento, requiere_cliente, requiere_proveedor, estado, descripcion
)
SELECT 'COMERCIAL', 'LEASING_FIN', 'COBRO_CUOTA', 'LEASING_FIN_COBRO_CUOTA', 'Cobro cuota leasing', 'HABER', '410701', 2,
       FALSE, TRUE, TRUE, FALSE, 'ACTIVO', 'Ingreso financiero'
WHERE EXISTS (SELECT 1 FROM fin.plan_cuenta WHERE codigo = '410701')
ON CONFLICT (modulo, submodulo, tipo_documento, codigo_evento, lado, orden) DO NOTHING;

-- ============================================================
-- TABLAS OPERATIVAS (public)
-- ============================================================
CREATE TABLE IF NOT EXISTS public.comercial_lf_cotizaciones (
    id                  BIGSERIAL PRIMARY KEY,
    cliente_id          BIGINT NOT NULL REFERENCES public.clientes(id) ON DELETE CASCADE,

    monto               NUMERIC(18, 2) NULL,
    moneda              VARCHAR(10) NOT NULL DEFAULT 'CLP',
    dolar_valor         NUMERIC(14, 4) NULL,

    tasa                NUMERIC(9, 6) NULL,
    plazo               INTEGER NULL,
    opcion_compra       NUMERIC(18, 2) NULL,
    periodos_gracia     INTEGER NOT NULL DEFAULT 0,

    fecha_inicio        DATE NULL,
    valor_neto          NUMERIC(18, 2) NULL,
    pago_inicial_tipo   VARCHAR(20) NULL,
    pago_inicial_valor  NUMERIC(18, 2) NULL,

    financia_seguro     BOOLEAN NOT NULL DEFAULT FALSE,
    seguro_monto_uf     NUMERIC(18, 4) NULL,
    otros_montos_pesos  NUMERIC(18, 2) NULL,

    concesionario       VARCHAR(255) NULL,
    ejecutivo           VARCHAR(255) NULL,

    fecha_cotizacion    DATE NOT NULL DEFAULT (CURRENT_DATE),
    uf_valor            NUMERIC(14, 4) NULL,
    monto_financiado    NUMERIC(18, 2) NULL,

    estado              VARCHAR(40) NOT NULL DEFAULT 'PENDIENTE',
    contrato_activo     BOOLEAN NOT NULL DEFAULT FALSE,

    creado_en           TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    actualizado_en      TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    CONSTRAINT chk_comercial_lf_estado CHECK (
        estado IN (
            'BORRADOR', 'COTIZADA', 'PENDIENTE', 'EN_ANALISIS_COMERCIAL', 'EN_ANALISIS_CREDITO',
            'PRE_APROBADA', 'APROBADA', 'EN_FORMALIZACION', 'CONTRATADA', 'VIGENTE',
            'RECHAZADA', 'PERDIDA_CLIENTE', 'ANULADA'
        )
    )
);

CREATE INDEX IF NOT EXISTS ix_comercial_lf_cot_cliente_fecha
    ON public.comercial_lf_cotizaciones (cliente_id, fecha_cotizacion);

CREATE INDEX IF NOT EXISTS ix_comercial_lf_cot_estado
    ON public.comercial_lf_cotizaciones (estado);

CREATE TABLE IF NOT EXISTS public.comercial_lf_proyeccion_linea (
    id                  BIGSERIAL PRIMARY KEY,
    cotizacion_id       BIGINT NOT NULL REFERENCES public.comercial_lf_cotizaciones(id) ON DELETE CASCADE,
    secuencia           INTEGER NOT NULL,
    etapa               VARCHAR(40) NOT NULL,
    ref_cuota           INTEGER NULL,
    glosa               VARCHAR(500) NOT NULL,
    cuenta_codigo       VARCHAR(30) NOT NULL,
    debe                NUMERIC(18, 2) NOT NULL DEFAULT 0,
    haber               NUMERIC(18, 2) NOT NULL DEFAULT 0,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    CONSTRAINT uq_comercial_lf_proy_seq UNIQUE (cotizacion_id, secuencia)
);

CREATE INDEX IF NOT EXISTS ix_comercial_lf_proy_cot
    ON public.comercial_lf_proyeccion_linea (cotizacion_id);

CREATE TABLE IF NOT EXISTS public.comercial_lf_analisis_credito (
    id                          BIGSERIAL PRIMARY KEY,
    cotizacion_id               BIGINT NOT NULL UNIQUE
                                    REFERENCES public.comercial_lf_cotizaciones(id) ON DELETE CASCADE,
    cliente_id                  BIGINT NOT NULL
                                    REFERENCES public.clientes(id) ON DELETE CASCADE,
    tipo_persona                VARCHAR(20) NOT NULL DEFAULT 'NATURAL',
    tipo_producto               VARCHAR(30) NOT NULL DEFAULT 'leasing_financiero',
    moneda_referencia           VARCHAR(10) NOT NULL DEFAULT 'CLP',

    -- Variables scoring persona natural
    ingreso_neto_mensual        NUMERIC(18, 2) NOT NULL DEFAULT 0,
    carga_financiera_mensual    NUMERIC(18, 2) NOT NULL DEFAULT 0,
    antiguedad_laboral_meses    INTEGER NOT NULL DEFAULT 0,

    -- Variables scoring persona jurídica
    ventas_anuales              NUMERIC(18, 2) NOT NULL DEFAULT 0,
    ebitda_anual                NUMERIC(18, 2) NOT NULL DEFAULT 0,
    deuda_financiera_total      NUMERIC(18, 2) NOT NULL DEFAULT 0,
    patrimonio                  NUMERIC(18, 2) NOT NULL DEFAULT 0,
    anios_operacion             INTEGER NOT NULL DEFAULT 0,

    -- Variables comunes de riesgo
    score_buro                  INTEGER NULL,
    comportamiento_pago         VARCHAR(20) NOT NULL DEFAULT 'SIN_HISTORIAL',
    ltv_pct                     NUMERIC(7, 2) NOT NULL DEFAULT 0,
    dscr                        NUMERIC(9, 4) NULL,
    leverage_ratio              NUMERIC(9, 4) NULL,

    -- Resultado
    score_total                 NUMERIC(6, 2) NOT NULL DEFAULT 0,
    rating                      VARCHAR(4) NOT NULL DEFAULT 'E',
    recomendacion               VARCHAR(20) NOT NULL DEFAULT 'RECHAZADO',
    nivel_riesgo                VARCHAR(20) NOT NULL DEFAULT 'ALTO',
    motivo_resumen              TEXT NOT NULL DEFAULT '',
    supuestos                   TEXT NOT NULL DEFAULT '',
    analista                    VARCHAR(200) NOT NULL DEFAULT 'sistema',
    creado_en                   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    actualizado_en              TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    CONSTRAINT chk_lf_analisis_tipo_persona
        CHECK (tipo_persona IN ('NATURAL', 'JURIDICA')),
    CONSTRAINT chk_lf_analisis_comportamiento
        CHECK (comportamiento_pago IN ('BUENO', 'REGULAR', 'MALO', 'SIN_HISTORIAL')),
    CONSTRAINT chk_lf_analisis_recomendacion
        CHECK (recomendacion IN ('APROBADO', 'RECHAZADO', 'OBSERVACION')),
    CONSTRAINT chk_lf_analisis_nivel_riesgo
        CHECK (nivel_riesgo IN ('BAJO', 'MEDIO', 'ALTO')),
    CONSTRAINT chk_lf_analisis_rating
        CHECK (rating IN ('A', 'B', 'C', 'D', 'E'))
);

CREATE INDEX IF NOT EXISTS ix_lf_analisis_cliente
    ON public.comercial_lf_analisis_credito (cliente_id);

CREATE INDEX IF NOT EXISTS ix_lf_analisis_recomendacion
    ON public.comercial_lf_analisis_credito (recomendacion);

CREATE INDEX IF NOT EXISTS ix_lf_analisis_rating
    ON public.comercial_lf_analisis_credito (rating);

CREATE OR REPLACE FUNCTION public.trg_lf_analisis_credito_set_updated()
RETURNS trigger AS $$
BEGIN
    NEW.actualizado_en := NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_lf_analisis_credito_updated ON public.comercial_lf_analisis_credito;
CREATE TRIGGER trg_lf_analisis_credito_updated
    BEFORE UPDATE ON public.comercial_lf_analisis_credito
    FOR EACH ROW
    EXECUTE FUNCTION public.trg_lf_analisis_credito_set_updated();

CREATE OR REPLACE FUNCTION public.trg_comercial_lf_cotizaciones_set_updated()
RETURNS trigger AS $$
BEGIN
    NEW.actualizado_en := NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_comercial_lf_cotizaciones_updated ON public.comercial_lf_cotizaciones;
CREATE TRIGGER trg_comercial_lf_cotizaciones_updated
    BEFORE UPDATE ON public.comercial_lf_cotizaciones
    FOR EACH ROW
    EXECUTE FUNCTION public.trg_comercial_lf_cotizaciones_set_updated();

COMMIT;
