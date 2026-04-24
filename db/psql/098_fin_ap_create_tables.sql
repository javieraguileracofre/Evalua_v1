-- db/psql/098_fin_ap_create_tables.sql
-- DDL Cuentas por pagar (fin.ap_*) — mismo criterio que SQLAlchemy.
-- Ejecutar como rol con CREATE en fin y REFERENCES en public.proveedor, public.proveedor_banco
--   y en fin.categoria_gasto, fin.centro_costo (o aplicar antes db/psql/096_grant_evalua_user_ap_fk.sql).
-- Si quedó a medias un reset, borre primero las tablas AP (094) o DROP manual de fin.ap_*.

BEGIN;

CREATE TABLE IF NOT EXISTS fin.ap_documento (
	id BIGSERIAL NOT NULL,
	uuid UUID DEFAULT gen_random_uuid() NOT NULL,
	proveedor_id BIGINT NOT NULL,
	tipo fin.ap_doc_tipo NOT NULL,
	estado fin.ap_doc_estado DEFAULT 'BORRADOR'::fin.ap_doc_estado NOT NULL,
	folio VARCHAR(40) NOT NULL,
	fecha_emision DATE NOT NULL,
	fecha_recepcion DATE,
	fecha_vencimiento DATE NOT NULL,
	moneda fin.moneda_iso DEFAULT 'CLP'::fin.moneda_iso NOT NULL,
	tipo_cambio NUMERIC(18, 6) DEFAULT 1 NOT NULL,
	neto NUMERIC(18, 2) DEFAULT 0 NOT NULL,
	exento NUMERIC(18, 2) DEFAULT 0 NOT NULL,
	iva NUMERIC(18, 2) DEFAULT 0 NOT NULL,
	otros_impuestos NUMERIC(18, 2) DEFAULT 0 NOT NULL,
	total NUMERIC(18, 2) DEFAULT 0 NOT NULL,
	saldo_pendiente NUMERIC(18, 2) DEFAULT 0 NOT NULL,
	referencia VARCHAR(180),
	observaciones TEXT,
	tipo_compra_contable VARCHAR(20) DEFAULT 'GASTO' NOT NULL,
	cuenta_gasto_codigo VARCHAR(30),
	cuenta_proveedores_codigo VARCHAR(30),
	asiento_id BIGINT,
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
	updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
	CONSTRAINT pk_ap_documento PRIMARY KEY (id),
	CONSTRAINT ux_ap_doc_unique UNIQUE (proveedor_id, tipo, folio),
	CONSTRAINT ux_ap_documento_uuid UNIQUE (uuid),
	CONSTRAINT fk_ap_documento_proveedor_id_proveedor FOREIGN KEY(proveedor_id) REFERENCES public.proveedor (id) ON DELETE RESTRICT
);

CREATE TABLE IF NOT EXISTS fin.ap_documento_detalle (
	id BIGSERIAL NOT NULL,
	documento_id BIGINT NOT NULL,
	linea INTEGER NOT NULL,
	descripcion VARCHAR(260) NOT NULL,
	cantidad NUMERIC(18, 6) DEFAULT 1 NOT NULL,
	precio_unitario NUMERIC(18, 6) DEFAULT 0 NOT NULL,
	descuento NUMERIC(18, 2) DEFAULT 0 NOT NULL,
	neto_linea NUMERIC(18, 2) DEFAULT 0 NOT NULL,
	iva_linea NUMERIC(18, 2) DEFAULT 0 NOT NULL,
	otros_impuestos NUMERIC(18, 2) DEFAULT 0 NOT NULL,
	total_linea NUMERIC(18, 2) GENERATED ALWAYS AS ((neto_linea + iva_linea)) STORED NOT NULL,
	categoria_gasto_id BIGINT,
	centro_costo_id BIGINT,
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
	updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
	CONSTRAINT pk_ap_documento_detalle PRIMARY KEY (id),
	CONSTRAINT ux_ap_doc_det_linea UNIQUE (documento_id, linea),
	CONSTRAINT fk_ap_documento_detalle_documento_id_ap_documento FOREIGN KEY(documento_id) REFERENCES fin.ap_documento (id) ON DELETE CASCADE,
	CONSTRAINT fk_ap_documento_detalle_categoria_gasto_id_categoria_gasto FOREIGN KEY(categoria_gasto_id) REFERENCES fin.categoria_gasto (id) ON DELETE SET NULL,
	CONSTRAINT fk_ap_documento_detalle_centro_costo_id_centro_costo FOREIGN KEY(centro_costo_id) REFERENCES fin.centro_costo (id) ON DELETE SET NULL
);

