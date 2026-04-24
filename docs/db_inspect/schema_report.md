# Reporte de estructura de base de datos

## Esquema `fin`

### `fin.adjunto` (table)

| # | Columna | Tipo | Nullable | PK | FK | Default |
|---|---------|------|----------|----|----|---------|
| 1 | id | BigInteger | NO | YES |  | nextval('fin.adjunto_id_seq'::regclass) |
| 2 | entidad | String(40) | NO |  |  |  |
| 3 | entidad_id | BigInteger | NO |  |  |  |
| 4 | nombre | String(220) | NO |  |  |  |
| 5 | mime | String(120) | YES |  |  |  |
| 6 | storage_path | String(500) | NO |  |  |  |
| 7 | hash_sha256 | String(80) | YES |  |  |  |
| 8 | created_at | DateTime | NO |  |  | now() |

**Índices**

- `adjunto_pkey`
  - `CREATE UNIQUE INDEX adjunto_pkey ON fin.adjunto USING btree (id)`
- `ix_adj_entidad`
  - `CREATE INDEX ix_adj_entidad ON fin.adjunto USING btree (entidad, entidad_id)`

### `fin.ap_documento` (table)

| # | Columna | Tipo | Nullable | PK | FK | Default |
|---|---------|------|----------|----|----|---------|
| 1 | id | BigInteger | NO | YES |  | nextval('fin.ap_documento_id_seq'::regclass) |
| 2 | uuid | UUID(as_uuid=True) | NO |  |  | gen_random_uuid() |
| 3 | proveedor_id | BigInteger | NO |  |  |  |
| 4 | tipo | String  # USER-DEFINED::ap_doc_tipo | NO |  |  |  |
| 5 | estado | String  # USER-DEFINED::ap_doc_estado | NO |  |  | 'BORRADOR'::fin.ap_doc_estado |
| 6 | folio | String(40) | NO |  |  |  |
| 7 | fecha_emision | Date | NO |  |  |  |
| 8 | fecha_recepcion | Date | YES |  |  |  |
| 9 | fecha_vencimiento | Date | NO |  |  |  |
| 10 | moneda | String  # USER-DEFINED::moneda_iso | NO |  |  | 'CLP'::fin.moneda_iso |
| 11 | tipo_cambio | Numeric(18, 6) | NO |  |  | 1 |
| 12 | neto | Numeric(18, 2) | NO |  |  | 0 |
| 13 | exento | Numeric(18, 2) | NO |  |  | 0 |
| 14 | iva | Numeric(18, 2) | NO |  |  | 0 |
| 15 | otros_impuestos | Numeric(18, 2) | NO |  |  | 0 |
| 16 | total | Numeric(18, 2) | NO |  |  | 0 |
| 17 | saldo_pendiente | Numeric(18, 2) | NO |  |  | 0 |
| 18 | referencia | String(180) | YES |  |  |  |
| 19 | observaciones | Text | YES |  |  |  |
| 20 | created_at | DateTime | NO |  |  | now() |
| 21 | updated_at | DateTime | NO |  |  | now() |

**Índices**

- `ap_documento_pkey`
  - `CREATE UNIQUE INDEX ap_documento_pkey ON fin.ap_documento USING btree (id)`
- `ix_ap_doc_estado`
  - `CREATE INDEX ix_ap_doc_estado ON fin.ap_documento USING btree (estado)`
- `ix_ap_doc_fechas`
  - `CREATE INDEX ix_ap_doc_fechas ON fin.ap_documento USING btree (fecha_emision, fecha_vencimiento)`
- `ix_ap_doc_proveedor`
  - `CREATE INDEX ix_ap_doc_proveedor ON fin.ap_documento USING btree (proveedor_id)`
- `ux_ap_doc_unique`
  - `CREATE UNIQUE INDEX ux_ap_doc_unique ON fin.ap_documento USING btree (proveedor_id, tipo, folio)`
- `ux_ap_documento_uuid`
  - `CREATE UNIQUE INDEX ux_ap_documento_uuid ON fin.ap_documento USING btree (uuid)`

### `fin.ap_documento_detalle` (table)

| # | Columna | Tipo | Nullable | PK | FK | Default |
|---|---------|------|----------|----|----|---------|
| 1 | id | BigInteger | NO | YES |  | nextval('fin.ap_documento_detalle_id_seq'::regclass) |
| 2 | documento_id | BigInteger | NO |  |  |  |
| 3 | linea | Integer | NO |  |  |  |
| 4 | descripcion | String(260) | NO |  |  |  |
| 5 | cantidad | Numeric(18, 6) | NO |  |  | 1 |
| 6 | precio_unitario | Numeric(18, 6) | NO |  |  | 0 |
| 7 | descuento | Numeric(18, 2) | NO |  |  | 0 |
| 8 | neto_linea | Numeric(18, 2) | NO |  |  | 0 |
| 9 | iva_linea | Numeric(18, 2) | NO |  |  | 0 |
| 10 | otros_impuestos | Numeric(18, 2) | NO |  |  | 0 |
| 11 | total_linea | Numeric(18, 2) | NO |  |  | 0 |
| 12 | categoria_gasto_id | BigInteger | YES |  |  |  |
| 13 | centro_costo_id | BigInteger | YES |  |  |  |
| 14 | created_at | DateTime | NO |  |  | now() |
| 15 | updated_at | DateTime | NO |  |  | now() |

**Índices**

- `ap_documento_detalle_pkey`
  - `CREATE UNIQUE INDEX ap_documento_detalle_pkey ON fin.ap_documento_detalle USING btree (id)`
- `ix_ap_doc_det_categoria`
  - `CREATE INDEX ix_ap_doc_det_categoria ON fin.ap_documento_detalle USING btree (categoria_gasto_id)`
- `ix_ap_doc_det_centro`
  - `CREATE INDEX ix_ap_doc_det_centro ON fin.ap_documento_detalle USING btree (centro_costo_id)`
- `ix_ap_doc_det_documento`
  - `CREATE INDEX ix_ap_doc_det_documento ON fin.ap_documento_detalle USING btree (documento_id)`
- `ux_ap_doc_det_linea`
  - `CREATE UNIQUE INDEX ux_ap_doc_det_linea ON fin.ap_documento_detalle USING btree (documento_id, linea)`

### `fin.ap_documento_impuesto` (table)

| # | Columna | Tipo | Nullable | PK | FK | Default |
|---|---------|------|----------|----|----|---------|
| 1 | id | BigInteger | NO | YES |  | nextval('fin.ap_documento_impuesto_id_seq'::regclass) |
| 2 | documento_id | BigInteger | NO |  |  |  |
| 3 | tipo | String  # USER-DEFINED::impuesto_tipo | NO |  |  | 'OTRO'::fin.impuesto_tipo |
| 4 | codigo | String(40) | YES |  |  |  |
| 5 | nombre | String(120) | YES |  |  |  |
| 6 | monto | Numeric(18, 2) | NO |  |  | 0 |
| 7 | created_at | DateTime | NO |  |  | now() |

**Índices**

- `ap_documento_impuesto_pkey`
  - `CREATE UNIQUE INDEX ap_documento_impuesto_pkey ON fin.ap_documento_impuesto USING btree (id)`
- `ix_ap_doc_imp_documento`
  - `CREATE INDEX ix_ap_doc_imp_documento ON fin.ap_documento_impuesto USING btree (documento_id)`
- `ux_ap_doc_imp_unique`
  - `CREATE UNIQUE INDEX ux_ap_doc_imp_unique ON fin.ap_documento_impuesto USING btree (documento_id, tipo, COALESCE(codigo, ''::character varying))`

### `fin.ap_pago` (table)

| # | Columna | Tipo | Nullable | PK | FK | Default |
|---|---------|------|----------|----|----|---------|
| 1 | id | BigInteger | NO | YES |  | nextval('fin.ap_pago_id_seq'::regclass) |
| 2 | uuid | UUID(as_uuid=True) | NO |  |  | gen_random_uuid() |
| 3 | proveedor_id | BigInteger | NO |  |  |  |
| 4 | estado | String  # USER-DEFINED::ap_pago_estado | NO |  |  | 'BORRADOR'::fin.ap_pago_estado |
| 5 | fecha_pago | Date | NO |  |  |  |
| 6 | medio_pago | String  # USER-DEFINED::medio_pago | NO |  |  | 'TRANSFERENCIA'::fin.medio_pago |
| 7 | referencia | String(180) | YES |  |  |  |
| 8 | banco_proveedor_id | BigInteger | YES |  |  |  |
| 9 | moneda | String  # USER-DEFINED::moneda_iso | NO |  |  | 'CLP'::fin.moneda_iso |
| 10 | tipo_cambio | Numeric(18, 6) | NO |  |  | 1 |
| 11 | monto_total | Numeric(18, 2) | NO |  |  | 0 |
| 12 | observaciones | Text | YES |  |  |  |
| 13 | created_at | DateTime | NO |  |  | now() |
| 14 | updated_at | DateTime | NO |  |  | now() |

**Índices**

- `ap_pago_pkey`
  - `CREATE UNIQUE INDEX ap_pago_pkey ON fin.ap_pago USING btree (id)`

### `fin.ap_pago_aplicacion` (table)

| # | Columna | Tipo | Nullable | PK | FK | Default |
|---|---------|------|----------|----|----|---------|
| 1 | id | BigInteger | NO | YES |  | nextval('fin.ap_pago_aplicacion_id_seq'::regclass) |
| 2 | pago_id | BigInteger | NO |  |  |  |
| 3 | documento_id | BigInteger | NO |  |  |  |
| 4 | monto_aplicado | Numeric(18, 2) | NO |  |  | 0 |
| 5 | created_at | DateTime | NO |  |  | now() |

