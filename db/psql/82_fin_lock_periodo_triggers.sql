BEGIN;

-- Función genérica para bloquear escrituras en períodos cerrados
CREATE OR REPLACE FUNCTION fin.fn_guard_periodo_cerrado()
RETURNS trigger
LANGUAGE plpgsql
AS $$
DECLARE
  v_fecha date;
BEGIN
  -- Definir fecha según tabla
  IF TG_TABLE_NAME = 'ap_documento' THEN
    v_fecha := NEW.fecha_emision;
  ELSIF TG_TABLE_NAME = 'ap_pago' THEN
    v_fecha := NEW.fecha_pago;
  ELSIF TG_TABLE_NAME = 'gasto' THEN
    v_fecha := NEW.fecha;
  ELSE
    -- Por seguridad, bloquea si no sabemos.
    RAISE EXCEPTION 'Guard de período: tabla no soportada: %', TG_TABLE_NAME;
  END IF;

  -- asegurar período creado
  PERFORM fin.fn_periodo_ensure(v_fecha);

  IF fin.fn_periodo_is_cerrado(v_fecha) THEN
    RAISE EXCEPTION 'Período contable cerrado (%). No se permite modificar registros.', v_fecha
      USING ERRCODE = 'P0001';
  END IF;

  RETURN NEW;
END;
$$;

-- AP DOCUMENTO
DROP TRIGGER IF EXISTS tr_guard_ap_documento_periodo ON fin.ap_documento;
CREATE TRIGGER tr_guard_ap_documento_periodo
BEFORE INSERT OR UPDATE OR DELETE ON fin.ap_documento
FOR EACH ROW EXECUTE FUNCTION fin.fn_guard_periodo_cerrado();

-- AP PAGO
DROP TRIGGER IF EXISTS tr_guard_ap_pago_periodo ON fin.ap_pago;
CREATE TRIGGER tr_guard_ap_pago_periodo
BEFORE INSERT OR UPDATE OR DELETE ON fin.ap_pago
FOR EACH ROW EXECUTE FUNCTION fin.fn_guard_periodo_cerrado();

-- GASTO
DROP TRIGGER IF EXISTS tr_guard_gasto_periodo ON fin.gasto;
CREATE TRIGGER tr_guard_gasto_periodo
BEFORE INSERT OR UPDATE OR DELETE ON fin.gasto
FOR EACH ROW EXECUTE FUNCTION fin.fn_guard_periodo_cerrado();

COMMIT;