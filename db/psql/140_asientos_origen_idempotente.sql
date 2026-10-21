-- 140_asientos_origen_idempotente.sql
-- Protección PostgreSQL contra doble contabilización concurrente.
-- Índice único parcial: solo orígenes de negocio con origen_id > 0.
-- NO incluye MANUAL_* (múltiples asientos legítimos con origen_id=0).
-- SÍ incluye LOP_DEPRECIACION cuando origen_id = id de fila de depreciación
-- (un asiento por periodo/activo, no por activo).

-- Preflight: si hay duplicados, este script fallará al crear el índice.
-- Operación: listar conflictos con:
--   SELECT origen_tipo, origen_id, COUNT(*), array_agg(id ORDER BY id)
--   FROM asientos_contables
--   WHERE origen_id > 0
--     AND origen_tipo IN (
--       'AP_DOCUMENTO','AP_PAGO','NOTA_VENTA','NOTA_VENTA_ANULACION','PAGO_CLIENTE',
--       'LEASING_FIN_ACTIVACION','LOP_ACTIVACION','LOP_FACTURACION',
--       'FONDO_RENDIR_ENT','FONDO_RENDIR_LIQ','REMUNERACION_PROVISION','REMUNERACION_PAGO',
--       'REV_MANUAL','INVENTARIO_MOV','LOP_DEPRECIACION'
--     )
--   GROUP BY 1,2 HAVING COUNT(*) > 1;

-- Retirar índice legado demasiado amplio (incluye origen_id=0 y LOP_DEPRECIACION).
DROP INDEX IF EXISTS public.ux_asientos_origen_unico;

CREATE UNIQUE INDEX IF NOT EXISTS ux_asientos_origen_idempotente
    ON public.asientos_contables (origen_tipo, origen_id)
    WHERE origen_id > 0
      AND origen_tipo IN (
          'AP_DOCUMENTO',
          'AP_PAGO',
          'NOTA_VENTA',
          'NOTA_VENTA_ANULACION',
          'PAGO_CLIENTE',
          'LEASING_FIN_ACTIVACION',
          'LOP_ACTIVACION',
          'LOP_FACTURACION',
          'FONDO_RENDIR_ENT',
          'FONDO_RENDIR_LIQ',
          'REMUNERACION_PROVISION',
          'REMUNERACION_PAGO',
          'REV_MANUAL',
          'INVENTARIO_MOV',
          'LOP_DEPRECIACION'
      );

CREATE INDEX IF NOT EXISTS ix_asientos_contables_fecha_origen
    ON public.asientos_contables (fecha DESC, origen_tipo);

COMMENT ON INDEX public.ux_asientos_origen_idempotente IS
    'Idempotencia contable concurrente por (origen_tipo, origen_id) en orígenes de negocio.';