**Índices**

- `ap_pago_aplicacion_pkey`
  - `CREATE UNIQUE INDEX ap_pago_aplicacion_pkey ON fin.ap_pago_aplicacion USING btree (id)`
- `ux_pago_doc`
  - `CREATE UNIQUE INDEX ux_pago_doc ON fin.ap_pago_aplicacion USING btree (pago_id, documento_id)`

### `fin.categoria_gasto` (table)

| # | Columna | Tipo | Nullable | PK | FK | Default |
|---|---------|------|----------|----|----|---------|
| 1 | id | BigInteger | NO | YES |  | nextval('fin.categoria_gasto_id_seq'::regclass) |
| 2 | codigo | String(30) | NO |  |  |  |
| 3 | nombre | String(160) | NO |  |  |  |
| 4 | tipo | String  # USER-DEFINED::tipo_gasto | NO |  |  | 'OPERACIONAL'::fin.tipo_gasto |
| 5 | estado | String  # USER-DEFINED::estado_activo | NO |  |  | 'ACTIVO'::fin.estado_activo |
| 6 | created_at | DateTime | NO |  |  | now() |
| 7 | updated_at | DateTime | NO |  |  | now() |

**Índices**

- `categoria_gasto_pkey`
  - `CREATE UNIQUE INDEX categoria_gasto_pkey ON fin.categoria_gasto USING btree (id)`
- `ux_cat_gasto_codigo`
  - `CREATE UNIQUE INDEX ux_cat_gasto_codigo ON fin.categoria_gasto USING btree (codigo)`

### `fin.centro_costo` (table)

| # | Columna | Tipo | Nullable | PK | FK | Default |
|---|---------|------|----------|----|----|---------|
| 1 | id | BigInteger | NO | YES |  | nextval('fin.centro_costo_id_seq'::regclass) |
| 2 | codigo | String(30) | NO |  |  |  |
| 3 | nombre | String(120) | NO |  |  |  |
| 4 | estado | String  # USER-DEFINED::estado_activo | NO |  |  | 'ACTIVO'::fin.estado_activo |
| 5 | created_at | DateTime | NO |  |  | now() |
| 6 | updated_at | DateTime | NO |  |  | now() |

**Índices**

- `centro_costo_pkey`
  - `CREATE UNIQUE INDEX centro_costo_pkey ON fin.centro_costo USING btree (id)`
- `ux_centro_costo_codigo`
  - `CREATE UNIQUE INDEX ux_centro_costo_codigo ON fin.centro_costo USING btree (codigo)`

### `fin.config_contable` (table)

| # | Columna | Tipo | Nullable | PK | FK | Default |
|---|---------|------|----------|----|----|---------|
| 1 | id | BigInteger | NO | YES |  | nextval('fin.config_contable_id_seq'::regclass) |
| 2 | codigo_evento | String(50) | NO |  |  |  |
| 3 | nombre_evento | String(150) | NO |  |  |  |
| 4 | lado | String(10) | NO |  |  |  |
| 5 | codigo_cuenta | String(30) | NO |  | fin.plan_cuenta.codigo |  |
| 6 | orden | Integer | NO |  |  | 1 |
| 7 | requiere_centro_costo | Boolean | NO |  |  | false |
| 8 | requiere_documento | Boolean | NO |  |  | false |
| 9 | estado | String(20) | NO |  |  | 'ACTIVO'::character varying |
| 10 | descripcion | Text | YES |  |  |  |
| 11 | created_at | DateTime | NO |  |  | now() |
| 12 | updated_at | DateTime | NO |  |  | now() |

**Índices**

- `config_contable_pkey`
  - `CREATE UNIQUE INDEX config_contable_pkey ON fin.config_contable USING btree (id)`
- `ix_config_contable_cuenta`
  - `CREATE INDEX ix_config_contable_cuenta ON fin.config_contable USING btree (codigo_cuenta)`
- `ix_config_contable_estado`
  - `CREATE INDEX ix_config_contable_estado ON fin.config_contable USING btree (estado)`
- `ix_config_contable_evento`
  - `CREATE INDEX ix_config_contable_evento ON fin.config_contable USING btree (codigo_evento)`
- `ix_fin_config_contable_cuenta`
  - `CREATE INDEX ix_fin_config_contable_cuenta ON fin.config_contable USING btree (codigo_cuenta)`
- `ix_fin_config_contable_estado`
  - `CREATE INDEX ix_fin_config_contable_estado ON fin.config_contable USING btree (estado)`
- `ix_fin_config_contable_evento`
  - `CREATE INDEX ix_fin_config_contable_evento ON fin.config_contable USING btree (codigo_evento)`
- `uq_config_contable_evento_lado_orden`
  - `CREATE UNIQUE INDEX uq_config_contable_evento_lado_orden ON fin.config_contable USING btree (codigo_evento, lado, orden)`

### `fin.config_contable_detalle_modulo` (table)

| # | Columna | Tipo | Nullable | PK | FK | Default |
|---|---------|------|----------|----|----|---------|
| 1 | id | BigInteger | NO | YES |  | nextval('fin.config_contable_detalle_modulo_id_seq'::regclass) |
| 2 | modulo | String(50) | NO |  |  |  |
| 3 | submodulo | String(50) | YES |  |  |  |
| 4 | tipo_documento | String(50) | YES |  |  |  |
| 5 | codigo_evento | String(50) | NO |  |  |  |
| 6 | nombre_evento | String(150) | NO |  |  |  |
| 7 | lado | String(10) | NO |  |  |  |
| 8 | codigo_cuenta | String(30) | NO |  | fin.plan_cuenta.codigo |  |
| 9 | orden | Integer | NO |  |  | 1 |
| 10 | requiere_centro_costo | Boolean | NO |  |  | false |
| 11 | requiere_documento | Boolean | NO |  |  | false |
| 12 | requiere_cliente | Boolean | NO |  |  | false |
| 13 | requiere_proveedor | Boolean | NO |  |  | false |
| 14 | estado | String(20) | NO |  |  | 'ACTIVO'::character varying |
| 15 | descripcion | Text | YES |  |  |  |
| 16 | created_at | DateTime | NO |  |  | now() |
| 17 | updated_at | DateTime | NO |  |  | now() |

**Índices**

- `config_contable_detalle_modulo_pkey`
  - `CREATE UNIQUE INDEX config_contable_detalle_modulo_pkey ON fin.config_contable_detalle_modulo USING btree (id)`
- `ix_fin_cfg_modulo_estado`
  - `CREATE INDEX ix_fin_cfg_modulo_estado ON fin.config_contable_detalle_modulo USING btree (estado)`
- `ix_fin_cfg_modulo_evento`
  - `CREATE INDEX ix_fin_cfg_modulo_evento ON fin.config_contable_detalle_modulo USING btree (codigo_evento)`
- `ix_fin_cfg_modulo_modulo`
  - `CREATE INDEX ix_fin_cfg_modulo_modulo ON fin.config_contable_detalle_modulo USING btree (modulo)`
- `ix_fin_cfg_modulo_submodulo`
  - `CREATE INDEX ix_fin_cfg_modulo_submodulo ON fin.config_contable_detalle_modulo USING btree (submodulo)`
- `ix_fin_cfg_modulo_tipo_doc`
  - `CREATE INDEX ix_fin_cfg_modulo_tipo_doc ON fin.config_contable_detalle_modulo USING btree (tipo_documento)`
- `uq_fin_cfg_modulo_evento_lado_orden`
  - `CREATE UNIQUE INDEX uq_fin_cfg_modulo_evento_lado_orden ON fin.config_contable_detalle_modulo USING btree (modulo, submodulo, tipo_documento, codigo_evento, lado, orden)`

### `fin.evento` (table)

| # | Columna | Tipo | Nullable | PK | FK | Default |
|---|---------|------|----------|----|----|---------|
| 1 | id | BigInteger | NO | YES |  | nextval('fin.evento_id_seq'::regclass) |
| 2 | entidad | String(40) | NO |  |  |  |
| 3 | entidad_id | BigInteger | NO |  |  |  |
| 4 | evento | String(80) | NO |  |  |  |
| 5 | detalle | Text | YES |  |  |  |
| 6 | user_email | String  # USER-DEFINED::citext | YES |  |  |  |
| 7 | ip_origen | String(80) | YES |  |  |  |
| 8 | created_at | DateTime | NO |  |  | now() |

**Índices**

- `evento_pkey`
  - `CREATE UNIQUE INDEX evento_pkey ON fin.evento USING btree (id)`
- `ix_evento_entidad`
  - `CREATE INDEX ix_evento_entidad ON fin.evento USING btree (entidad, entidad_id)`
- `ix_evento_fecha`
  - `CREATE INDEX ix_evento_fecha ON fin.evento USING btree (created_at)`

### `fin.periodo` (table)

| # | Columna | Tipo | Nullable | PK | FK | Default |
|---|---------|------|----------|----|----|---------|
| 1 | id | BigInteger | NO | YES |  | nextval('fin.periodo_id_seq'::regclass) |
| 2 | anio | Integer | NO |  |  |  |
| 3 | mes | Integer | NO |  |  |  |
| 4 | estado | String  # USER-DEFINED::periodo_estado | NO |  |  | 'ABIERTO'::fin.periodo_estado |
| 5 | cerrado_at | DateTime | YES |  |  |  |
| 6 | cerrado_por | String  # USER-DEFINED::citext | YES |  |  |  |
| 7 | notas | Text | YES |  |  |  |
| 8 | created_at | DateTime | NO |  |  | now() |
| 9 | updated_at | DateTime | NO |  |  | now() |

