-- db/psql/089_fin_plan_cuentas.sql
-- ============================================================
-- PLAN DE CUENTAS · EVALUA ERP
-- Camino dorado contable premium
-- ============================================================

CREATE SCHEMA IF NOT EXISTS fin;

CREATE TABLE IF NOT EXISTS fin.plan_cuenta (
    id                  BIGSERIAL PRIMARY KEY,
    codigo              VARCHAR(30) NOT NULL,
    nombre              VARCHAR(180) NOT NULL,
    nivel               INTEGER NOT NULL DEFAULT 1,
    cuenta_padre_id     BIGINT NULL,
    tipo                VARCHAR(30) NOT NULL,          -- ACTIVO, PASIVO, PATRIMONIO, INGRESO, COSTO, GASTO, ORDEN
    clasificacion       VARCHAR(50) NOT NULL,          -- ACTIVO_CORRIENTE, PASIVO_CORRIENTE, INGRESO_OPERACIONAL, etc.
    naturaleza          VARCHAR(20) NOT NULL,          -- DEUDORA / ACREEDORA
    acepta_movimiento   BOOLEAN NOT NULL DEFAULT TRUE,
    requiere_centro_costo BOOLEAN NOT NULL DEFAULT FALSE,
    estado              VARCHAR(20) NOT NULL DEFAULT 'ACTIVO',
    descripcion         TEXT NULL,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT now(),

    CONSTRAINT ux_fin_plan_cuenta_codigo UNIQUE (codigo),
    CONSTRAINT fk_fin_plan_cuenta_padre
        FOREIGN KEY (cuenta_padre_id)
        REFERENCES fin.plan_cuenta(id)
        ON DELETE RESTRICT
);

CREATE INDEX IF NOT EXISTS ix_fin_plan_cuenta_padre
    ON fin.plan_cuenta(cuenta_padre_id);

CREATE INDEX IF NOT EXISTS ix_fin_plan_cuenta_tipo
    ON fin.plan_cuenta(tipo);

CREATE INDEX IF NOT EXISTS ix_fin_plan_cuenta_clasificacion
    ON fin.plan_cuenta(clasificacion);

CREATE INDEX IF NOT EXISTS ix_fin_plan_cuenta_estado
    ON fin.plan_cuenta(estado);

CREATE INDEX IF NOT EXISTS ix_fin_plan_cuenta_nivel
    ON fin.plan_cuenta(nivel);

-- Trigger updated_at
CREATE OR REPLACE FUNCTION fin.fn_set_updated_at_plan_cuenta()
RETURNS trigger AS $$
BEGIN
    NEW.updated_at := now();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_fin_plan_cuenta_updated_at ON fin.plan_cuenta;

CREATE TRIGGER trg_fin_plan_cuenta_updated_at
BEFORE UPDATE ON fin.plan_cuenta
FOR EACH ROW
EXECUTE FUNCTION fin.fn_set_updated_at_plan_cuenta();

-- ============================================================
-- Seed base premium
-- ============================================================
INSERT INTO fin.plan_cuenta
(codigo, nombre, nivel, cuenta_padre_id, tipo, clasificacion, naturaleza, acepta_movimiento, requiere_centro_costo, estado, descripcion)
VALUES
('1', 'ACTIVO', 1, NULL, 'ACTIVO', 'ACTIVO', 'DEUDORA', FALSE, FALSE, 'ACTIVO', 'Grupo contable de activos'),
('2', 'PASIVO', 1, NULL, 'PASIVO', 'PASIVO', 'ACREEDORA', FALSE, FALSE, 'ACTIVO', 'Grupo contable de pasivos'),
('3', 'PATRIMONIO', 1, NULL, 'PATRIMONIO', 'PATRIMONIO', 'ACREEDORA', FALSE, FALSE, 'ACTIVO', 'Grupo contable patrimonial'),
('4', 'INGRESOS', 1, NULL, 'INGRESO', 'INGRESOS', 'ACREEDORA', FALSE, FALSE, 'ACTIVO', 'Grupo contable de ingresos'),
('5', 'COSTOS', 1, NULL, 'COSTO', 'COSTOS', 'DEUDORA', FALSE, FALSE, 'ACTIVO', 'Grupo contable de costos'),
('6', 'GASTOS', 1, NULL, 'GASTO', 'GASTOS', 'DEUDORA', FALSE, FALSE, 'ACTIVO', 'Grupo contable de gastos')
ON CONFLICT (codigo) DO NOTHING;

