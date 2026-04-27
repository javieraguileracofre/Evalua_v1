-- db/psql/111_fin_validacion_contable.sql
-- Validaciones automáticas de consistencia contable.

DO $$
DECLARE
    v_count integer;
BEGIN
    -- 1) No hay cuentas de movimiento con hijos.
    SELECT COUNT(*)
    INTO v_count
    FROM fin.plan_cuenta p
    WHERE p.acepta_movimiento = TRUE
      AND EXISTS (SELECT 1 FROM fin.plan_cuenta h WHERE h.cuenta_padre_id = p.id);
    IF v_count > 0 THEN
        RAISE EXCEPTION 'Validacion contable: existen % cuentas de movimiento con hijos.', v_count;
    END IF;

    -- 2) No hay cuentas agrupadoras usadas en config_contable.
    SELECT COUNT(*)
    INTO v_count
    FROM fin.config_contable c
    JOIN fin.plan_cuenta p ON p.codigo = c.codigo_cuenta
    WHERE c.estado = 'ACTIVO'
      AND p.acepta_movimiento = FALSE;
    IF v_count > 0 THEN
        RAISE EXCEPTION 'Validacion contable: existen % cuentas agrupadoras usadas en config_contable.', v_count;
    END IF;

    -- 3) No hay config_contable con codigo_cuenta inexistente.
    SELECT COUNT(*)
    INTO v_count
    FROM fin.config_contable c
    LEFT JOIN fin.plan_cuenta p ON p.codigo = c.codigo_cuenta
    WHERE p.codigo IS NULL;
    IF v_count > 0 THEN
        RAISE EXCEPTION 'Validacion contable: existen % referencias inexistentes en fin.config_contable.', v_count;
    END IF;

    -- 4) No hay config_contable_detalle_modulo con codigo_cuenta inexistente.
    SELECT COUNT(*)
    INTO v_count
    FROM fin.config_contable_detalle_modulo c
    LEFT JOIN fin.plan_cuenta p ON p.codigo = c.codigo_cuenta
    WHERE p.codigo IS NULL;
    IF v_count > 0 THEN
        RAISE EXCEPTION 'Validacion contable: existen % referencias inexistentes en fin.config_contable_detalle_modulo.', v_count;
    END IF;

    -- 5) Cada evento contable activo tiene al menos un DEBE y un HABER.
    SELECT COUNT(*)
    INTO v_count
    FROM (
        SELECT codigo_evento
        FROM fin.config_contable
        WHERE estado = 'ACTIVO'
        GROUP BY codigo_evento
        HAVING SUM(CASE WHEN lado = 'DEBE' THEN 1 ELSE 0 END) = 0
            OR SUM(CASE WHEN lado = 'HABER' THEN 1 ELSE 0 END) = 0
    ) q;
    IF v_count > 0 THEN
        RAISE EXCEPTION 'Validacion contable: existen % eventos activos sin DEBE/HABER en fin.config_contable.', v_count;
    END IF;

    -- 6) No existen cuentas activas sin padre salvo nivel 1.
    SELECT COUNT(*)
    INTO v_count
    FROM fin.plan_cuenta p
    WHERE p.estado = 'ACTIVO'
      AND p.nivel > 1
      AND p.cuenta_padre_id IS NULL;
    IF v_count > 0 THEN
        RAISE EXCEPTION 'Validacion contable: existen % cuentas activas sin padre (nivel > 1).', v_count;
    END IF;

    -- 7) Naturaleza coherente por tipo (con excepciones documentadas).
    SELECT COUNT(*)
    INTO v_count
    FROM fin.plan_cuenta p
    WHERE p.estado = 'ACTIVO'
      AND (
        (p.tipo IN ('PASIVO', 'PATRIMONIO', 'INGRESO') AND p.naturaleza <> 'ACREEDORA')
        OR (p.tipo IN ('ACTIVO', 'COSTO', 'GASTO') AND p.naturaleza <> 'DEUDORA' AND p.codigo <> '120899')
      );
    IF v_count > 0 THEN
        RAISE EXCEPTION 'Validacion contable: existen % cuentas con naturaleza incompatible con tipo.', v_count;
    END IF;
END $$;