**Índices**

- `periodo_pkey`
  - `CREATE UNIQUE INDEX periodo_pkey ON fin.periodo USING btree (id)`
- `ux_periodo`
  - `CREATE UNIQUE INDEX ux_periodo ON fin.periodo USING btree (anio, mes)`

### `fin.plan_cuenta` (table)

| # | Columna | Tipo | Nullable | PK | FK | Default |
|---|---------|------|----------|----|----|---------|
| 1 | id | BigInteger | NO | YES |  | nextval('fin.plan_cuenta_id_seq'::regclass) |
| 2 | codigo | String(30) | NO |  |  |  |
| 3 | nombre | String(180) | NO |  |  |  |
| 4 | nivel | Integer | NO |  |  | 1 |
| 5 | cuenta_padre_id | BigInteger | YES |  | fin.plan_cuenta.id |  |
| 6 | tipo | String(30) | NO |  |  |  |
| 7 | clasificacion | String(50) | NO |  |  |  |
| 8 | naturaleza | String(20) | NO |  |  |  |
| 9 | acepta_movimiento | Boolean | NO |  |  | true |
| 10 | requiere_centro_costo | Boolean | NO |  |  | false |
| 11 | estado | String(20) | NO |  |  | 'ACTIVO'::character varying |
| 12 | descripcion | Text | YES |  |  |  |
| 13 | created_at | DateTime | NO |  |  | now() |
| 14 | updated_at | DateTime | NO |  |  | now() |

**Índices**

- `ix_fin_plan_cuenta_clasificacion`
  - `CREATE INDEX ix_fin_plan_cuenta_clasificacion ON fin.plan_cuenta USING btree (clasificacion)`
- `ix_fin_plan_cuenta_codigo`
  - `CREATE UNIQUE INDEX ix_fin_plan_cuenta_codigo ON fin.plan_cuenta USING btree (codigo)`
- `ix_fin_plan_cuenta_estado`
  - `CREATE INDEX ix_fin_plan_cuenta_estado ON fin.plan_cuenta USING btree (estado)`
- `ix_fin_plan_cuenta_padre`
  - `CREATE INDEX ix_fin_plan_cuenta_padre ON fin.plan_cuenta USING btree (cuenta_padre_id)`
- `ix_fin_plan_cuenta_tipo`
  - `CREATE INDEX ix_fin_plan_cuenta_tipo ON fin.plan_cuenta USING btree (tipo)`
- `pk_plan_cuenta`
  - `CREATE UNIQUE INDEX pk_plan_cuenta ON fin.plan_cuenta USING btree (id)`
- `uq_plan_cuenta_codigo`
  - `CREATE UNIQUE INDEX uq_plan_cuenta_codigo ON fin.plan_cuenta USING btree (codigo)`

### `fin.proveedor_fin` (table)

| # | Columna | Tipo | Nullable | PK | FK | Default |
|---|---------|------|----------|----|----|---------|
| 1 | id | BigInteger | NO | YES |  | nextval('fin.proveedor_fin_id_seq'::regclass) |
| 2 | proveedor_id | BigInteger | NO |  |  |  |
| 3 | condicion_pago_dias | Integer | NO |  |  | 30 |
| 4 | limite_credito | Numeric(18, 2) | NO |  |  | 0 |
| 5 | estado | String  # USER-DEFINED::estado_simple | NO |  |  | 'ACTIVO'::fin.estado_simple |
| 6 | notas | Text | YES |  |  |  |
| 7 | created_at | DateTime | NO |  |  | now() |
| 8 | updated_at | DateTime | NO |  |  | now() |

**Índices**

- `ix_proveedor_fin_estado`
  - `CREATE INDEX ix_proveedor_fin_estado ON fin.proveedor_fin USING btree (estado)`
- `ix_proveedor_fin_proveedor`
  - `CREATE INDEX ix_proveedor_fin_proveedor ON fin.proveedor_fin USING btree (proveedor_id)`
- `proveedor_fin_pkey`
  - `CREATE UNIQUE INDEX proveedor_fin_pkey ON fin.proveedor_fin USING btree (id)`
- `ux_proveedor_fin_proveedor`
  - `CREATE UNIQUE INDEX ux_proveedor_fin_proveedor ON fin.proveedor_fin USING btree (proveedor_id)`

### `fin.vw_config_contable` (view)

| # | Columna | Tipo | Nullable | PK | FK | Default |
|---|---------|------|----------|----|----|---------|
| 1 | id | BigInteger | YES |  |  |  |
| 2 | codigo_evento | String(50) | YES |  |  |  |
| 3 | nombre_evento | String(150) | YES |  |  |  |
| 4 | lado | String(10) | YES |  |  |  |
| 5 | codigo_cuenta | String(30) | YES |  |  |  |
| 6 | nombre_cuenta | String(180) | YES |  |  |  |
| 7 | tipo | String(30) | YES |  |  |  |
| 8 | clasificacion | String(50) | YES |  |  |  |
| 9 | orden | Integer | YES |  |  |  |
| 10 | requiere_centro_costo | Boolean | YES |  |  |  |
| 11 | requiere_documento | Boolean | YES |  |  |  |
| 12 | estado | String(20) | YES |  |  |  |
| 13 | descripcion | Text | YES |  |  |  |

### `fin.vw_config_contable_modulo` (view)

| # | Columna | Tipo | Nullable | PK | FK | Default |
|---|---------|------|----------|----|----|---------|
| 1 | id | BigInteger | YES |  |  |  |
| 2 | modulo | String(50) | YES |  |  |  |
| 3 | submodulo | String(50) | YES |  |  |  |
| 4 | tipo_documento | String(50) | YES |  |  |  |
| 5 | codigo_evento | String(50) | YES |  |  |  |
| 6 | nombre_evento | String(150) | YES |  |  |  |
| 7 | lado | String(10) | YES |  |  |  |
| 8 | codigo_cuenta | String(30) | YES |  |  |  |
| 9 | nombre_cuenta | String(180) | YES |  |  |  |
| 10 | tipo | String(30) | YES |  |  |  |
| 11 | clasificacion | String(50) | YES |  |  |  |
| 12 | orden | Integer | YES |  |  |  |
| 13 | requiere_centro_costo | Boolean | YES |  |  |  |
| 14 | requiere_documento | Boolean | YES |  |  |  |
| 15 | requiere_cliente | Boolean | YES |  |  |  |
| 16 | requiere_proveedor | Boolean | YES |  |  |  |
| 17 | estado | String(20) | YES |  |  |  |
| 18 | descripcion | Text | YES |  |  |  |

### `fin.vw_kpi_dashboard_fin` (view)

| # | Columna | Tipo | Nullable | PK | FK | Default |
|---|---------|------|----------|----|----|---------|
| 1 | docs_total | BigInteger | YES |  |  |  |
| 2 | monto_total | Numeric(18, 2) | YES |  |  |  |
| 3 | saldo_pendiente | Numeric(18, 2) | YES |  |  |  |
| 4 | saldo_vencido | Numeric(18, 2) | YES |  |  |  |
| 5 | pagado_mes | Numeric(18, 2) | YES |  |  |  |
| 6 | gasto_mes | Numeric(18, 2) | YES |  |  |  |

## Esquema `public`

### `public.ap_documento_compra` (table)

| # | Columna | Tipo | Nullable | PK | FK | Default |
|---|---------|------|----------|----|----|---------|
| 1 | id | BigInteger | NO | YES |  | nextval('ap_documento_compra_id_seq'::regclass) |
| 2 | proveedor_id | BigInteger | NO |  |  |  |
| 3 | tipo | String  # USER-DEFINED::ap_documento_tipo | NO |  |  |  |
| 4 | estado | String  # USER-DEFINED::ap_estado_documento | NO |  |  | 'BORRADOR'::ap_estado_documento |
| 5 | folio | String(40) | NO |  |  |  |
| 6 | fecha_emision | Date | NO |  |  |  |
| 7 | fecha_recepcion | Date | YES |  |  |  |
| 8 | fecha_vencimiento | Date | NO |  |  |  |
| 9 | moneda | String(10) | NO |  |  | 'CLP'::character varying |
| 10 | tipo_cambio | Numeric(18, 6) | NO |  |  | 1 |
| 11 | neto | Numeric(18, 2) | NO |  |  | 0 |
| 12 | exento | Numeric(18, 2) | NO |  |  | 0 |
| 13 | iva | Numeric(18, 2) | NO |  |  | 0 |
| 14 | otros_impuestos | Numeric(18, 2) | NO |  |  | 0 |
| 15 | total | Numeric(18, 2) | NO |  |  | 0 |
| 16 | saldo_pendiente | Numeric(18, 2) | NO |  |  | 0 |
| 17 | referencia | String(180) | YES |  |  |  |
| 18 | observaciones | Text | YES |  |  |  |
| 19 | created_at | DateTime | NO |  |  | now() |
| 20 | updated_at | DateTime | NO |  |  | now() |

**Índices**

- `ap_documento_compra_pkey`
  - `CREATE UNIQUE INDEX ap_documento_compra_pkey ON public.ap_documento_compra USING btree (id)`
- `ix_ap_doc_estado`
  - `CREATE INDEX ix_ap_doc_estado ON public.ap_documento_compra USING btree (estado)`
- `ix_ap_doc_fechas`
  - `CREATE INDEX ix_ap_doc_fechas ON public.ap_documento_compra USING btree (fecha_emision, fecha_vencimiento)`