INSERT INTO fin.plan_cuenta
(codigo, nombre, nivel, cuenta_padre_id, tipo, clasificacion, naturaleza, acepta_movimiento, requiere_centro_costo, estado, descripcion)
SELECT '1.1', 'ACTIVO CORRIENTE', 2, id, 'ACTIVO', 'ACTIVO_CORRIENTE', 'DEUDORA', FALSE, FALSE, 'ACTIVO', 'Activo corriente'
FROM fin.plan_cuenta
WHERE codigo = '1'
ON CONFLICT (codigo) DO NOTHING;

INSERT INTO fin.plan_cuenta
(codigo, nombre, nivel, cuenta_padre_id, tipo, clasificacion, naturaleza, acepta_movimiento, requiere_centro_costo, estado, descripcion)
SELECT '2.1', 'PASIVO CORRIENTE', 2, id, 'PASIVO', 'PASIVO_CORRIENTE', 'ACREEDORA', FALSE, FALSE, 'ACTIVO', 'Pasivo corriente'
FROM fin.plan_cuenta
WHERE codigo = '2'
ON CONFLICT (codigo) DO NOTHING;

INSERT INTO fin.plan_cuenta
(codigo, nombre, nivel, cuenta_padre_id, tipo, clasificacion, naturaleza, acepta_movimiento, requiere_centro_costo, estado, descripcion)
SELECT '4.1', 'INGRESOS OPERACIONALES', 2, id, 'INGRESO', 'INGRESO_OPERACIONAL', 'ACREEDORA', FALSE, FALSE, 'ACTIVO', 'Ingresos operacionales'
FROM fin.plan_cuenta
WHERE codigo = '4'
ON CONFLICT (codigo) DO NOTHING;

INSERT INTO fin.plan_cuenta
(codigo, nombre, nivel, cuenta_padre_id, tipo, clasificacion, naturaleza, acepta_movimiento, requiere_centro_costo, estado, descripcion)
SELECT '5.1', 'COSTO DE VENTAS', 2, id, 'COSTO', 'COSTO_VENTA', 'DEUDORA', FALSE, FALSE, 'ACTIVO', 'Costo de ventas'
FROM fin.plan_cuenta
WHERE codigo = '5'
ON CONFLICT (codigo) DO NOTHING;

INSERT INTO fin.plan_cuenta
(codigo, nombre, nivel, cuenta_padre_id, tipo, clasificacion, naturaleza, acepta_movimiento, requiere_centro_costo, estado, descripcion)
SELECT '6.1', 'GASTOS DE ADMINISTRACION', 2, id, 'GASTO', 'GASTO_ADMINISTRACION', 'DEUDORA', FALSE, FALSE, 'ACTIVO', 'Gastos de administración'
FROM fin.plan_cuenta
WHERE codigo = '6'
ON CONFLICT (codigo) DO NOTHING;

-- Cuentas operativas mínimas
INSERT INTO fin.plan_cuenta
(codigo, nombre, nivel, cuenta_padre_id, tipo, clasificacion, naturaleza, acepta_movimiento, requiere_centro_costo, estado, descripcion)
SELECT '1.1.1', 'CAJA', 3, id, 'ACTIVO', 'ACTIVO_CORRIENTE', 'DEUDORA', TRUE, FALSE, 'ACTIVO', 'Caja general'
FROM fin.plan_cuenta
WHERE codigo = '1.1'
ON CONFLICT (codigo) DO NOTHING;

INSERT INTO fin.plan_cuenta
(codigo, nombre, nivel, cuenta_padre_id, tipo, clasificacion, naturaleza, acepta_movimiento, requiere_centro_costo, estado, descripcion)
SELECT '1.1.2', 'BANCOS', 3, id, 'ACTIVO', 'ACTIVO_CORRIENTE', 'DEUDORA', TRUE, FALSE, 'ACTIVO', 'Bancos'
FROM fin.plan_cuenta
WHERE codigo = '1.1'
ON CONFLICT (codigo) DO NOTHING;

