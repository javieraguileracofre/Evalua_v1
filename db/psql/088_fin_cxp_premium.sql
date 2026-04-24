-- db/psql/088_fin_cxp_premium.sql
-- ============================================================
-- CxP premium - refuerzos de integridad, vistas y performance
-- ============================================================

BEGIN;

-- ------------------------------------------------------------
-- FK opcionales / refuerzos
-- ------------------------------------------------------------
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM pg_constraint
        WHERE conname = 'fk_fin_ap_pago_banco_proveedor'
    ) THEN
        ALTER TABLE fin.ap_pago
        ADD CONSTRAINT fk_fin_ap_pago_banco_proveedor
        FOREIGN KEY (banco_proveedor_id)
        REFERENCES public.proveedor_banco(id)
        ON UPDATE CASCADE
        ON DELETE SET NULL;
    END IF;
END $$;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM pg_constraint
        WHERE conname = 'fk_fin_ap_documento_proveedor'
    ) THEN
        ALTER TABLE fin.ap_documento
        ADD CONSTRAINT fk_fin_ap_documento_proveedor
        FOREIGN KEY (proveedor_id)
        REFERENCES public.proveedor(id)
        ON UPDATE CASCADE
        ON DELETE RESTRICT;
    END IF;
END $$;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM pg_constraint
        WHERE conname = 'fk_fin_ap_pago_proveedor'
    ) THEN
        ALTER TABLE fin.ap_pago
        ADD CONSTRAINT fk_fin_ap_pago_proveedor
        FOREIGN KEY (proveedor_id)
        REFERENCES public.proveedor(id)
        ON UPDATE CASCADE
        ON DELETE RESTRICT;
    END IF;
END $$;

-- ------------------------------------------------------------
-- Índices adicionales
-- ------------------------------------------------------------
CREATE INDEX IF NOT EXISTS ix_fin_ap_pago_proveedor_fecha
    ON fin.ap_pago (proveedor_id, fecha_pago);

CREATE INDEX IF NOT EXISTS ix_fin_ap_pago_aplicacion_documento
    ON fin.ap_pago_aplicacion (documento_id);

CREATE INDEX IF NOT EXISTS ix_fin_ap_documento_saldo_estado
    ON fin.ap_documento (estado, saldo_pendiente);

-- ------------------------------------------------------------
-- Vista premium de resumen CxP
-- ------------------------------------------------------------
CREATE OR REPLACE VIEW fin.vw_cxp_resumen AS
SELECT
    d.id,
    d.uuid,
    d.proveedor_id,
    p.rut,
    p.razon_social,
    p.nombre_fantasia,
    d.tipo,
    d.estado,
    d.folio,
    d.fecha_emision,
    d.fecha_recepcion,
    d.fecha_vencimiento,
    d.moneda,
    d.tipo_cambio,
    d.neto,
    d.exento,
    d.iva,
    d.otros_impuestos,
    d.total,
    d.saldo_pendiente,
    d.referencia,
    d.observaciones,
    CASE
        WHEN d.saldo_pendiente <= 0 THEN 'PAGADO'
        WHEN d.fecha_vencimiento < CURRENT_DATE THEN 'VENCIDO'
        WHEN d.fecha_vencimiento <= CURRENT_DATE + 7 THEN 'POR_VENCER'
        ELSE 'AL_DIA'
    END AS estado_visual,
    GREATEST((CURRENT_DATE - d.fecha_vencimiento), 0) AS dias_mora,
    COALESCE((
        SELECT SUM(a.monto_aplicado)
        FROM fin.ap_pago_aplicacion a
        WHERE a.documento_id = d.id
    ), 0)::numeric(18,2) AS monto_pagado
FROM fin.ap_documento d
JOIN public.proveedor p
  ON p.id = d.proveedor_id;

COMMIT;