- `ix_ap_doc_proveedor`
  - `CREATE INDEX ix_ap_doc_proveedor ON public.ap_documento_compra USING btree (proveedor_id)`
- `ux_ap_doc_unique`
  - `CREATE UNIQUE INDEX ux_ap_doc_unique ON public.ap_documento_compra USING btree (proveedor_id, tipo, folio)`

### `public.ap_documento_compra_detalle` (table)

| # | Columna | Tipo | Nullable | PK | FK | Default |
|---|---------|------|----------|----|----|---------|
| 1 | id | BigInteger | NO | YES |  | nextval('ap_documento_compra_detalle_id_seq'::regclass) |
| 2 | documento_id | BigInteger | NO |  |  |  |
| 3 | linea | Integer | NO |  |  |  |
| 4 | descripcion | String(260) | NO |  |  |  |
| 5 | cantidad | Numeric(18, 6) | NO |  |  | 1 |
| 6 | precio_unitario | Numeric(18, 6) | NO |  |  | 0 |
| 7 | descuento | Numeric(18, 2) | NO |  |  | 0 |
| 8 | neto_linea | Numeric(18, 2) | NO |  |  | 0 |
| 9 | iva_linea | Numeric(18, 2) | NO |  |  | 0 |
| 10 | otros_impuestos | Numeric(18, 2) | NO |  |  | 0 |
| 11 | total_linea | Numeric(18, 2) | NO |  |  | 0 |
| 12 | categoria_gasto_id | BigInteger | YES |  |  |  |
| 13 | centro_costo_id | BigInteger | YES |  |  |  |
| 14 | created_at | DateTime | NO |  |  | now() |
| 15 | updated_at | DateTime | NO |  |  | now() |

**Índices**

- `ap_documento_compra_detalle_pkey`
  - `CREATE UNIQUE INDEX ap_documento_compra_detalle_pkey ON public.ap_documento_compra_detalle USING btree (id)`
- `ix_ap_doc_det_categoria`
  - `CREATE INDEX ix_ap_doc_det_categoria ON public.ap_documento_compra_detalle USING btree (categoria_gasto_id)`
- `ix_ap_doc_det_centro`
  - `CREATE INDEX ix_ap_doc_det_centro ON public.ap_documento_compra_detalle USING btree (centro_costo_id)`
- `ix_ap_doc_det_documento`
  - `CREATE INDEX ix_ap_doc_det_documento ON public.ap_documento_compra_detalle USING btree (documento_id)`
- `ux_ap_doc_det_linea`
  - `CREATE UNIQUE INDEX ux_ap_doc_det_linea ON public.ap_documento_compra_detalle USING btree (documento_id, linea)`

### `public.ap_pago` (table)

| # | Columna | Tipo | Nullable | PK | FK | Default |
|---|---------|------|----------|----|----|---------|
| 1 | id | BigInteger | NO | YES |  | nextval('ap_pago_id_seq'::regclass) |
| 2 | proveedor_id | BigInteger | NO |  |  |  |
| 3 | estado | String  # USER-DEFINED::ap_estado_pago | NO |  |  | 'BORRADOR'::ap_estado_pago |
| 4 | fecha_pago | Date | NO |  |  |  |
| 5 | medio_pago | String  # USER-DEFINED::fin_medio_pago | NO |  |  | 'TRANSFERENCIA'::fin_medio_pago |
| 6 | referencia | String(180) | YES |  |  |  |
| 7 | moneda | String(10) | NO |  |  | 'CLP'::character varying |
| 8 | tipo_cambio | Numeric(18, 6) | NO |  |  | 1 |
| 9 | monto_total | Numeric(18, 2) | NO |  |  | 0 |
| 10 | observaciones | Text | YES |  |  |  |
| 11 | created_at | DateTime | NO |  |  | now() |
| 12 | updated_at | DateTime | NO |  |  | now() |

**Índices**

- `ap_pago_pkey`
  - `CREATE UNIQUE INDEX ap_pago_pkey ON public.ap_pago USING btree (id)`
- `ix_ap_pago_estado`
  - `CREATE INDEX ix_ap_pago_estado ON public.ap_pago USING btree (estado)`
- `ix_ap_pago_fecha`
  - `CREATE INDEX ix_ap_pago_fecha ON public.ap_pago USING btree (fecha_pago)`
- `ix_ap_pago_proveedor`
  - `CREATE INDEX ix_ap_pago_proveedor ON public.ap_pago USING btree (proveedor_id)`

### `public.ap_pago_aplicacion` (table)

| # | Columna | Tipo | Nullable | PK | FK | Default |
|---|---------|------|----------|----|----|---------|
| 1 | id | BigInteger | NO | YES |  | nextval('ap_pago_aplicacion_id_seq'::regclass) |
| 2 | pago_id | BigInteger | NO |  |  |  |
| 3 | documento_id | BigInteger | NO |  |  |  |
| 4 | monto_aplicado | Numeric(18, 2) | NO |  |  | 0 |
| 5 | created_at | DateTime | NO |  |  | now() |

**Índices**

- `ap_pago_aplicacion_pkey`
  - `CREATE UNIQUE INDEX ap_pago_aplicacion_pkey ON public.ap_pago_aplicacion USING btree (id)`
- `ix_ap_pago_apl_doc`
  - `CREATE INDEX ix_ap_pago_apl_doc ON public.ap_pago_aplicacion USING btree (documento_id)`
- `ix_ap_pago_apl_pago`
  - `CREATE INDEX ix_ap_pago_apl_pago ON public.ap_pago_aplicacion USING btree (pago_id)`
- `ux_ap_pago_doc`
  - `CREATE UNIQUE INDEX ux_ap_pago_doc ON public.ap_pago_aplicacion USING btree (pago_id, documento_id)`

### `public.asientos_contables` (table)

| # | Columna | Tipo | Nullable | PK | FK | Default |
|---|---------|------|----------|----|----|---------|
| 1 | id | BigInteger | NO | YES |  | nextval('asientos_contables_id_seq'::regclass) |
| 2 | fecha | Date | NO |  |  |  |
| 3 | descripcion | Text | YES |  |  |  |
| 4 | origen_tipo | String(30) | YES |  |  |  |
| 5 | origen_id | BigInteger | YES |  |  |  |
| 6 | fecha_creacion | DateTime | NO |  |  |  |
| 7 | glosa | String(255) | YES |  |  |  |

**Índices**

- `asientos_contables_pkey`
  - `CREATE UNIQUE INDEX asientos_contables_pkey ON public.asientos_contables USING btree (id)`
- `ix_asientos_contables_id`
  - `CREATE INDEX ix_asientos_contables_id ON public.asientos_contables USING btree (id)`

### `public.asientos_detalle` (table)

| # | Columna | Tipo | Nullable | PK | FK | Default |
|---|---------|------|----------|----|----|---------|
| 1 | id | BigInteger | NO | YES |  | nextval('asientos_detalle_id_seq'::regclass) |
| 2 | asiento_id | BigInteger | NO |  | public.asientos_contables.id |  |
| 3 | cuenta_contable | String(50) | YES |  |  |  |
| 4 | descripcion | String(255) | YES |  |  |  |
| 5 | debe | Numeric(14, 2) | NO |  |  |  |
| 6 | haber | Numeric(14, 2) | NO |  |  |  |
| 7 | codigo_cuenta | String(20) | NO |  |  |  |
| 8 | nombre_cuenta | String(255) | NO |  |  |  |

**Índices**

- `asientos_detalle_pkey`
  - `CREATE UNIQUE INDEX asientos_detalle_pkey ON public.asientos_detalle USING btree (id)`
- `ix_asientos_detalle_id`
  - `CREATE INDEX ix_asientos_detalle_id ON public.asientos_detalle USING btree (id)`

### `public.cajas` (table)

| # | Columna | Tipo | Nullable | PK | FK | Default |
|---|---------|------|----------|----|----|---------|
| 1 | id | BigInteger | NO | YES |  | nextval('cajas_id_seq'::regclass) |
| 2 | nombre | String(100) | NO |  |  |  |
| 3 | descripcion | String(255) | YES |  |  |  |
| 4 | saldo_inicial | Numeric(14, 2) | NO |  |  |  |
| 5 | saldo_actual | Numeric(14, 2) | NO |  |  |  |
| 6 | fecha_apertura | DateTime | YES |  |  |  |
| 7 | fecha_cierre | DateTime | YES |  |  |  |
| 8 | estado | String(20) | NO |  |  |  |
| 9 | activa | Boolean | NO |  |  |  |

**Índices**

- `cajas_pkey`
  - `CREATE UNIQUE INDEX cajas_pkey ON public.cajas USING btree (id)`
- `ix_cajas_id`
  - `CREATE INDEX ix_cajas_id ON public.cajas USING btree (id)`

### `public.categorias_producto` (table)

| # | Columna | Tipo | Nullable | PK | FK | Default |
|---|---------|------|----------|----|----|---------|
| 1 | id | BigInteger | NO | YES |  | nextval('categorias_producto_id_seq'::regclass) |
| 2 | nombre | String(150) | NO |  |  |  |
| 3 | descripcion | Text | YES |  |  |  |
| 4 | activo | Boolean | NO |  |  |  |
| 5 | fecha_creacion | DateTime | NO |  |  |  |

**Índices**

- `categorias_producto_nombre_key`
  - `CREATE UNIQUE INDEX categorias_producto_nombre_key ON public.categorias_producto USING btree (nombre)`
- `categorias_producto_pkey`
  - `CREATE UNIQUE INDEX categorias_producto_pkey ON public.categorias_producto USING btree (id)`