INSERT INTO fin.plan_cuenta
(codigo, nombre, nivel, cuenta_padre_id, tipo, clasificacion, naturaleza, acepta_movimiento, requiere_centro_costo, estado, descripcion)
SELECT '1.1.3', 'CLIENTES', 3, id, 'ACTIVO', 'ACTIVO_CORRIENTE', 'DEUDORA', TRUE, FALSE, 'ACTIVO', 'Clientes por cobrar'
FROM fin.plan_cuenta
WHERE codigo = '1.1'
ON CONFLICT (codigo) DO NOTHING;

INSERT INTO fin.plan_cuenta
(codigo, nombre, nivel, cuenta_padre_id, tipo, clasificacion, naturaleza, acepta_movimiento, requiere_centro_costo, estado, descripcion)
SELECT '2.1.1', 'PROVEEDORES', 3, id, 'PASIVO', 'PASIVO_CORRIENTE', 'ACREEDORA', TRUE, FALSE, 'ACTIVO', 'Proveedores por pagar'
FROM fin.plan_cuenta
WHERE codigo = '2.1'
ON CONFLICT (codigo) DO NOTHING;

INSERT INTO fin.plan_cuenta
(codigo, nombre, nivel, cuenta_padre_id, tipo, clasificacion, naturaleza, acepta_movimiento, requiere_centro_costo, estado, descripcion)
SELECT '4.1.1', 'VENTAS', 3, id, 'INGRESO', 'INGRESO_OPERACIONAL', 'ACREEDORA', TRUE, TRUE, 'ACTIVO', 'Ventas netas'
FROM fin.plan_cuenta
WHERE codigo = '4.1'
ON CONFLICT (codigo) DO NOTHING;

INSERT INTO fin.plan_cuenta
(codigo, nombre, nivel, cuenta_padre_id, tipo, clasificacion, naturaleza, acepta_movimiento, requiere_centro_costo, estado, descripcion)
SELECT '4.1.2', 'IVA DEBITO FISCAL', 3, id, 'PASIVO', 'PASIVO_CORRIENTE', 'ACREEDORA', TRUE, FALSE, 'ACTIVO', 'IVA débito fiscal'
FROM fin.plan_cuenta
WHERE codigo = '4.1'
ON CONFLICT (codigo) DO NOTHING;

INSERT INTO fin.plan_cuenta
(codigo, nombre, nivel, cuenta_padre_id, tipo, clasificacion, naturaleza, acepta_movimiento, requiere_centro_costo, estado, descripcion)
SELECT '5.1.1', 'COSTO DE VENTA', 3, id, 'COSTO', 'COSTO_VENTA', 'DEUDORA', TRUE, TRUE, 'ACTIVO', 'Costo directo de ventas'
FROM fin.plan_cuenta
WHERE codigo = '5.1'
ON CONFLICT (codigo) DO NOTHING;

INSERT INTO fin.plan_cuenta
(codigo, nombre, nivel, cuenta_padre_id, tipo, clasificacion, naturaleza, acepta_movimiento, requiere_centro_costo, estado, descripcion)
SELECT '6.1.1', 'GASTOS DE ADMINISTRACION', 3, id, 'GASTO', 'GASTO_ADMINISTRACION', 'DEUDORA', TRUE, TRUE, 'ACTIVO', 'Gastos administrativos'
FROM fin.plan_cuenta
WHERE codigo = '6.1'
ON CONFLICT (codigo) DO NOTHING;

INSERT INTO fin.plan_cuenta
(codigo, nombre, nivel, cuenta_padre_id, tipo, clasificacion, naturaleza, acepta_movimiento, requiere_centro_costo, estado, descripcion)
SELECT '1.1.4', 'IVA CREDITO FISCAL', 3, id, 'ACTIVO', 'ACTIVO_CORRIENTE', 'DEUDORA', TRUE, FALSE, 'ACTIVO', 'IVA crédito fiscal'
FROM fin.plan_cuenta
WHERE codigo = '1.1'
ON CONFLICT (codigo) DO NOTHING;