CREATE TABLE IF NOT EXISTS fin.ap_documento_impuesto (
	id BIGSERIAL NOT NULL,
	documento_id BIGINT NOT NULL,
	tipo fin.impuesto_tipo DEFAULT 'OTRO'::fin.impuesto_tipo NOT NULL,
	codigo VARCHAR(40),
	nombre VARCHAR(120),
	monto NUMERIC(18, 2) DEFAULT 0 NOT NULL,
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
	CONSTRAINT pk_ap_documento_impuesto PRIMARY KEY (id),
	CONSTRAINT ux_ap_doc_imp_unique UNIQUE (documento_id, tipo, codigo),
	CONSTRAINT fk_ap_documento_impuesto_documento_id_ap_documento FOREIGN KEY(documento_id) REFERENCES fin.ap_documento (id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS fin.ap_pago (
	id BIGSERIAL NOT NULL,
	uuid UUID DEFAULT gen_random_uuid() NOT NULL,
	proveedor_id BIGINT NOT NULL,
	estado fin.ap_pago_estado DEFAULT 'BORRADOR'::fin.ap_pago_estado NOT NULL,
	fecha_pago DATE NOT NULL,
	medio_pago fin.medio_pago DEFAULT 'TRANSFERENCIA'::fin.medio_pago NOT NULL,
	referencia VARCHAR(180),
	banco_proveedor_id BIGINT,
	moneda fin.moneda_iso DEFAULT 'CLP'::fin.moneda_iso NOT NULL,
	tipo_cambio NUMERIC(18, 6) DEFAULT 1 NOT NULL,
	monto_total NUMERIC(18, 2) DEFAULT 0 NOT NULL,
	observaciones TEXT,
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
	updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
	CONSTRAINT pk_ap_pago PRIMARY KEY (id),
	CONSTRAINT fk_ap_pago_proveedor_id_proveedor FOREIGN KEY(proveedor_id) REFERENCES public.proveedor (id) ON DELETE RESTRICT,
	CONSTRAINT fk_ap_pago_banco_proveedor_id_proveedor_banco FOREIGN KEY(banco_proveedor_id) REFERENCES public.proveedor_banco (id) ON DELETE SET NULL
);

CREATE TABLE IF NOT EXISTS fin.ap_pago_aplicacion (
	id BIGSERIAL NOT NULL,
	pago_id BIGINT NOT NULL,
	documento_id BIGINT NOT NULL,
	monto_aplicado NUMERIC(18, 2) DEFAULT 0 NOT NULL,
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
	CONSTRAINT pk_ap_pago_aplicacion PRIMARY KEY (id),
	CONSTRAINT ux_pago_doc UNIQUE (pago_id, documento_id),
	CONSTRAINT fk_ap_pago_aplicacion_pago_id_ap_pago FOREIGN KEY(pago_id) REFERENCES fin.ap_pago (id) ON DELETE CASCADE,
	CONSTRAINT fk_ap_pago_aplicacion_documento_id_ap_documento FOREIGN KEY(documento_id) REFERENCES fin.ap_documento (id) ON DELETE RESTRICT
);

CREATE INDEX IF NOT EXISTS ix_ap_doc_estado ON fin.ap_documento (estado);
CREATE INDEX IF NOT EXISTS ix_ap_doc_proveedor ON fin.ap_documento (proveedor_id);
CREATE INDEX IF NOT EXISTS ix_ap_doc_fechas ON fin.ap_documento (fecha_emision, fecha_vencimiento);
CREATE INDEX IF NOT EXISTS ix_ap_doc_det_categoria ON fin.ap_documento_detalle (categoria_gasto_id);
CREATE INDEX IF NOT EXISTS ix_ap_doc_det_centro ON fin.ap_documento_detalle (centro_costo_id);
CREATE INDEX IF NOT EXISTS ix_ap_doc_det_documento ON fin.ap_documento_detalle (documento_id);
CREATE INDEX IF NOT EXISTS ix_ap_doc_imp_documento ON fin.ap_documento_impuesto (documento_id);
CREATE INDEX IF NOT EXISTS ix_ap_pago_proveedor_fecha ON fin.ap_pago (proveedor_id, fecha_pago);
CREATE INDEX IF NOT EXISTS ix_ap_pago_aplicacion_documento ON fin.ap_pago_aplicacion (documento_id);

COMMIT;