- `ix_categorias_producto_id`
  - `CREATE INDEX ix_categorias_producto_id ON public.categorias_producto USING btree (id)`

### `public.clientes` (table)

| # | Columna | Tipo | Nullable | PK | FK | Default |
|---|---------|------|----------|----|----|---------|
| 1 | id | BigInteger | NO | YES |  | nextval('clientes_id_seq'::regclass) |
| 2 | rut | String(20) | NO |  |  |  |
| 3 | razon_social | String(200) | NO |  |  |  |
| 4 | nombre_fantasia | String(200) | YES |  |  |  |
| 5 | giro | String(200) | YES |  |  |  |
| 6 | direccion | String(250) | YES |  |  |  |
| 7 | comuna | String(100) | YES |  |  |  |
| 8 | ciudad | String(100) | YES |  |  |  |
| 9 | telefono | String(50) | YES |  |  |  |
| 10 | email | String(150) | YES |  |  |  |
| 11 | activo | Boolean | NO |  |  |  |
| 12 | fecha_creacion | DateTime | NO |  |  |  |
| 13 | fecha_actualizacion | DateTime | NO |  |  |  |

**Índices**

- `clientes_pkey`
  - `CREATE UNIQUE INDEX clientes_pkey ON public.clientes USING btree (id)`
- `ix_clientes_id`
  - `CREATE INDEX ix_clientes_id ON public.clientes USING btree (id)`
- `ix_clientes_rut`
  - `CREATE UNIQUE INDEX ix_clientes_rut ON public.clientes USING btree (rut)`

### `public.cuentas_por_cobrar` (table)

| # | Columna | Tipo | Nullable | PK | FK | Default |
|---|---------|------|----------|----|----|---------|
| 1 | id | BigInteger | NO | YES |  | nextval('cuentas_por_cobrar_id_seq'::regclass) |
| 2 | cliente_id | BigInteger | NO |  | public.clientes.id |  |
| 3 | nota_venta_id | BigInteger | YES |  | public.notas_venta.id |  |
| 4 | fecha_emision | Date | NO |  |  |  |
| 5 | fecha_vencimiento | Date | NO |  |  |  |
| 6 | monto_original | Numeric(14, 2) | NO |  |  |  |
| 7 | saldo_pendiente | Numeric(14, 2) | NO |  |  |  |
| 8 | estado | String(20) | NO |  |  |  |
| 9 | observacion | Text | YES |  |  |  |
| 10 | fecha_creacion | DateTime | NO |  |  |  |
| 11 | fecha_actualizacion | DateTime | NO |  |  |  |
| 12 | razon_social | String(255) | YES |  |  |  |

**Índices**

- `cuentas_por_cobrar_pkey`
  - `CREATE UNIQUE INDEX cuentas_por_cobrar_pkey ON public.cuentas_por_cobrar USING btree (id)`
- `ix_cuentas_por_cobrar_id`
  - `CREATE INDEX ix_cuentas_por_cobrar_id ON public.cuentas_por_cobrar USING btree (id)`

### `public.cuentas_por_pagar` (table)

| # | Columna | Tipo | Nullable | PK | FK | Default |
|---|---------|------|----------|----|----|---------|
| 1 | id | BigInteger | NO | YES |  | nextval('cuentas_por_pagar_id_seq'::regclass) |
| 2 | proveedor_id | BigInteger | NO |  | public.proveedores.id |  |
| 3 | factura_compra_id | BigInteger | YES |  | public.facturas_compra.id |  |
| 4 | fecha_emision | Date | NO |  |  |  |
| 5 | fecha_vencimiento | Date | NO |  |  |  |
| 6 | monto_original | Numeric(14, 2) | NO |  |  |  |
| 7 | saldo_pendiente | Numeric(14, 2) | NO |  |  |  |
| 8 | estado | String(20) | NO |  |  |  |
| 9 | observacion | Text | YES |  |  |  |
| 10 | fecha_creacion | DateTime | NO |  |  |  |
| 11 | fecha_actualizacion | DateTime | NO |  |  |  |

**Índices**

- `cuentas_por_pagar_pkey`
  - `CREATE UNIQUE INDEX cuentas_por_pagar_pkey ON public.cuentas_por_pagar USING btree (id)`
- `ix_cuentas_por_pagar_id`
  - `CREATE INDEX ix_cuentas_por_pagar_id ON public.cuentas_por_pagar USING btree (id)`

### `public.email_log` (table)

| # | Columna | Tipo | Nullable | PK | FK | Default |
|---|---------|------|----------|----|----|---------|
| 1 | id | Integer | NO | YES |  | nextval('email_log_id_seq'::regclass) |
| 2 | created_at | DateTime | NO |  |  | CURRENT_TIMESTAMP |
| 3 | modulo | String(50) | NO |  |  | 'COBRANZA'::character varying |
| 4 | evento | String(50) | NO |  |  | 'RECORDATORIO'::character varying |
| 5 | cliente_id | Integer | YES |  |  |  |
| 6 | cxc_id | Integer | YES |  |  |  |
| 7 | to_email | String(255) | NO |  |  |  |
| 8 | subject | String(255) | NO |  |  |  |
| 9 | include_detalle | Boolean | NO |  |  | true |
| 10 | status | String(20) | NO |  |  | 'PENDIENTE'::character varying |
| 11 | sent_at | DateTime | YES |  |  |  |
| 12 | error_message | Text | YES |  |  |  |
| 13 | meta_json | Text | YES |  |  |  |

**Índices**

- `email_log_pkey`
  - `CREATE UNIQUE INDEX email_log_pkey ON public.email_log USING btree (id)`
- `ix_email_log_cliente_id`
  - `CREATE INDEX ix_email_log_cliente_id ON public.email_log USING btree (cliente_id)`
- `ix_email_log_created_at`
  - `CREATE INDEX ix_email_log_created_at ON public.email_log USING btree (created_at)`
- `ix_email_log_status`
  - `CREATE INDEX ix_email_log_status ON public.email_log USING btree (status)`

### `public.facturas_compra` (table)

| # | Columna | Tipo | Nullable | PK | FK | Default |
|---|---------|------|----------|----|----|---------|
| 1 | id | BigInteger | NO | YES |  | nextval('facturas_compra_id_seq'::regclass) |
| 2 | proveedor_id | BigInteger | NO |  | public.proveedores.id |  |
| 3 | numero_documento | String(50) | NO |  |  |  |
| 4 | fecha_emision | Date | NO |  |  |  |
| 5 | fecha_vencimiento | Date | YES |  |  |  |
| 6 | neto | Numeric(14, 2) | NO |  |  |  |
| 7 | iva | Numeric(14, 2) | NO |  |  |  |
| 8 | total | Numeric(14, 2) | NO |  |  |  |
| 9 | estado | String(20) | NO |  |  |  |
| 10 | observacion | Text | YES |  |  |  |
| 11 | fecha_creacion | DateTime | NO |  |  |  |
| 12 | fecha_actualizacion | DateTime | NO |  |  |  |

**Índices**

- `facturas_compra_pkey`
  - `CREATE UNIQUE INDEX facturas_compra_pkey ON public.facturas_compra USING btree (id)`
- `ix_facturas_compra_id`
  - `CREATE INDEX ix_facturas_compra_id ON public.facturas_compra USING btree (id)`

### `public.facturas_compra_detalle` (table)

| # | Columna | Tipo | Nullable | PK | FK | Default |
|---|---------|------|----------|----|----|---------|
| 1 | id | BigInteger | NO | YES |  | nextval('facturas_compra_detalle_id_seq'::regclass) |
| 2 | factura_compra_id | BigInteger | NO |  | public.facturas_compra.id |  |
| 3 | producto_id | BigInteger | YES |  | public.productos.id |  |
| 4 | descripcion | String(250) | YES |  |  |  |
| 5 | cantidad | Numeric(14, 2) | NO |  |  |  |
| 6 | costo_unitario | Numeric(14, 4) | NO |  |  |  |
| 7 | subtotal | Numeric(14, 2) | NO |  |  |  |

**Índices**

- `facturas_compra_detalle_pkey`
  - `CREATE UNIQUE INDEX facturas_compra_detalle_pkey ON public.facturas_compra_detalle USING btree (id)`
- `ix_facturas_compra_detalle_id`
  - `CREATE INDEX ix_facturas_compra_detalle_id ON public.facturas_compra_detalle USING btree (id)`

### `public.fin_adjunto` (table)

| # | Columna | Tipo | Nullable | PK | FK | Default |
|---|---------|------|----------|----|----|---------|
| 1 | id | BigInteger | NO | YES |  | nextval('fin_adjunto_id_seq'::regclass) |
| 2 | entidad | String(40) | NO |  |  |  |
| 3 | entidad_id | BigInteger | NO |  |  |  |
| 4 | nombre | String(220) | NO |  |  |  |
| 5 | mime | String(120) | YES |  |  |  |
| 6 | storage_path | String(500) | NO |  |  |  |
| 7 | hash_sha256 | String(80) | YES |  |  |  |
| 8 | created_at | DateTime | NO |  |  | now() |

**Índices**

- `fin_adjunto_pkey`
  - `CREATE UNIQUE INDEX fin_adjunto_pkey ON public.fin_adjunto USING btree (id)`
- `ix_fin_adjunto_entidad`
  - `CREATE INDEX ix_fin_adjunto_entidad ON public.fin_adjunto USING btree (entidad, entidad_id)`

### `public.fin_categoria_gasto` (table)

