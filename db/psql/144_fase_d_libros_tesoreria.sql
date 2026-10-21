-- 144_fase_d_libros_tesoreria.sql
-- Documento tributario interno, conciliación, diferencia de cambio,
-- costo promedio y lecturas. Sin XML, certificado ni envío al SII.

CREATE SCHEMA IF NOT EXISTS fin;

ALTER TABLE public.productos
    ADD COLUMN IF NOT EXISTS costo_promedio numeric(14, 4) NOT NULL DEFAULT 0;

COMMENT ON COLUMN public.productos.costo_promedio IS
    'Costo promedio ponderado vigente. Las salidas lo consumen y las entradas lo recalculan.';

CREATE TABLE IF NOT EXISTS fin.documento_tributario (
    id bigserial PRIMARY KEY,
    direccion varchar(12) NOT NULL,
    tipo varchar(20) NOT NULL,
    folio varchar(40) NOT NULL,
    rut_emisor varchar(20) NOT NULL,
    rut_receptor varchar(20) NOT NULL DEFAULT '',
    razon_social varchar(180) NOT NULL DEFAULT '',
    fecha_emision date NOT NULL,
    neto numeric(18, 2) NOT NULL,
    iva numeric(18, 2) NOT NULL,
    total numeric(18, 2) NOT NULL,
    moneda varchar(8) NOT NULL DEFAULT 'CLP',
    asiento_id bigint NULL REFERENCES public.asientos_contables (id),
    origen_tipo varchar(30) NOT NULL,
    origen_id bigint NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT ck_documento_tributario_direccion CHECK (direccion IN ('EMITIDO', 'RECIBIDO')),
    CONSTRAINT ck_documento_tributario_tipo CHECK (
        tipo IN (
            'FACTURA', 'FACTURA_EXENTA', 'BOLETA',
            'NOTA_CREDITO', 'NOTA_DEBITO', 'GUIA', 'OTRO'
        )
    ),
    CONSTRAINT ux_documento_tributario_folio UNIQUE (direccion, tipo, folio, rut_emisor)
);

COMMENT ON TABLE fin.documento_tributario IS
    'Registro interno de libro de compras y ventas. No es un DTE ni se envía al SII.';

CREATE INDEX IF NOT EXISTS ix_documento_tributario_fecha
    ON fin.documento_tributario (direccion, fecha_emision);

