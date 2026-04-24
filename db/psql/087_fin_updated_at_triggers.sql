-- db/psql/087_fin_updated_at_triggers.sql

CREATE OR REPLACE FUNCTION fin.set_updated_at()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS trg_fin_ap_documento_updated_at ON fin.ap_documento;
CREATE TRIGGER trg_fin_ap_documento_updated_at
BEFORE UPDATE ON fin.ap_documento
FOR EACH ROW
EXECUTE FUNCTION fin.set_updated_at();

DROP TRIGGER IF EXISTS trg_fin_ap_documento_detalle_updated_at ON fin.ap_documento_detalle;
CREATE TRIGGER trg_fin_ap_documento_detalle_updated_at
BEFORE UPDATE ON fin.ap_documento_detalle
FOR EACH ROW
EXECUTE FUNCTION fin.set_updated_at();

DROP TRIGGER IF EXISTS trg_fin_ap_pago_updated_at ON fin.ap_pago;
CREATE TRIGGER trg_fin_ap_pago_updated_at
BEFORE UPDATE ON fin.ap_pago
FOR EACH ROW
EXECUTE FUNCTION fin.set_updated_at();

DROP TRIGGER IF EXISTS trg_fin_categoria_gasto_updated_at ON fin.categoria_gasto;
CREATE TRIGGER trg_fin_categoria_gasto_updated_at
BEFORE UPDATE ON fin.categoria_gasto
FOR EACH ROW
EXECUTE FUNCTION fin.set_updated_at();

DROP TRIGGER IF EXISTS trg_fin_centro_costo_updated_at ON fin.centro_costo;
CREATE TRIGGER trg_fin_centro_costo_updated_at
BEFORE UPDATE ON fin.centro_costo
FOR EACH ROW
EXECUTE FUNCTION fin.set_updated_at();

DROP TRIGGER IF EXISTS trg_fin_periodo_updated_at ON fin.periodo;
CREATE TRIGGER trg_fin_periodo_updated_at
BEFORE UPDATE ON fin.periodo
FOR EACH ROW
EXECUTE FUNCTION fin.set_updated_at();

DROP TRIGGER IF EXISTS trg_fin_proveedor_updated_at ON fin.proveedor;
CREATE TRIGGER trg_fin_proveedor_updated_at
BEFORE UPDATE ON fin.proveedor
FOR EACH ROW
EXECUTE FUNCTION fin.set_updated_at();

DROP TRIGGER IF EXISTS trg_fin_proveedor_banco_updated_at ON fin.proveedor_banco;
CREATE TRIGGER trg_fin_proveedor_banco_updated_at
BEFORE UPDATE ON fin.proveedor_banco
FOR EACH ROW
EXECUTE FUNCTION fin.set_updated_at();

DROP TRIGGER IF EXISTS trg_fin_proveedor_contacto_updated_at ON fin.proveedor_contacto;
CREATE TRIGGER trg_fin_proveedor_contacto_updated_at
BEFORE UPDATE ON fin.proveedor_contacto
FOR EACH ROW
EXECUTE FUNCTION fin.set_updated_at();

DROP TRIGGER IF EXISTS trg_fin_proveedor_direccion_updated_at ON fin.proveedor_direccion;
CREATE TRIGGER trg_fin_proveedor_direccion_updated_at
BEFORE UPDATE ON fin.proveedor_direccion
FOR EACH ROW
EXECUTE FUNCTION fin.set_updated_at();