| # | Columna | Tipo | Nullable | PK | FK | Default |
|---|---------|------|----------|----|----|---------|
| 1 | id | BigInteger | NO | YES |  | nextval('fin_categoria_gasto_id_seq'::regclass) |
| 2 | codigo | String(30) | NO |  |  |  |
| 3 | nombre | String(160) | NO |  |  |  |
| 4 | tipo | String  # USER-DEFINED::fin_tipo_gasto | NO |  |  | 'OPERACIONAL'::fin_tipo_gasto |
| 5 | activo | Boolean | NO |  |  | true |
| 6 | created_at | DateTime | NO |  |  | now() |
| 7 | updated_at | DateTime | NO |  |  | now() |

**Índices**

- `fin_categoria_gasto_pkey`
  - `CREATE UNIQUE INDEX fin_categoria_gasto_pkey ON public.fin_categoria_gasto USING btree (id)`
- `ux_cat_gasto_codigo`
  - `CREATE UNIQUE INDEX ux_cat_gasto_codigo ON public.fin_categoria_gasto USING btree (codigo)`

### `public.fin_centro_costo` (table)

| # | Columna | Tipo | Nullable | PK | FK | Default |
|---|---------|------|----------|----|----|---------|
| 1 | id | BigInteger | NO | YES |  | nextval('fin_centro_costo_id_seq'::regclass) |
| 2 | codigo | String(30) | NO |  |  |  |
| 3 | nombre | String(120) | NO |  |  |  |
| 4 | activo | Boolean | NO |  |  | true |
| 5 | created_at | DateTime | NO |  |  | now() |
| 6 | updated_at | DateTime | NO |  |  | now() |

**Índices**

- `fin_centro_costo_pkey`
  - `CREATE UNIQUE INDEX fin_centro_costo_pkey ON public.fin_centro_costo USING btree (id)`
- `ux_centro_costo_codigo`
  - `CREATE UNIQUE INDEX ux_centro_costo_codigo ON public.fin_centro_costo USING btree (codigo)`

### `public.fin_evento` (table)

| # | Columna | Tipo | Nullable | PK | FK | Default |
|---|---------|------|----------|----|----|---------|
| 1 | id | BigInteger | NO | YES |  | nextval('fin_evento_id_seq'::regclass) |
| 2 | entidad | String(40) | NO |  |  |  |
| 3 | entidad_id | BigInteger | NO |  |  |  |
| 4 | evento | String(80) | NO |  |  |  |
| 5 | detalle | Text | YES |  |  |  |
| 6 | user_email | String(180) | YES |  |  |  |
| 7 | ip_origen | String(80) | YES |  |  |  |
| 8 | created_at | DateTime | NO |  |  | now() |

**Índices**

- `fin_evento_pkey`
  - `CREATE UNIQUE INDEX fin_evento_pkey ON public.fin_evento USING btree (id)`
- `ix_fin_evento_entidad`
  - `CREATE INDEX ix_fin_evento_entidad ON public.fin_evento USING btree (entidad, entidad_id)`
- `ix_fin_evento_fecha`
  - `CREATE INDEX ix_fin_evento_fecha ON public.fin_evento USING btree (created_at)`

### `public.fin_gasto` (table)

| # | Columna | Tipo | Nullable | PK | FK | Default |
|---|---------|------|----------|----|----|---------|
| 1 | id | BigInteger | NO | YES |  | nextval('fin_gasto_id_seq'::regclass) |
| 2 | estado | String  # USER-DEFINED::fin_estado_gasto | NO |  |  | 'BORRADOR'::fin_estado_gasto |
| 3 | fecha | Date | NO |  |  |  |
| 4 | proveedor_id | BigInteger | YES |  |  |  |
| 5 | documento_ref | String(80) | YES |  |  |  |
| 6 | categoria_gasto_id | BigInteger | NO |  |  |  |
| 7 | centro_costo_id | BigInteger | YES |  |  |  |
| 8 | medio_pago | String  # USER-DEFINED::fin_medio_pago | NO |  |  | 'OTRO'::fin_medio_pago |
| 9 | moneda | String(10) | NO |  |  | 'CLP'::character varying |
| 10 | tipo_cambio | Numeric(18, 6) | NO |  |  | 1 |
| 11 | neto | Numeric(18, 2) | NO |  |  | 0 |
| 12 | exento | Numeric(18, 2) | NO |  |  | 0 |
| 13 | iva | Numeric(18, 2) | NO |  |  | 0 |
| 14 | otros_impuestos | Numeric(18, 2) | NO |  |  | 0 |
| 15 | total | Numeric(18, 2) | NO |  |  | 0 |
| 16 | descripcion | String(260) | NO |  |  |  |
| 17 | observaciones | Text | YES |  |  |  |
| 18 | created_at | DateTime | NO |  |  | now() |
| 19 | updated_at | DateTime | NO |  |  | now() |

**Índices**

- `fin_gasto_pkey`
  - `CREATE UNIQUE INDEX fin_gasto_pkey ON public.fin_gasto USING btree (id)`
- `ix_fin_gasto_categoria`
  - `CREATE INDEX ix_fin_gasto_categoria ON public.fin_gasto USING btree (categoria_gasto_id)`
- `ix_fin_gasto_centro`
  - `CREATE INDEX ix_fin_gasto_centro ON public.fin_gasto USING btree (centro_costo_id)`
- `ix_fin_gasto_estado`
  - `CREATE INDEX ix_fin_gasto_estado ON public.fin_gasto USING btree (estado)`
- `ix_fin_gasto_fecha`
  - `CREATE INDEX ix_fin_gasto_fecha ON public.fin_gasto USING btree (fecha)`
- `ix_fin_gasto_proveedor`
  - `CREATE INDEX ix_fin_gasto_proveedor ON public.fin_gasto USING btree (proveedor_id)`

### `public.inventario_movimientos` (table)

| # | Columna | Tipo | Nullable | PK | FK | Default |
|---|---------|------|----------|----|----|---------|
| 1 | id | BigInteger | NO | YES |  | nextval('inventario_movimientos_id_seq'::regclass) |
| 2 | producto_id | BigInteger | NO |  | public.productos.id |  |
| 3 | fecha | DateTime | NO |  |  |  |
| 4 | tipo_movimiento | String(20) | NO |  |  |  |
| 5 | cantidad | Numeric(14, 2) | NO |  |  |  |
| 6 | costo_unitario | Numeric(14, 4) | NO |  |  |  |
| 7 | referencia_tipo | String(30) | YES |  |  |  |
| 8 | referencia_id | BigInteger | YES |  |  |  |
| 9 | observacion | Text | YES |  |  |  |

**Índices**

- `inventario_movimientos_pkey`
  - `CREATE UNIQUE INDEX inventario_movimientos_pkey ON public.inventario_movimientos USING btree (id)`
- `ix_inventario_movimientos_id`
  - `CREATE INDEX ix_inventario_movimientos_id ON public.inventario_movimientos USING btree (id)`

### `public.movimientos_caja` (table)

| # | Columna | Tipo | Nullable | PK | FK | Default |
|---|---------|------|----------|----|----|---------|
| 1 | id | BigInteger | NO | YES |  | nextval('movimientos_caja_id_seq'::regclass) |
| 2 | caja_id | BigInteger | NO |  | public.cajas.id |  |
| 3 | fecha | DateTime | NO |  |  |  |
| 4 | tipo_movimiento | String(20) | NO |  |  |  |
| 5 | medio_pago | String(20) | NO |  |  |  |
| 6 | monto | Numeric(14, 2) | NO |  |  |  |
| 7 | referencia_tipo | String(30) | YES |  |  |  |
| 8 | referencia_id | BigInteger | YES |  |  |  |
| 9 | observacion | Text | YES |  |  |  |

**Índices**

- `ix_movimientos_caja_id`
  - `CREATE INDEX ix_movimientos_caja_id ON public.movimientos_caja USING btree (id)`
- `movimientos_caja_pkey`
  - `CREATE UNIQUE INDEX movimientos_caja_pkey ON public.movimientos_caja USING btree (id)`

### `public.notas_venta` (table)

| # | Columna | Tipo | Nullable | PK | FK | Default |
|---|---------|------|----------|----|----|---------|
| 1 | id | BigInteger | NO | YES |  | nextval('notas_venta_id_seq'::regclass) |
| 2 | numero | String(50) | NO |  |  |  |
| 3 | fecha | DateTime | NO |  |  |  |
| 4 | cliente_id | BigInteger | YES |  | public.clientes.id |  |
| 5 | caja_id | BigInteger | YES |  | public.cajas.id |  |
| 6 | tipo_pago | String(20) | NO |  |  |  |
| 7 | estado | String(20) | NO |  |  |  |
| 8 | subtotal_neto | Numeric(14, 2) | NO |  |  |  |
| 9 | descuento_total | Numeric(14, 2) | NO |  |  |  |
| 10 | total_neto | Numeric(14, 2) | NO |  |  |  |
| 11 | total_iva | Numeric(14, 2) | NO |  |  |  |
| 12 | total_total | Numeric(14, 2) | NO |  |  |  |
| 13 | observacion | Text | YES |  |  |  |
| 14 | usuario_emisor | String(100) | YES |  |  |  |
| 15 | fecha_creacion | DateTime | NO |  |  |  |
| 16 | fecha_actualizacion | DateTime | NO |  |  |  |
| 17 | fecha_vencimiento | Date | NO |  |  |  |

**Índices**

- `ix_notas_venta_fecha_vencimiento`
  - `CREATE INDEX ix_notas_venta_fecha_vencimiento ON public.notas_venta USING btree (fecha_vencimiento)`
