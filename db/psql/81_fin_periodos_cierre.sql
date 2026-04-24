BEGIN;

DO $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname='periodo_estado' AND typnamespace='fin'::regnamespace) THEN
    CREATE TYPE fin.periodo_estado AS ENUM ('ABIERTO','CERRADO');
  END IF;
END $$;

-- 1) Período contable (por mes)
CREATE TABLE IF NOT EXISTS fin.periodo (
  id           BIGSERIAL PRIMARY KEY,
  anio         int NOT NULL,
  mes          int NOT NULL CHECK (mes BETWEEN 1 AND 12),
  estado       fin.periodo_estado NOT NULL DEFAULT 'ABIERTO',
  cerrado_at   timestamptz,
  cerrado_por  citext,
  notas        text,
  created_at   timestamptz NOT NULL DEFAULT now(),
  updated_at   timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT ux_periodo UNIQUE (anio, mes)
);

DROP TRIGGER IF EXISTS tr_periodo_updated_at ON fin.periodo;
CREATE TRIGGER tr_periodo_updated_at
BEFORE UPDATE ON fin.periodo
FOR EACH ROW EXECUTE FUNCTION fin.fn_set_updated_at();

-- 2) Helper: obtener período desde una fecha
CREATE OR REPLACE FUNCTION fin.fn_periodo_key(p_fecha date)
RETURNS TABLE(anio int, mes int)
LANGUAGE sql
IMMUTABLE
AS $$
  SELECT EXTRACT(YEAR FROM p_fecha)::int AS anio,
         EXTRACT(MONTH FROM p_fecha)::int AS mes;
$$;

-- 3) Asegura que exista el período (idempotente)
CREATE OR REPLACE FUNCTION fin.fn_periodo_ensure(p_fecha date)
RETURNS bigint
LANGUAGE plpgsql
AS $$
DECLARE
  v_anio int;
  v_mes int;
  v_id bigint;
BEGIN
  SELECT anio, mes INTO v_anio, v_mes FROM fin.fn_periodo_key(p_fecha);

  SELECT id INTO v_id
  FROM fin.periodo
  WHERE anio = v_anio AND mes = v_mes;

  IF v_id IS NULL THEN
    INSERT INTO fin.periodo(anio, mes, estado)
    VALUES (v_anio, v_mes, 'ABIERTO')
    RETURNING id INTO v_id;
  END IF;

  RETURN v_id;
END;
$$;

-- 4) Validación: ¿está cerrado el período de una fecha?
CREATE OR REPLACE FUNCTION fin.fn_periodo_is_cerrado(p_fecha date)
RETURNS boolean
LANGUAGE sql
STABLE
AS $$
  SELECT COALESCE((
    SELECT (estado = 'CERRADO')
    FROM fin.periodo
    WHERE anio = EXTRACT(YEAR FROM p_fecha)::int
      AND mes  = EXTRACT(MONTH FROM p_fecha)::int
  ), false);
$$;

-- 5) Cerrar período
CREATE OR REPLACE FUNCTION fin.fn_periodo_cerrar(p_anio int, p_mes int, p_user citext, p_notas text DEFAULT NULL)
RETURNS void
LANGUAGE plpgsql
AS $$
BEGIN
  -- asegura que exista
  INSERT INTO fin.periodo(anio, mes, estado)
  VALUES (p_anio, p_mes, 'ABIERTO')
  ON CONFLICT (anio, mes) DO NOTHING;

  UPDATE fin.periodo
     SET estado = 'CERRADO',
         cerrado_at = now(),
         cerrado_por = p_user,
         notas = p_notas
   WHERE anio = p_anio AND mes = p_mes;

  -- registra evento (si tienes fin.evento)
  INSERT INTO fin.evento(entidad, entidad_id, evento, detalle, user_email)
  VALUES ('PERIODO', 0, 'CERRADO', format('Cierre %s-%s', p_anio, lpad(p_mes::text,2,'0')), p_user);
END;
$$;

-- 6) Abrir período (solo admin)
CREATE OR REPLACE FUNCTION fin.fn_periodo_abrir(p_anio int, p_mes int, p_user citext, p_notas text DEFAULT NULL)
RETURNS void
LANGUAGE plpgsql
AS $$
BEGIN
  INSERT INTO fin.periodo(anio, mes, estado)
  VALUES (p_anio, p_mes, 'ABIERTO')
  ON CONFLICT (anio, mes) DO NOTHING;

  UPDATE fin.periodo
     SET estado = 'ABIERTO',
         notas = p_notas
   WHERE anio = p_anio AND mes = p_mes;

  INSERT INTO fin.evento(entidad, entidad_id, evento, detalle, user_email)
  VALUES ('PERIODO', 0, 'ABIERTO', format('Apertura %s-%s', p_anio, lpad(p_mes::text,2,'0')), p_user);
END;
$$;

COMMIT;