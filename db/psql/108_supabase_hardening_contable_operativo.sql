BEGIN;

-- ============================================================
-- 108_supabase_hardening_contable_operativo.sql
-- Hardening contable/operativo para Supabase (idempotente)
-- ============================================================

-- 1) ASIENTOS CONTABLES: integridad de detalle
DO $$
BEGIN
    IF EXISTS (
        SELECT 1
        FROM information_schema.tables
        WHERE table_schema = 'public' AND table_name = 'asientos_detalle'
    ) AND NOT EXISTS (
        SELECT 1
        FROM pg_constraint
        WHERE conname = 'chk_asiento_detalle_debe_nonneg'
    ) THEN
        ALTER TABLE public.asientos_detalle
            ADD CONSTRAINT chk_asiento_detalle_debe_nonneg
            CHECK (debe >= 0) NOT VALID;
    END IF;
END $$;

DO $$
BEGIN
    IF EXISTS (
        SELECT 1
        FROM information_schema.tables
        WHERE table_schema = 'public' AND table_name = 'asientos_detalle'
    ) AND NOT EXISTS (
        SELECT 1
        FROM pg_constraint
        WHERE conname = 'chk_asiento_detalle_haber_nonneg'
    ) THEN
        ALTER TABLE public.asientos_detalle
            ADD CONSTRAINT chk_asiento_detalle_haber_nonneg
            CHECK (haber >= 0) NOT VALID;
    END IF;
END $$;

DO $$
BEGIN
    IF EXISTS (
        SELECT 1
        FROM information_schema.tables
        WHERE table_schema = 'public' AND table_name = 'asientos_detalle'
    ) AND NOT EXISTS (
        SELECT 1
        FROM pg_constraint
        WHERE conname = 'chk_asiento_detalle_un_lado'
    ) THEN
        ALTER TABLE public.asientos_detalle
            ADD CONSTRAINT chk_asiento_detalle_un_lado
            CHECK (
                (debe = 0 AND haber > 0)
                OR
                (haber = 0 AND debe > 0)
            ) NOT VALID;
    END IF;
END $$;

-- 2) ASIENTOS CONTABLES: unicidad por origen para evitar doble contabilización
DO $$
BEGIN
    IF EXISTS (
        SELECT 1
        FROM information_schema.tables
        WHERE table_schema = 'public' AND table_name = 'asientos_contables'
    ) THEN
        CREATE UNIQUE INDEX IF NOT EXISTS ux_asientos_origen_unico
            ON public.asientos_contables (origen_tipo, origen_id)
            WHERE origen_tipo IS NOT NULL AND origen_id IS NOT NULL;

        CREATE INDEX IF NOT EXISTS ix_asientos_origen_fecha
            ON public.asientos_contables (origen_tipo, origen_id, fecha);
    END IF;
END $$;

-- 3) TRIGGER: validar que cada asiento cierre (debe = haber)
CREATE OR REPLACE FUNCTION public.fn_validar_asiento_cuadrado()
RETURNS trigger
LANGUAGE plpgsql
AS $$
DECLARE
    _asiento_id bigint;
    _debe numeric(18,2);
    _haber numeric(18,2);
BEGIN
    _asiento_id := COALESCE(NEW.asiento_id, OLD.asiento_id);

    SELECT
        COALESCE(SUM(d.debe), 0)::numeric(18,2),
        COALESCE(SUM(d.haber), 0)::numeric(18,2)
    INTO _debe, _haber
    FROM public.asientos_detalle d
    WHERE d.asiento_id = _asiento_id;

    IF _debe <> _haber THEN
        RAISE EXCEPTION
            'Asiento % descuadrado: debe=% haber=%',
            _asiento_id, _debe, _haber
            USING ERRCODE = '23514';
    END IF;

    RETURN NULL;
END;
$$;

DO $$
BEGIN
    IF EXISTS (
        SELECT 1
        FROM information_schema.tables
        WHERE table_schema = 'public' AND table_name = 'asientos_detalle'
    ) THEN
        DROP TRIGGER IF EXISTS trg_validar_asiento_cuadrado ON public.asientos_detalle;
        CREATE CONSTRAINT TRIGGER trg_validar_asiento_cuadrado
        AFTER INSERT OR UPDATE OR DELETE
        ON public.asientos_detalle
        DEFERRABLE INITIALLY DEFERRED
        FOR EACH ROW
        EXECUTE FUNCTION public.fn_validar_asiento_cuadrado();
    END IF;
END $$;

-- 4) CxC / CxP: calidad de datos de fechas y saldos
DO $$
BEGIN
    IF EXISTS (
        SELECT 1
        FROM information_schema.tables
        WHERE table_schema = 'public' AND table_name = 'cuentas_por_cobrar'
    ) AND NOT EXISTS (
        SELECT 1
        FROM pg_constraint
        WHERE conname = 'chk_cxc_saldos'
    ) THEN
        ALTER TABLE public.cuentas_por_cobrar
            ADD CONSTRAINT chk_cxc_saldos
            CHECK (
                monto_original >= 0
                AND saldo_pendiente >= 0
                AND saldo_pendiente <= monto_original
            ) NOT VALID;
    END IF;
