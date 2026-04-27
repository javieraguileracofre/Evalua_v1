-- db/psql/114_fin_plan_cuentas_normalizar_codigos.sql
-- Normaliza referencias legacy con puntos hacia codigos canonicos sin separadores.

CREATE SCHEMA IF NOT EXISTS fin;

-- Deteccion de cuentas activas con puntos.
SELECT codigo, nombre, tipo, nivel, estado
FROM fin.plan_cuenta
WHERE codigo LIKE '%.%';

CREATE TABLE IF NOT EXISTS fin.plan_cuenta_codigo_alias (
    codigo_alias VARCHAR(30) PRIMARY KEY,
    codigo_canonico VARCHAR(30) NOT NULL,
    motivo TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

INSERT INTO fin.plan_cuenta_codigo_alias (codigo_alias, codigo_canonico, motivo)
VALUES
    ('1.1.1', '110101', 'Legacy caja general'),
    ('1.1.1.01', '110101', 'Legacy caja general subcuenta'),
    ('1.01.01', '110101', 'Legacy caja general variante'),
    ('1.1.01', '110101', 'Legacy caja general variante'),
    ('1.1.2', '110201', 'Legacy bancos'),
    ('1.1.2.01', '110201', 'Legacy bancos subcuenta'),
    ('1.02.01', '110201', 'Legacy bancos variante'),
    ('1.1.02', '110201', 'Legacy bancos variante'),
    ('1.1.3', '110301', 'Legacy clientes'),
    ('1.1.03', '110301', 'Legacy clientes variante'),
    ('1.1.04', '110601', 'Legacy anticipos a rendir'),
    ('1.1.05', '110601', 'Legacy fondos por rendir'),
    ('1.01.05', '110601', 'Legacy fondos por rendir variante'),
    ('1.05.01', '110601', 'Legacy fondos por rendir variante'),
    ('2.1.1', '210101', 'Legacy proveedores'),
    ('2.1.2', '210201', 'Legacy IVA debito fiscal'),
    ('4.1.1', '410101', 'Legacy ventas'),
    ('4.1.01', '410101', 'Legacy ventas variante'),
    ('4.1.7', '410701', 'Legacy ingresos financieros leasing'),
    ('5.1.1', '510101', 'Legacy costo de ventas'),
    ('5.1.01', '510101', 'Legacy costo de ventas variante'),
    ('6.1.01', '610104', 'Legacy gastos generales'),
    ('6.1.02', '610102', 'Legacy combustibles'),
    ('6.1.03', '610103', 'Legacy peajes'),
    ('6.1.04', '610105', 'Legacy viaticos'),
    ('6.2.01', '620101', 'Legacy mantencion y reparaciones')
ON CONFLICT (codigo_alias) DO UPDATE
SET codigo_canonico = EXCLUDED.codigo_canonico,
    motivo = EXCLUDED.motivo;

DO $$
DECLARE
    col RECORD;
    acc RECORD;
    has_refs BOOLEAN;
    has_children BOOLEAN;
BEGIN
    -- 1) Migrar referencias desde aliases conocidos a codigos canonicos.
    FOR col IN
        SELECT c.table_schema, c.table_name, c.column_name
        FROM information_schema.columns c
        WHERE c.table_schema IN ('fin', 'public')
          AND (
                c.column_name IN ('codigo_cuenta', 'cuenta_contable', 'cuenta_codigo')
             OR c.column_name LIKE 'cuenta\_%\_codigo' ESCAPE '\'
          )
    LOOP
        EXECUTE format(
            'UPDATE %I.%I t
                SET %I = a.codigo_canonico
               FROM fin.plan_cuenta_codigo_alias a
              WHERE t.%I = a.codigo_alias
                AND t.%I IS DISTINCT FROM a.codigo_canonico',
            col.table_schema, col.table_name, col.column_name, col.column_name, col.column_name
        );
    END LOOP;

    -- 2) Normalizar el propio plan: cuentas activas con puntos.
    FOR acc IN
        SELECT pc.id, pc.codigo
        FROM fin.plan_cuenta pc
        WHERE pc.estado = 'ACTIVO'
          AND pc.codigo LIKE '%.%'
    LOOP
        has_refs := FALSE;

        FOR col IN
            SELECT c.table_schema, c.table_name, c.column_name
            FROM information_schema.columns c
            WHERE c.table_schema IN ('fin', 'public')
              AND (
                    c.column_name IN ('codigo_cuenta', 'cuenta_contable', 'cuenta_codigo')
                 OR c.column_name LIKE 'cuenta\_%\_codigo' ESCAPE '\'
              )
        LOOP
            EXECUTE format(
                'SELECT EXISTS (SELECT 1 FROM %I.%I WHERE %I = $1 LIMIT 1)',
                col.table_schema, col.table_name, col.column_name
            )
            INTO has_refs
            USING acc.codigo;

            EXIT WHEN has_refs;
        END LOOP;

        SELECT EXISTS (
            SELECT 1
            FROM fin.plan_cuenta h
            WHERE h.cuenta_padre_id = acc.id
        )
        INTO has_children;

        IF has_refs OR has_children THEN
            UPDATE fin.plan_cuenta
               SET estado = 'INACTIVO'
             WHERE id = acc.id
               AND estado <> 'INACTIVO';
        ELSE
            DELETE FROM fin.plan_cuenta
             WHERE id = acc.id;
        END IF;
    END LOOP;
END $$;

-- Validacion final obligatoria.
SELECT COUNT(*)
FROM fin.plan_cuenta
WHERE estado = 'ACTIVO'
  AND codigo LIKE '%.%';
