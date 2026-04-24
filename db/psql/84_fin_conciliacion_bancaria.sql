BEGIN;

DO $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname='conciliacion_estado' AND typnamespace='fin'::regnamespace) THEN
    CREATE TYPE fin.conciliacion_estado AS ENUM ('PENDIENTE','CONCILIADO','DESCARTADO');
  END IF;
END $$;

-- Movimiento bancario (cartola)
CREATE TABLE IF NOT EXISTS fin.mov_banco (
  id             BIGSERIAL PRIMARY KEY,
  fecha          date NOT NULL,
  descripcion    varchar(260) NOT NULL,
  monto          numeric(18,2) NOT NULL, -- negativo egreso, positivo ingreso
  moneda         fin.moneda_iso NOT NULL DEFAULT 'CLP',
  referencia     varchar(120),
  estado         fin.conciliacion_estado NOT NULL DEFAULT 'PENDIENTE',
  conciliado_at  timestamptz,
  conciliado_por citext,
  created_at     timestamptz NOT NULL DEFAULT now(),
  updated_at     timestamptz NOT NULL DEFAULT now()
);

DROP TRIGGER IF EXISTS tr_mov_banco_updated_at ON fin.mov_banco;
CREATE TRIGGER tr_mov_banco_updated_at
BEFORE UPDATE ON fin.mov_banco
FOR EACH ROW EXECUTE FUNCTION fin.fn_set_updated_at();

-- Matching: movimiento bancario <-> pago proveedor
CREATE TABLE IF NOT EXISTS fin.mov_banco_match_pago (
  id           BIGSERIAL PRIMARY KEY,
  mov_banco_id bigint NOT NULL REFERENCES fin.mov_banco(id) ON DELETE CASCADE,
  pago_id      bigint NOT NULL REFERENCES fin.ap_pago(id) ON DELETE CASCADE,
  created_at   timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT ux_mov_pago UNIQUE (mov_banco_id, pago_id)
);

-- Al crear match, marcar conciliado
CREATE OR REPLACE FUNCTION fin.fn_conciliar_mov_banco()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
  UPDATE fin.mov_banco
     SET estado = 'CONCILIADO',
         conciliado_at = now(),
         conciliado_por = current_user
   WHERE id = NEW.mov_banco_id;

  RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS tr_match_conciliar ON fin.mov_banco_match_pago;
CREATE TRIGGER tr_match_conciliar
AFTER INSERT ON fin.mov_banco_match_pago
FOR EACH ROW EXECUTE FUNCTION fin.fn_conciliar_mov_banco();

COMMIT;