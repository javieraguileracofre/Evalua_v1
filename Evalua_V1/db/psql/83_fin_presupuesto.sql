    BEGIN;

CREATE TABLE IF NOT EXISTS fin.presupuesto (
  id                BIGSERIAL PRIMARY KEY,
  anio              int NOT NULL,
  mes               int NOT NULL CHECK (mes BETWEEN 1 AND 12),

  categoria_gasto_id bigint NOT NULL REFERENCES fin.categoria_gasto(id),
  centro_costo_id    bigint NOT NULL REFERENCES fin.centro_costo(id),

  monto_presupuestado numeric(18,2) NOT NULL DEFAULT 0,
  notas              text,

  created_at         timestamptz NOT NULL DEFAULT now(),
  updated_at         timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT ux_presupuesto UNIQUE (anio, mes, categoria_gasto_id, centro_costo_id)
);

DROP TRIGGER IF EXISTS tr_presupuesto_updated_at ON fin.presupuesto;
CREATE TRIGGER tr_presupuesto_updated_at
BEFORE UPDATE ON fin.presupuesto
FOR EACH ROW EXECUTE FUNCTION fin.fn_set_updated_at();

-- Real mensual por categoría y centro de costo
CREATE OR REPLACE VIEW fin.vw_real_gasto_mes_cc_cat AS
SELECT
  EXTRACT(YEAR FROM g.fecha)::int AS anio,
  EXTRACT(MONTH FROM g.fecha)::int AS mes,
  g.categoria_gasto_id,
  g.centro_costo_id,
  COALESCE(SUM(g.total),0) AS monto_real
FROM fin.gasto g
WHERE g.estado <> 'ANULADO'
GROUP BY 1,2,3,4;

-- Presupuesto vs Real (desviación)
CREATE OR REPLACE VIEW fin.vw_presupuesto_vs_real AS
SELECT
  p.anio,
  p.mes,
  p.categoria_gasto_id,
  c.codigo AS categoria_codigo,
  c.nombre AS categoria_nombre,
  p.centro_costo_id,
  cc.codigo AS centro_codigo,
  cc.nombre AS centro_nombre,
  p.monto_presupuestado,
  COALESCE(r.monto_real,0) AS monto_real,
  (COALESCE(r.monto_real,0) - p.monto_presupuestado) AS desviacion,
  CASE
    WHEN p.monto_presupuestado = 0 THEN NULL
    ELSE round(((COALESCE(r.monto_real,0) - p.monto_presupuestado) / p.monto_presupuestado) * 100, 2)
  END AS desviacion_pct
FROM fin.presupuesto p
JOIN fin.categoria_gasto c ON c.id = p.categoria_gasto_id
JOIN fin.centro_costo cc ON cc.id = p.centro_costo_id
LEFT JOIN fin.vw_real_gasto_mes_cc_cat r
  ON r.anio = p.anio
 AND r.mes = p.mes
 AND r.categoria_gasto_id = p.categoria_gasto_id
 AND r.centro_costo_id = p.centro_costo_id;

COMMIT;