- `ix_notas_venta_id`
  - `CREATE INDEX ix_notas_venta_id ON public.notas_venta USING btree (id)`
- `ix_notas_venta_numero`
  - `CREATE UNIQUE INDEX ix_notas_venta_numero ON public.notas_venta USING btree (numero)`
- `notas_venta_pkey`
  - `CREATE UNIQUE INDEX notas_venta_pkey ON public.notas_venta USING btree (id)`

### `public.notas_venta_detalle` (table)

| # | Columna | Tipo | Nullable | PK | FK | Default |
|---|---------|------|----------|----|----|---------|
| 1 | id | BigInteger | NO | YES |  | nextval('notas_venta_detalle_id_seq'::regclass) |
| 2 | nota_venta_id | BigInteger | NO |  | public.notas_venta.id |  |
| 3 | producto_id | BigInteger | YES |  | public.productos.id |  |
| 4 | descripcion | String(250) | YES |  |  |  |
| 5 | cantidad | Numeric(14, 2) | NO |  |  |  |
| 6 | precio_unitario | Numeric(14, 2) | NO |  |  |  |
| 7 | descuento_porcentaje | Numeric(5, 2) | NO |  |  |  |
| 8 | descuento_monto | Numeric(14, 2) | NO |  |  |  |
| 9 | subtotal | Numeric(14, 2) | NO |  |  |  |

**Índices**

- `ix_notas_venta_detalle_id`
  - `CREATE INDEX ix_notas_venta_detalle_id ON public.notas_venta_detalle USING btree (id)`
- `notas_venta_detalle_pkey`
  - `CREATE UNIQUE INDEX notas_venta_detalle_pkey ON public.notas_venta_detalle USING btree (id)`

### `public.pagos_clientes` (table)

| # | Columna | Tipo | Nullable | PK | FK | Default |
|---|---------|------|----------|----|----|---------|
| 1 | id | BigInteger | NO | YES |  | nextval('pagos_clientes_id_seq'::regclass) |
| 2 | cuenta_cobrar_id | BigInteger | NO |  | public.cuentas_por_cobrar.id |  |
| 3 | fecha_pago | DateTime | NO |  |  |  |
| 4 | monto_pago | Numeric(14, 2) | NO |  |  |  |
| 6 | caja_id | BigInteger | YES |  | public.cajas.id |  |
| 7 | referencia | String(100) | YES |  |  |  |
| 8 | observacion | Text | YES |  |  |  |
| 9 | forma_pago | Text | YES |  |  |  |

**Índices**

- `ix_pagos_clientes_id`
  - `CREATE INDEX ix_pagos_clientes_id ON public.pagos_clientes USING btree (id)`
- `pagos_clientes_pkey`
  - `CREATE UNIQUE INDEX pagos_clientes_pkey ON public.pagos_clientes USING btree (id)`

### `public.pagos_proveedores` (table)

| # | Columna | Tipo | Nullable | PK | FK | Default |
|---|---------|------|----------|----|----|---------|
| 1 | id | BigInteger | NO | YES |  | nextval('pagos_proveedores_id_seq'::regclass) |
| 2 | cuenta_pagar_id | BigInteger | NO |  | public.cuentas_por_pagar.id |  |
| 3 | fecha_pago | DateTime | NO |  |  |  |
| 4 | monto_pago | Numeric(14, 2) | NO |  |  |  |
| 5 | medio_pago | String(20) | NO |  |  |  |
| 6 | referencia | String(100) | YES |  |  |  |
| 7 | observacion | Text | YES |  |  |  |

**Índices**

- `ix_pagos_proveedores_id`
  - `CREATE INDEX ix_pagos_proveedores_id ON public.pagos_proveedores USING btree (id)`
- `pagos_proveedores_pkey`
  - `CREATE UNIQUE INDEX pagos_proveedores_pkey ON public.pagos_proveedores USING btree (id)`

### `public.productos` (table)

| # | Columna | Tipo | Nullable | PK | FK | Default |
|---|---------|------|----------|----|----|---------|
| 1 | id | BigInteger | NO | YES |  | nextval('productos_id_seq'::regclass) |
| 2 | codigo | String(50) | NO |  |  |  |
| 3 | nombre | String(200) | NO |  |  |  |
| 4 | descripcion | Text | YES |  |  |  |
| 5 | categoria_id | BigInteger | YES |  | public.categorias_producto.id |  |
| 6 | unidad_medida_id | BigInteger | YES |  | public.unidades_medida.id |  |
| 7 | precio_compra | Numeric(14, 2) | NO |  |  |  |
| 8 | precio_venta | Numeric(14, 2) | NO |  |  |  |
| 9 | stock_minimo | Numeric(14, 2) | NO |  |  |  |
| 10 | stock_actual | Numeric(14, 2) | NO |  |  |  |
| 11 | activo | Boolean | NO |  |  |  |
| 12 | fecha_creacion | DateTime | NO |  |  |  |
| 13 | fecha_actualizacion | DateTime | NO |  |  |  |
| 14 | codigo_barra | String(80) | YES |  |  |  |
| 15 | controla_stock | Boolean | NO |  |  | true |
| 16 | permite_venta_fraccionada | Boolean | NO |  |  | false |
| 17 | es_servicio | Boolean | NO |  |  | false |

**Índices**

- `ix_productos_codigo`
  - `CREATE UNIQUE INDEX ix_productos_codigo ON public.productos USING btree (codigo)`
- `ix_productos_codigo_barra`
  - `CREATE INDEX ix_productos_codigo_barra ON public.productos USING btree (codigo_barra)`
- `ix_productos_id`
  - `CREATE INDEX ix_productos_id ON public.productos USING btree (id)`
- `productos_pkey`
  - `CREATE UNIQUE INDEX productos_pkey ON public.productos USING btree (id)`
- `ux_productos_codigo_barra`
  - `CREATE UNIQUE INDEX ux_productos_codigo_barra ON public.productos USING btree (codigo_barra) WHERE (codigo_barra IS NOT NULL)`

### `public.proveedor` (table)

| # | Columna | Tipo | Nullable | PK | FK | Default |
|---|---------|------|----------|----|----|---------|
| 1 | id | BigInteger | NO | YES |  | nextval('proveedor_id_seq'::regclass) |
| 2 | rut | String(20) | NO |  |  |  |
| 3 | rut_normalizado | String(20) | YES |  |  |  |
| 4 | razon_social | String(180) | NO |  |  |  |
| 5 | nombre_fantasia | String(180) | YES |  |  |  |
| 6 | giro | String(180) | YES |  |  |  |
| 7 | email | String(180) | YES |  |  |  |
| 8 | telefono | String(50) | YES |  |  |  |
| 9 | sitio_web | String(180) | YES |  |  |  |
| 10 | condicion_pago_dias | Integer | NO |  |  | 30 |
| 11 | limite_credito | Numeric(18, 2) | NO |  |  | 0 |
| 12 | activo | Boolean | NO |  |  | true |
| 13 | notas | Text | YES |  |  |  |
| 14 | created_at | DateTime | NO |  |  | now() |
| 15 | updated_at | DateTime | NO |  |  | now() |

**Índices**

- `ix_proveedor_razon_social`
  - `CREATE INDEX ix_proveedor_razon_social ON public.proveedor USING btree (razon_social)`
- `proveedor_pkey`
  - `CREATE UNIQUE INDEX proveedor_pkey ON public.proveedor USING btree (id)`
- `ux_proveedor_rut_normalizado`
  - `CREATE UNIQUE INDEX ux_proveedor_rut_normalizado ON public.proveedor USING btree (rut_normalizado)`

### `public.proveedor_banco` (table)

| # | Columna | Tipo | Nullable | PK | FK | Default |
|---|---------|------|----------|----|----|---------|
| 1 | id | BigInteger | NO | YES |  | nextval('proveedor_banco_id_seq'::regclass) |
| 2 | proveedor_id | BigInteger | NO |  |  |  |
| 3 | banco | String(120) | NO |  |  |  |
| 4 | tipo_cuenta | String(60) | NO |  |  |  |
| 5 | numero_cuenta | String(60) | NO |  |  |  |
| 6 | titular | String(180) | YES |  |  |  |
| 7 | rut_titular | String(20) | YES |  |  |  |
| 8 | email_pago | String(180) | YES |  |  |  |
| 9 | es_principal | Boolean | NO |  |  | false |
| 10 | activo | Boolean | NO |  |  | true |
| 11 | created_at | DateTime | NO |  |  | now() |
| 12 | updated_at | DateTime | NO |  |  | now() |

**Índices**

- `ix_prov_banco_proveedor`
  - `CREATE INDEX ix_prov_banco_proveedor ON public.proveedor_banco USING btree (proveedor_id)`
- `proveedor_banco_pkey`
  - `CREATE UNIQUE INDEX proveedor_banco_pkey ON public.proveedor_banco USING btree (id)`
- `ux_prov_banco_unique`
  - `CREATE UNIQUE INDEX ux_prov_banco_unique ON public.proveedor_banco USING btree (proveedor_id, banco, tipo_cuenta, numero_cuenta)`

### `public.proveedor_contacto` (table)

| # | Columna | Tipo | Nullable | PK | FK | Default |
|---|---------|------|----------|----|----|---------|
| 1 | id | BigInteger | NO | YES |  | nextval('proveedor_contacto_id_seq'::regclass) |
| 2 | proveedor_id | BigInteger | NO |  |  |  |
| 3 | nombre | String(120) | NO |  |  |  |
| 4 | cargo | String(120) | YES |  |  |  |
| 5 | email | String(180) | YES |  |  |  |
| 6 | telefono | String(50) | YES |  |  |  |
| 7 | es_principal | Boolean | NO |  |  | false |
| 8 | activo | Boolean | NO |  |  | true |
| 9 | created_at | DateTime | NO |  |  | now() |
| 10 | updated_at | DateTime | NO |  |  | now() |