END $$;

DO $$
BEGIN
    IF EXISTS (
        SELECT 1
        FROM information_schema.tables
        WHERE table_schema = 'public' AND table_name = 'cuentas_por_cobrar'
    ) AND NOT EXISTS (
        SELECT 1
        FROM pg_constraint
        WHERE conname = 'chk_cxc_fechas'
    ) THEN
        ALTER TABLE public.cuentas_por_cobrar
            ADD CONSTRAINT chk_cxc_fechas
            CHECK (fecha_vencimiento >= fecha_emision) NOT VALID;
    END IF;
END $$;

DO $$
BEGIN
    IF EXISTS (
        SELECT 1
        FROM information_schema.tables
        WHERE table_schema = 'public' AND table_name = 'cuentas_por_pagar'
    ) AND NOT EXISTS (
        SELECT 1
        FROM pg_constraint
        WHERE conname = 'chk_cxp_saldos'
    ) THEN
        ALTER TABLE public.cuentas_por_pagar
            ADD CONSTRAINT chk_cxp_saldos
            CHECK (
                monto_original >= 0
                AND saldo_pendiente >= 0
                AND saldo_pendiente <= monto_original
            ) NOT VALID;
    END IF;
END $$;

DO $$
BEGIN
    IF EXISTS (
        SELECT 1
        FROM information_schema.tables
        WHERE table_schema = 'public' AND table_name = 'cuentas_por_pagar'
    ) AND NOT EXISTS (
        SELECT 1
        FROM pg_constraint
        WHERE conname = 'chk_cxp_fechas'
    ) THEN
        ALTER TABLE public.cuentas_por_pagar
            ADD CONSTRAINT chk_cxp_fechas
            CHECK (fecha_vencimiento >= fecha_emision) NOT VALID;
    END IF;
END $$;

-- 5) Índices operativos para cobranza / pagos / inventario
DO $$
BEGIN
    IF EXISTS (
        SELECT 1
        FROM information_schema.tables
        WHERE table_schema = 'public' AND table_name = 'cuentas_por_cobrar'
    ) THEN
        CREATE INDEX IF NOT EXISTS ix_cxc_cliente_estado_venc
            ON public.cuentas_por_cobrar (cliente_id, estado, fecha_vencimiento);
    END IF;
END $$;

DO $$
BEGIN
    IF EXISTS (
        SELECT 1
        FROM information_schema.tables
        WHERE table_schema = 'public' AND table_name = 'cuentas_por_pagar'
    ) THEN
        CREATE INDEX IF NOT EXISTS ix_cxp_proveedor_estado_venc
            ON public.cuentas_por_pagar (proveedor_id, estado, fecha_vencimiento);
    END IF;
END $$;

DO $$
BEGIN
    IF EXISTS (
        SELECT 1
        FROM information_schema.tables
        WHERE table_schema = 'public' AND table_name = 'inventario_movimientos'
    ) THEN
        CREATE INDEX IF NOT EXISTS ix_inventario_producto_fecha
            ON public.inventario_movimientos (producto_id, fecha);
    END IF;
END $$;

-- 6) Vista de auditoría para detectar objetos duplicados entre esquemas fin/public
CREATE OR REPLACE VIEW public.vw_schema_objetos_duplicados AS
WITH t AS (
    SELECT table_name
    FROM information_schema.tables
    WHERE table_schema = 'public' AND table_type = 'BASE TABLE'
), f AS (
    SELECT table_name
    FROM information_schema.tables
    WHERE table_schema = 'fin' AND table_type = 'BASE TABLE'
)
SELECT
    p.table_name AS objeto
FROM t p
INNER JOIN f n ON n.table_name = p.table_name
ORDER BY p.table_name;

-- 7) Validar constraints agregadas (si hay datos sucios, esta sección fallará
--    y mostrará exactamente dónde limpiar antes de reintentar)
ALTER TABLE IF EXISTS public.asientos_detalle
    VALIDATE CONSTRAINT chk_asiento_detalle_debe_nonneg;
ALTER TABLE IF EXISTS public.asientos_detalle
    VALIDATE CONSTRAINT chk_asiento_detalle_haber_nonneg;
ALTER TABLE IF EXISTS public.asientos_detalle
    VALIDATE CONSTRAINT chk_asiento_detalle_un_lado;

ALTER TABLE IF EXISTS public.cuentas_por_cobrar
    VALIDATE CONSTRAINT chk_cxc_saldos;
ALTER TABLE IF EXISTS public.cuentas_por_cobrar
    VALIDATE CONSTRAINT chk_cxc_fechas;

ALTER TABLE IF EXISTS public.cuentas_por_pagar
    VALIDATE CONSTRAINT chk_cxp_saldos;
ALTER TABLE IF EXISTS public.cuentas_por_pagar
    VALIDATE CONSTRAINT chk_cxp_fechas;

COMMIT;

