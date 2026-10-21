-- 146_asientos_cabecera_cuadre.sql
-- La aplicación ya escribe moneda, estado, usuario y fecha_actualizacion.
-- El cuadre debe = haber queda en un trigger diferido, para que varias
-- líneas del mismo asiento se validen al cerrar la transacción.

ALTER TABLE public.asientos_contables
    ADD COLUMN IF NOT EXISTS moneda varchar(10) NOT NULL DEFAULT 'CLP',
    ADD COLUMN IF NOT EXISTS estado varchar(20) NOT NULL DEFAULT 'PUBLICADO',
    ADD COLUMN IF NOT EXISTS usuario varchar(100),
    ADD COLUMN IF NOT EXISTS fecha_actualizacion timestamp without time zone;

UPDATE public.asientos_contables
SET fecha_actualizacion = fecha_creacion
WHERE fecha_actualizacion IS NULL;

ALTER TABLE public.asientos_contables
    ALTER COLUMN fecha_actualizacion SET DEFAULT now(),
    ALTER COLUMN fecha_actualizacion SET NOT NULL;

UPDATE public.asientos_contables
SET glosa = LEFT(descripcion, 255)
WHERE (glosa IS NULL OR btrim(glosa) = '')
  AND descripcion IS NOT NULL
  AND btrim(descripcion) <> '';

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'chk_asiento_estado'
    ) THEN
        ALTER TABLE public.asientos_contables
            ADD CONSTRAINT chk_asiento_estado
            CHECK (estado IN ('PUBLICADO', 'ANULADO')) NOT VALID;
    END IF;
END $$;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'chk_asiento_detalle_debe_nonneg'
    ) THEN
        ALTER TABLE public.asientos_detalle
            ADD CONSTRAINT chk_asiento_detalle_debe_nonneg
            CHECK (debe >= 0) NOT VALID;
    END IF;
END $$;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'chk_asiento_detalle_haber_nonneg'
    ) THEN
        ALTER TABLE public.asientos_detalle
            ADD CONSTRAINT chk_asiento_detalle_haber_nonneg
            CHECK (haber >= 0) NOT VALID;
    END IF;
END $$;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'chk_asiento_detalle_un_lado'
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

DROP TRIGGER IF EXISTS trg_validar_asiento_cuadrado ON public.asientos_detalle;

CREATE CONSTRAINT TRIGGER trg_validar_asiento_cuadrado
AFTER INSERT OR UPDATE OR DELETE
ON public.asientos_detalle
DEFERRABLE INITIALLY DEFERRED
FOR EACH ROW
EXECUTE FUNCTION public.fn_validar_asiento_cuadrado();