**Índices**

- `ix_prov_contacto_proveedor`
  - `CREATE INDEX ix_prov_contacto_proveedor ON public.proveedor_contacto USING btree (proveedor_id)`
- `proveedor_contacto_pkey`
  - `CREATE UNIQUE INDEX proveedor_contacto_pkey ON public.proveedor_contacto USING btree (id)`

### `public.proveedor_direccion` (table)

| # | Columna | Tipo | Nullable | PK | FK | Default |
|---|---------|------|----------|----|----|---------|
| 1 | id | BigInteger | NO | YES |  | nextval('proveedor_direccion_id_seq'::regclass) |
| 2 | proveedor_id | BigInteger | NO |  |  |  |
| 3 | linea1 | String(180) | NO |  |  |  |
| 4 | linea2 | String(180) | YES |  |  |  |
| 5 | comuna | String(120) | YES |  |  |  |
| 6 | ciudad | String(120) | YES |  |  |  |
| 7 | region | String(120) | YES |  |  |  |
| 8 | pais | String(120) | NO |  |  | 'Chile'::character varying |
| 9 | codigo_postal | String(20) | YES |  |  |  |
| 10 | es_principal | Boolean | NO |  |  | false |
| 11 | activo | Boolean | NO |  |  | true |
| 12 | created_at | DateTime | NO |  |  | now() |
| 13 | updated_at | DateTime | NO |  |  | now() |

**Índices**

- `ix_prov_direccion_proveedor`
  - `CREATE INDEX ix_prov_direccion_proveedor ON public.proveedor_direccion USING btree (proveedor_id)`
- `proveedor_direccion_pkey`
  - `CREATE UNIQUE INDEX proveedor_direccion_pkey ON public.proveedor_direccion USING btree (id)`

### `public.proveedores` (table)

| # | Columna | Tipo | Nullable | PK | FK | Default |
|---|---------|------|----------|----|----|---------|
| 1 | id | BigInteger | NO | YES |  | nextval('proveedores_id_seq'::regclass) |
| 2 | rut | String(20) | NO |  |  |  |
| 3 | razon_social | String(200) | NO |  |  |  |
| 4 | nombre_fantasia | String(200) | YES |  |  |  |
| 5 | giro | String(200) | YES |  |  |  |
| 6 | direccion | String(250) | YES |  |  |  |
| 7 | comuna | String(100) | YES |  |  |  |
| 8 | ciudad | String(100) | YES |  |  |  |
| 9 | telefono | String(50) | YES |  |  |  |
| 10 | email | String(150) | YES |  |  |  |
| 11 | activo | Boolean | NO |  |  |  |
| 12 | fecha_creacion | DateTime | NO |  |  |  |
| 13 | fecha_actualizacion | DateTime | NO |  |  |  |

**Índices**

- `ix_proveedores_id`
  - `CREATE INDEX ix_proveedores_id ON public.proveedores USING btree (id)`
- `ix_proveedores_rut`
  - `CREATE UNIQUE INDEX ix_proveedores_rut ON public.proveedores USING btree (rut)`
- `proveedores_pkey`
  - `CREATE UNIQUE INDEX proveedores_pkey ON public.proveedores USING btree (id)`

### `public.tenant_domains` (table)

| # | Columna | Tipo | Nullable | PK | FK | Default |
|---|---------|------|----------|----|----|---------|
| 1 | id | BigInteger | NO | YES |  | nextval('tenant_domains_id_seq'::regclass) |
| 2 | tenant_id | BigInteger | NO |  |  |  |
| 3 | domain | String(255) | NO |  |  |  |
| 4 | is_primary | Boolean | NO |  |  | false |
| 5 | created_at | DateTime | NO |  |  | now() |

**Índices**

- `ix_tenant_domains_tenant`
  - `CREATE INDEX ix_tenant_domains_tenant ON public.tenant_domains USING btree (tenant_id)`
- `tenant_domains_domain_key`
  - `CREATE UNIQUE INDEX tenant_domains_domain_key ON public.tenant_domains USING btree (domain)`
- `tenant_domains_pkey`
  - `CREATE UNIQUE INDEX tenant_domains_pkey ON public.tenant_domains USING btree (id)`

### `public.tenants` (table)

| # | Columna | Tipo | Nullable | PK | FK | Default |
|---|---------|------|----------|----|----|---------|
| 1 | id | BigInteger | NO | YES |  | nextval('tenants_id_seq'::regclass) |
| 2 | tenant_code | String(60) | NO |  |  |  |
| 3 | tenant_name | String(160) | NO |  |  |  |
| 4 | db_driver | String(80) | NO |  |  | 'postgresql+psycopg'::character varying |
| 5 | db_host | String(120) | NO |  |  |  |
| 6 | db_port | Integer | NO |  |  | 5432 |
| 7 | db_name | String(120) | NO |  |  |  |
| 8 | db_user | String(120) | NO |  |  |  |
| 9 | db_password | Text | NO |  |  |  |
| 10 | db_sslmode | String(20) | YES |  |  |  |
| 11 | is_active | Boolean | NO |  |  | true |
| 12 | created_at | DateTime | NO |  |  | now() |
| 13 | updated_at | DateTime | NO |  |  | now() |

**Índices**

- `ix_tenants_code_active`
  - `CREATE INDEX ix_tenants_code_active ON public.tenants USING btree (tenant_code, is_active)`
- `tenants_db_name_key`
  - `CREATE UNIQUE INDEX tenants_db_name_key ON public.tenants USING btree (db_name)`
- `tenants_pkey`
  - `CREATE UNIQUE INDEX tenants_pkey ON public.tenants USING btree (id)`
- `tenants_tenant_code_key`
  - `CREATE UNIQUE INDEX tenants_tenant_code_key ON public.tenants USING btree (tenant_code)`

### `public.unidades_medida` (table)

| # | Columna | Tipo | Nullable | PK | FK | Default |
|---|---------|------|----------|----|----|---------|
| 1 | id | BigInteger | NO | YES |  | nextval('unidades_medida_id_seq'::regclass) |
| 2 | codigo | String(20) | NO |  |  |  |
| 3 | nombre | String(100) | NO |  |  |  |
| 4 | simbolo | String(20) | YES |  |  |  |
| 5 | activo | Boolean | NO |  |  |  |
| 6 | fecha_creacion | DateTime | NO |  |  |  |

**Índices**

- `ix_unidades_medida_id`
  - `CREATE INDEX ix_unidades_medida_id ON public.unidades_medida USING btree (id)`
- `unidades_medida_codigo_key`
  - `CREATE UNIQUE INDEX unidades_medida_codigo_key ON public.unidades_medida USING btree (codigo)`
- `unidades_medida_pkey`
  - `CREATE UNIQUE INDEX unidades_medida_pkey ON public.unidades_medida USING btree (id)`

### `public.vw_ap_aging` (view)

| # | Columna | Tipo | Nullable | PK | FK | Default |
|---|---------|------|----------|----|----|---------|
| 1 | proveedor_id | BigInteger | YES |  |  |  |
| 2 | razon_social | String(180) | YES |  |  |  |
| 3 | documento_id | BigInteger | YES |  |  |  |
| 4 | tipo | String  # USER-DEFINED::ap_documento_tipo | YES |  |  |  |
| 5 | folio | String(40) | YES |  |  |  |
| 6 | fecha_emision | Date | YES |  |  |  |
| 7 | fecha_vencimiento | Date | YES |  |  |  |
| 8 | total | Numeric(18, 2) | YES |  |  |  |
| 9 | saldo_pendiente | Numeric(18, 2) | YES |  |  |  |
| 10 | dias_vencido | Integer | YES |  |  |  |
| 11 | tramo | Text | YES |  |  |  |

### `public.vw_ap_ranking_proveedores` (view)

| # | Columna | Tipo | Nullable | PK | FK | Default |
|---|---------|------|----------|----|----|---------|
| 1 | proveedor_id | BigInteger | YES |  |  |  |
| 2 | razon_social | String(180) | YES |  |  |  |
| 3 | compras_total | Numeric | YES |  |  |  |
| 4 | saldo_pendiente | Numeric | YES |  |  |  |

### `public.vw_ap_resumen_proveedor` (view)

| # | Columna | Tipo | Nullable | PK | FK | Default |
|---|---------|------|----------|----|----|---------|
| 1 | proveedor_id | BigInteger | YES |  |  |  |
| 2 | razon_social | String(180) | YES |  |  |  |
| 3 | docs_con_saldo | BigInteger | YES |  |  |  |
| 4 | saldo_total | Numeric | YES |  |  |  |
| 5 | saldo_vencido | Numeric | YES |  |  |  |
| 6 | saldo_por_vencer | Numeric | YES |  |  |  |

### `public.vw_gastos_mensual_categoria` (view)

| # | Columna | Tipo | Nullable | PK | FK | Default |
|---|---------|------|----------|----|----|---------|
| 1 | mes | Date | YES |  |  |  |
| 2 | categoria_id | BigInteger | YES |  |  |  |
| 3 | categoria_codigo | String(30) | YES |  |  |  |
| 4 | categoria_nombre | String(160) | YES |  |  |  |
| 5 | categoria_tipo | String  # USER-DEFINED::fin_tipo_gasto | YES |  |  |  |
| 6 | total_gasto | Numeric | YES |  |  |  |
