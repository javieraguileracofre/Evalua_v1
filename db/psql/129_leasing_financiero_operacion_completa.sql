-- 129_leasing_financiero_operacion_completa.sql
-- Clientes tipificados, activo LF, amortización persistida, checklist, OC/factura/pago.
-- Idempotente.

BEGIN;

-- ============================================================
-- CLIENTES: tipificación PN/PJ + región
-- ============================================================
ALTER TABLE public.clientes
    ADD COLUMN IF NOT EXISTS tipo_persona VARCHAR(20) NOT NULL DEFAULT 'JURIDICA',
    ADD COLUMN IF NOT EXISTS nombres VARCHAR(120) NULL,
    ADD COLUMN IF NOT EXISTS apellido_paterno VARCHAR(80) NULL,
    ADD COLUMN IF NOT EXISTS apellido_materno VARCHAR(80) NULL,
    ADD COLUMN IF NOT EXISTS region VARCHAR(100) NULL,
    ADD COLUMN IF NOT EXISTS representante_legal_nombre VARCHAR(200) NULL,
    ADD COLUMN IF NOT EXISTS representante_legal_rut VARCHAR(20) NULL;

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'chk_clientes_tipo_persona') THEN
        ALTER TABLE public.clientes
            ADD CONSTRAINT chk_clientes_tipo_persona
            CHECK (tipo_persona IN ('NATURAL', 'JURIDICA'));
    END IF;
END $$;