CREATE TABLE IF NOT EXISTS fin.cartola_bancaria (
    id bigserial PRIMARY KEY,
    nombre varchar(120) NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS fin.cartola_linea (
    id bigserial PRIMARY KEY,
    cartola_id bigint NOT NULL REFERENCES fin.cartola_bancaria (id) ON DELETE CASCADE,
    fecha date NOT NULL,
    monto numeric(18, 2) NOT NULL,
    glosa varchar(255) NOT NULL DEFAULT '',
    referencia varchar(80) NOT NULL DEFAULT '',
    estado varchar(16) NOT NULL DEFAULT 'PENDIENTE',
    CONSTRAINT ck_cartola_linea_estado CHECK (estado IN ('PENDIENTE', 'CONCILIADA', 'DIFERENCIA'))
);

CREATE INDEX IF NOT EXISTS ix_cartola_linea_cartola
    ON fin.cartola_linea (cartola_id, estado);

CREATE TABLE IF NOT EXISTS fin.conciliacion (
    id bigserial PRIMARY KEY,
    linea_id bigint NOT NULL UNIQUE REFERENCES fin.cartola_linea (id) ON DELETE CASCADE,
    movimiento_tipo varchar(20) NOT NULL,
    movimiento_id bigint NOT NULL,
    asiento_diferencia_id bigint NULL REFERENCES public.asientos_contables (id),
    created_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT ck_conciliacion_movimiento CHECK (movimiento_tipo IN ('PAGO_CLIENTE', 'AP_PAGO'))
);

CREATE TABLE IF NOT EXISTS fin.tipo_cambio_cierre (
    anio integer NOT NULL,
    mes integer NOT NULL,
    moneda varchar(8) NOT NULL,
    valor numeric(18, 6) NOT NULL,
    PRIMARY KEY (anio, mes, moneda),
    CONSTRAINT ck_tipo_cambio_cierre_mes CHECK (mes BETWEEN 1 AND 12),
    CONSTRAINT ck_tipo_cambio_cierre_valor CHECK (valor > 0)
);

CREATE TABLE IF NOT EXISTS fin.revaluacion_fx (
    id bigserial PRIMARY KEY,
    anio integer NOT NULL,
    mes integer NOT NULL,
    documento_tipo varchar(20) NOT NULL,
    documento_id bigint NOT NULL,
    moneda varchar(8) NOT NULL,
    saldo_moneda numeric(18, 2) NOT NULL,
    tc_origen numeric(18, 6) NOT NULL,
    tc_cierre numeric(18, 6) NOT NULL,
    diferencia numeric(18, 2) NOT NULL,
    asiento_id bigint NULL REFERENCES public.asientos_contables (id),
    CONSTRAINT ux_revaluacion_fx_periodo UNIQUE (anio, mes, documento_tipo, documento_id)
);

CREATE TABLE IF NOT EXISTS fin.api_idempotencia (
    id bigserial PRIMARY KEY,
    alcance varchar(40) NOT NULL,
    clave varchar(80) NOT NULL,
    estado varchar(12) NOT NULL,
    cuerpo text NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT ux_api_idempotencia UNIQUE (alcance, clave),
    CONSTRAINT ck_api_idempotencia_estado CHECK (estado IN ('EN_CURSO', 'OK'))
);

DROP INDEX IF EXISTS public.ux_asientos_origen_idempotente;

CREATE UNIQUE INDEX ux_asientos_origen_idempotente
    ON public.asientos_contables (origen_tipo, origen_id)
    WHERE origen_id > 0
      AND origen_tipo IN (
          'AP_DOCUMENTO',
          'AP_PAGO',
          'AP_DOCUMENTO_REVERSA',
          'NOTA_VENTA',
          'NOTA_VENTA_ANULACION',
          'NOTA_VENTA_REVERSA',
          'PAGO_CLIENTE',
          'LEASING_FIN_ACTIVACION',
          'LOP_ACTIVACION',
          'LOP_FACTURACION',
          'FONDO_RENDIR_ENT',
          'FONDO_RENDIR_ENT_REVERSA',
          'FONDO_RENDIR_LIQ',
          'REMUNERACION_PROVISION',
          'REMUNERACION_PAGO',
          'REV_MANUAL',
          'INVENTARIO_MOV',
          'INVENTARIO_SALIDA',
          'LOP_DEPRECIACION',
          'DIFERENCIA_CAMBIO',
          'CONCILIACION_DIF'
      );

COMMENT ON INDEX public.ux_asientos_origen_idempotente IS
    'Idempotencia contable por (origen_tipo, origen_id), incluidas reversiones, diferencia de cambio y conciliación.';

CREATE OR REPLACE VIEW public.analytics_cartera_cxc AS
SELECT
    id,
    cliente_id,
    fecha_emision,
    fecha_vencimiento,
    monto_original,
    saldo_pendiente,
    estado
FROM public.cuentas_por_cobrar
WHERE saldo_pendiente > 0;

CREATE OR REPLACE VIEW public.analytics_contratos_lop_vigentes AS
SELECT
    id,
    codigo,
    fecha_inicio,
    fecha_termino,
    estado,
    renta_mensual,
    moneda,
    plazo_meses
FROM public.leasing_op_contrato
WHERE estado = 'VIGENTE';

CREATE OR REPLACE VIEW public.analytics_resultado_mes AS
SELECT
    CAST(EXTRACT(YEAR FROM a.fecha) AS integer) AS anio,
    CAST(EXTRACT(MONTH FROM a.fecha) AS integer) AS mes,
    d.codigo_cuenta,
    SUM(d.debe) AS debe,
    SUM(d.haber) AS haber
FROM public.asientos_contables a
JOIN public.asientos_detalle d ON d.asiento_id = a.id
GROUP BY 1, 2, 3;

CREATE OR REPLACE VIEW public.analytics_libro_venta AS
SELECT *
FROM fin.documento_tributario
WHERE direccion = 'EMITIDO';

CREATE OR REPLACE VIEW public.analytics_libro_compra AS
SELECT *
FROM fin.documento_tributario
WHERE direccion = 'RECIBIDO';
