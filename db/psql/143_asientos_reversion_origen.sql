-- 143_asientos_reversion_origen.sql
-- Amplía el índice único parcial para reversiones de negocio.
-- No borra asientos. Reemplaza la definición del índice (DROP + CREATE).

DROP INDEX IF EXISTS public.ux_asientos_origen_idempotente;

CREATE UNIQUE INDEX ux_asientos_origen_idempotente
    ON public.asientos_contables (origen_tipo, origen_id)
    WHERE origen_id > 0
      AND origen_tipo IN (
          'AP_DOCUMENTO',
          'AP_PAGO',
          'AP_DOCUMENTO_REVERSA',
          'NOTA_VENTA',
          'NOTA_VENTA_ANULACION',
          'NOTA_VENTA_REVERSA',
          'PAGO_CLIENTE',
          'LEASING_FIN_ACTIVACION',
          'LOP_ACTIVACION',
          'LOP_FACTURACION',
          'FONDO_RENDIR_ENT',
          'FONDO_RENDIR_ENT_REVERSA',
          'FONDO_RENDIR_LIQ',
          'REMUNERACION_PROVISION',
          'REMUNERACION_PAGO',
          'REV_MANUAL',
          'INVENTARIO_MOV',
          'LOP_DEPRECIACION'
      );

COMMENT ON INDEX public.ux_asientos_origen_idempotente IS
    'Idempotencia contable por (origen_tipo, origen_id), incluidas reversiones de negocio.';