CREATE TABLE IF NOT EXISTS public.cliente_direccion (
    id BIGSERIAL PRIMARY KEY,
    cliente_id BIGINT NOT NULL REFERENCES public.clientes(id) ON DELETE CASCADE,
    tipo VARCHAR(30) NOT NULL DEFAULT 'COMERCIAL',
    direccion VARCHAR(250) NOT NULL,
    comuna VARCHAR(100) NULL,
    ciudad VARCHAR(100) NULL,
    region VARCHAR(100) NULL,
    pais VARCHAR(80) NOT NULL DEFAULT 'Chile',
    es_principal BOOLEAN NOT NULL DEFAULT FALSE,
    activo BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS ix_cliente_direccion_cliente
    ON public.cliente_direccion (cliente_id, es_principal DESC);

CREATE TABLE IF NOT EXISTS public.cliente_auditoria (
    id BIGSERIAL PRIMARY KEY,
    cliente_id BIGINT NOT NULL REFERENCES public.clientes(id) ON DELETE CASCADE,
    campo VARCHAR(80) NOT NULL,
    valor_anterior TEXT NULL,
    valor_nuevo TEXT NULL,
    usuario VARCHAR(200) NOT NULL DEFAULT 'sistema',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS ix_cliente_auditoria_cliente_fecha
    ON public.cliente_auditoria (cliente_id, created_at DESC);

-- ============================================================
-- COTIZACIÓN LF: proveedor, fondeo, spread, congelamiento
-- ============================================================
ALTER TABLE public.comercial_lf_cotizaciones
    ADD COLUMN IF NOT EXISTS proveedor_id BIGINT NULL
        REFERENCES public.proveedor(id) ON DELETE SET NULL,
    ADD COLUMN IF NOT EXISTS tasa_fondeo NUMERIC(9, 6) NULL,
    ADD COLUMN IF NOT EXISTS spread_margen NUMERIC(9, 6) NULL,
    ADD COLUMN IF NOT EXISTS condiciones_congeladas BOOLEAN NOT NULL DEFAULT FALSE,
    ADD COLUMN IF NOT EXISTS escenario_oficial_version INTEGER NULL;

CREATE INDEX IF NOT EXISTS ix_lf_cot_proveedor
    ON public.comercial_lf_cotizaciones (proveedor_id);

-- ============================================================
-- ACTIVO COTIZADO (1:1 con cotización)
-- ============================================================
CREATE TABLE IF NOT EXISTS public.comercial_lf_activo (
    id BIGSERIAL PRIMARY KEY,
    cotizacion_id BIGINT NOT NULL UNIQUE
        REFERENCES public.comercial_lf_cotizaciones(id) ON DELETE CASCADE,
    proveedor_id BIGINT NULL REFERENCES public.proveedor(id) ON DELETE SET NULL,
    categoria VARCHAR(80) NULL,
    marca VARCHAR(120) NULL,
    modelo VARCHAR(120) NULL,
    descripcion VARCHAR(500) NOT NULL DEFAULT '',
    numero_serie VARCHAR(120) NULL,
    numero_chasis VARCHAR(120) NULL,
    valor_neto NUMERIC(18, 2) NULL,
    iva_monto NUMERIC(18, 2) NULL,
    valor_total NUMERIC(18, 2) NULL,
    estado VARCHAR(40) NOT NULL DEFAULT 'COTIZADO',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT chk_lf_activo_estado CHECK (
        estado IN ('COTIZADO', 'OC_EMITIDA', 'FACTURADO', 'ENTREGADO', 'ACTIVO', 'ANULADO')
    )
);

-- ============================================================
-- AMORTIZACIÓN PERSISTIDA (versión oficial)
-- ============================================================
CREATE TABLE IF NOT EXISTS public.comercial_lf_amortizacion_linea (
    id BIGSERIAL PRIMARY KEY,
    cotizacion_id BIGINT NOT NULL
        REFERENCES public.comercial_lf_cotizaciones(id) ON DELETE CASCADE,
    version_n INTEGER NOT NULL DEFAULT 1,
    numero_cuota INTEGER NOT NULL,
    fecha_cuota DATE NULL,
    saldo_inicial NUMERIC(18, 2) NOT NULL DEFAULT 0,
    cuota NUMERIC(18, 2) NOT NULL DEFAULT 0,
    interes NUMERIC(18, 2) NOT NULL DEFAULT 0,
    amortizacion NUMERIC(18, 2) NOT NULL DEFAULT 0,
    saldo_final NUMERIC(18, 2) NOT NULL DEFAULT 0,
    iva_cuota NUMERIC(18, 2) NULL,
    otros_cargos NUMERIC(18, 2) NULL,
    es_gracia BOOLEAN NOT NULL DEFAULT FALSE,
    es_opcion_compra BOOLEAN NOT NULL DEFAULT FALSE,
    es_oficial BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_lf_amort_cot_ver_cuota UNIQUE (cotizacion_id, version_n, numero_cuota)
);

CREATE INDEX IF NOT EXISTS ix_lf_amort_cot_oficial
    ON public.comercial_lf_amortizacion_linea (cotizacion_id, es_oficial, version_n DESC);

-- ============================================================
-- ORDEN DE COMPRA / FACTURA COMPRA (entidades formales)
-- ============================================================
CREATE TABLE IF NOT EXISTS public.comercial_lf_orden_compra (
    id BIGSERIAL PRIMARY KEY,
    cotizacion_id BIGINT NOT NULL
        REFERENCES public.comercial_lf_cotizaciones(id) ON DELETE CASCADE,
    proveedor_id BIGINT NOT NULL REFERENCES public.proveedor(id),
    numero VARCHAR(50) NOT NULL,
    fecha_emision DATE NOT NULL,
    fecha_entrega_estimada DATE NULL,
    neto NUMERIC(18, 2) NOT NULL,
    iva NUMERIC(18, 2) NOT NULL DEFAULT 0,
    total NUMERIC(18, 2) NOT NULL,
    moneda VARCHAR(10) NOT NULL DEFAULT 'CLP',
    condiciones TEXT NULL,
    estado VARCHAR(30) NOT NULL DEFAULT 'BORRADOR',
    usuario VARCHAR(200) NOT NULL DEFAULT 'sistema',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT chk_lf_oc_estado CHECK (
        estado IN ('BORRADOR', 'APROBADA', 'ENVIADA', 'RECIBIDA', 'ANULADA')
    )
);

CREATE INDEX IF NOT EXISTS ix_lf_oc_cotizacion
    ON public.comercial_lf_orden_compra (cotizacion_id, created_at DESC);

CREATE TABLE IF NOT EXISTS public.comercial_lf_factura_compra (
    id BIGSERIAL PRIMARY KEY,
    cotizacion_id BIGINT NOT NULL
        REFERENCES public.comercial_lf_cotizaciones(id) ON DELETE CASCADE,
    orden_compra_id BIGINT NULL
        REFERENCES public.comercial_lf_orden_compra(id) ON DELETE SET NULL,
    proveedor_id BIGINT NOT NULL REFERENCES public.proveedor(id),
    folio VARCHAR(50) NOT NULL,
    fecha_factura DATE NOT NULL,
    neto NUMERIC(18, 2) NOT NULL,
    iva NUMERIC(18, 2) NOT NULL DEFAULT 0,
    total NUMERIC(18, 2) NOT NULL,
    diferencia_cotizacion NUMERIC(18, 2) NULL,
    diferencia_oc NUMERIC(18, 2) NULL,
    ap_documento_id BIGINT NULL,
    estado VARCHAR(30) NOT NULL DEFAULT 'REGISTRADA',
    usuario VARCHAR(200) NOT NULL DEFAULT 'sistema',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT chk_lf_factura_estado CHECK (
        estado IN ('BORRADOR', 'REGISTRADA', 'VALIDADA', 'CONTABILIZADA', 'ANULADA')
    )
);

CREATE INDEX IF NOT EXISTS ix_lf_factura_cot
    ON public.comercial_lf_factura_compra (cotizacion_id, created_at DESC);

-- ============================================================
-- SOLICITUD DE PAGO AL PROVEEDOR
-- ============================================================
CREATE TABLE IF NOT EXISTS public.comercial_lf_solicitud_pago (
    id BIGSERIAL PRIMARY KEY,
    cotizacion_id BIGINT NOT NULL
        REFERENCES public.comercial_lf_cotizaciones(id) ON DELETE CASCADE,
    factura_compra_id BIGINT NOT NULL
        REFERENCES public.comercial_lf_factura_compra(id) ON DELETE CASCADE,
    proveedor_id BIGINT NOT NULL REFERENCES public.proveedor(id),
    monto NUMERIC(18, 2) NOT NULL,
    moneda VARCHAR(10) NOT NULL DEFAULT 'CLP',
    estado VARCHAR(30) NOT NULL DEFAULT 'BORRADOR',
    idempotency_key VARCHAR(80) NOT NULL,
    aprobado_por VARCHAR(200) NULL,
    fecha_aprobacion TIMESTAMPTZ NULL,
    ap_pago_id BIGINT NULL,
    usuario VARCHAR(200) NOT NULL DEFAULT 'sistema',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_lf_solicitud_pago_idem UNIQUE (idempotency_key),
    CONSTRAINT chk_lf_solicitud_estado CHECK (
        estado IN ('BORRADOR', 'SOLICITADA', 'APROBADA', 'PAGADA', 'RECHAZADA', 'ANULADA')
    )
);

CREATE INDEX IF NOT EXISTS ix_lf_solicitud_cot
    ON public.comercial_lf_solicitud_pago (cotizacion_id, estado);

-- ============================================================
-- CHECKLIST OPERATIVO (ítems por cotización)
-- ============================================================
CREATE TABLE IF NOT EXISTS public.comercial_lf_checklist_item (
    id BIGSERIAL PRIMARY KEY,
    cotizacion_id BIGINT NOT NULL
        REFERENCES public.comercial_lf_cotizaciones(id) ON DELETE CASCADE,
    codigo VARCHAR(50) NOT NULL,
    titulo VARCHAR(200) NOT NULL,
    es_automatico BOOLEAN NOT NULL DEFAULT FALSE,
    es_bloqueante BOOLEAN NOT NULL DEFAULT TRUE,
    estado VARCHAR(20) NOT NULL DEFAULT 'PENDIENTE',
    responsable VARCHAR(200) NULL,
    fecha_limite DATE NULL,
    fecha_cumplimiento TIMESTAMPTZ NULL,
    aprobado_por VARCHAR(200) NULL,
    evidencia_ref VARCHAR(200) NULL,
    comentario TEXT NULL,
    orden INTEGER NOT NULL DEFAULT 0,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_lf_checklist_cot_codigo UNIQUE (cotizacion_id, codigo),
    CONSTRAINT chk_lf_checklist_estado CHECK (
        estado IN ('PENDIENTE', 'COMPLETADO', 'APROBADO', 'RECHAZADO', 'OMITIDO')
    )
);

CREATE INDEX IF NOT EXISTS ix_lf_checklist_cot_orden
    ON public.comercial_lf_checklist_item (cotizacion_id, orden);

COMMIT;
