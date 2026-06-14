-- db/psql/109_leasing_operativo_gestion_cartera.sql
-- Mora, terminación, repossession/remarketing y políticas de cobranza LOP.

BEGIN;

ALTER TABLE public.leasing_op_cuota
    ADD COLUMN IF NOT EXISTS dias_mora INTEGER NOT NULL DEFAULT 0,
    ADD COLUMN IF NOT EXISTS monto_mora NUMERIC(18, 4) NOT NULL DEFAULT 0,
    ADD COLUMN IF NOT EXISTS fecha_mora_aplicada DATE NULL;

ALTER TABLE public.leasing_op_contrato
    ADD COLUMN IF NOT EXISTS fecha_termino DATE NULL,
    ADD COLUMN IF NOT EXISTS motivo_termino TEXT NULL DEFAULT '';

ALTER TABLE public.leasing_op_contrato DROP CONSTRAINT IF EXISTS chk_lo_ctr_est;
ALTER TABLE public.leasing_op_contrato
    ADD CONSTRAINT chk_lo_ctr_est CHECK (
        estado IN ('VIGENTE', 'CERRADO', 'LIQUIDADO', 'RENOVADO', 'MORA', 'TERMINADO_ANTICIPADO', 'EN_REPOSSESSION', 'LIQUIDADO_REMARKETING')
    );

CREATE TABLE IF NOT EXISTS public.leasing_op_gestion_evento (
    id                  BIGSERIAL PRIMARY KEY,
    contrato_id         BIGINT NOT NULL REFERENCES public.leasing_op_contrato(id) ON DELETE CASCADE,
    cuota_id            BIGINT NULL REFERENCES public.leasing_op_cuota(id) ON DELETE SET NULL,
    tipo                VARCHAR(32) NOT NULL,
    estado              VARCHAR(24) NOT NULL DEFAULT 'VIGENTE',
    dias_mora           INTEGER NOT NULL DEFAULT 0,
    monto_mora          NUMERIC(18, 4) NOT NULL DEFAULT 0,
    monto_penalidad     NUMERIC(18, 4) NOT NULL DEFAULT 0,
    monto_recupero      NUMERIC(18, 4) NOT NULL DEFAULT 0,
    payload_json        JSONB NOT NULL DEFAULT '{}'::jsonb,
    usuario             VARCHAR(200) NOT NULL DEFAULT 'sistema',
    creado_en           TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT chk_lo_gest_tipo CHECK (
        tipo IN ('MORA', 'TERMINACION_ANTICIPADA', 'REPOSSESSION', 'REMARKETING', 'PAGO_COBRANZA')
    )
);

CREATE INDEX IF NOT EXISTS ix_lo_gest_ctr ON public.leasing_op_gestion_evento (contrato_id, tipo);
CREATE INDEX IF NOT EXISTS ix_lo_gest_cuota ON public.leasing_op_gestion_evento (cuota_id);

INSERT INTO public.leasing_op_politica (clave, valor_json, descripcion)
VALUES
(
    'mora_v1',
    '{
      "tasa_mora_mensual_pct": 1.5,
      "tasa_mora_diaria_pct": 0.05,
      "dias_gracia": 5,
      "mora_sobre": "NETO",
      "generar_cxc_mora": true
    }'::jsonb,
    'Parámetros mora leasing operativo.'
),
(
    'terminacion_v1',
    '{
      "penalidad_pct_rentas_pendientes": 50,
      "penalidad_pct_capex_remanente": 8,
      "incluir_iva_penalidad": true,
      "requiere_repossession": false
    }'::jsonb,
    'Terminación anticipada contrato LOP.'
),
(
    'remarketing_v1',
    '{
      "descuento_venta_forzada_pct": 12,
      "costo_repossession_default": 800000,
      "costo_reacondicionamiento_pct": 3,
      "meses_objetivo_venta": 3
    }'::jsonb,
    'Remarketing activo recuperado.'
)
ON CONFLICT (clave) DO NOTHING;
ALTER TABLE public.leasing_op_activo_fijo DROP CONSTRAINT IF EXISTS chk_lo_af_estado;
ALTER TABLE public.leasing_op_activo_fijo
    ADD CONSTRAINT chk_lo_af_estado CHECK (
        estado IN ('DISPONIBLE', 'ARRENDADO', 'MANTENCION', 'BAJA', 'REPOSSESSION', 'VENDIDO')
    );

ALTER TABLE public.leasing_op_cuota DROP CONSTRAINT IF EXISTS chk_lo_cuo_est;
ALTER TABLE public.leasing_op_cuota
    ADD CONSTRAINT chk_lo_cuo_est CHECK (estado IN ('PENDIENTE', 'FACTURADA', 'PAGADA', 'MORA', 'CANCELADA'));

COMMIT;
