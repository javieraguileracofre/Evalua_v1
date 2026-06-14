-- db/psql/124_lf_cotizaciones_cleanup_borrador_prueba.sql
-- Elimina cotizaciones de leasing financiero creadas en pruebas (cliente juiste wenoooooo CHUPALOOO).
-- Idempotente: si ya no existen, no hace cambios.

BEGIN;

DO $$
DECLARE
    v_ids BIGINT[];
    v_deleted INT;
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM information_schema.tables
        WHERE table_schema = 'public'
          AND table_name = 'comercial_lf_cotizaciones'
    ) THEN
        RAISE NOTICE '124_lf_cleanup: tabla comercial_lf_cotizaciones no existe; omitido.';
        RETURN;
    END IF;

    SELECT ARRAY_AGG(c.id ORDER BY c.id)
      INTO v_ids
      FROM public.comercial_lf_cotizaciones c
      JOIN public.clientes cl ON cl.id = c.cliente_id
     WHERE c.estado = 'BORRADOR'
       AND c.fecha_cotizacion = DATE '2026-05-21'
       AND cl.razon_social ILIKE '%juiste wenoooooo CHUPALOOO%'
       AND COALESCE(c.workflow_json ->> 'etapa_actual', 'ANALISIS_CREDITO') = 'ANALISIS_CREDITO';

    IF v_ids IS NULL OR cardinality(v_ids) = 0 THEN
        RAISE NOTICE '124_lf_cleanup: sin cotizaciones de prueba para eliminar.';
        RETURN;
    END IF;

    RAISE NOTICE '124_lf_cleanup: eliminando % cotizaciones (ids %).', cardinality(v_ids), v_ids;

    IF EXISTS (
        SELECT 1
        FROM information_schema.tables
        WHERE table_schema = 'public'
          AND table_name = 'credito_solicitud'
    ) THEN
        UPDATE public.credito_solicitud
           SET comercial_lf_cotizacion_id = NULL
         WHERE comercial_lf_cotizacion_id = ANY (v_ids);
    END IF;

    DELETE FROM public.comercial_lf_cotizaciones
     WHERE id = ANY (v_ids);

    GET DIAGNOSTICS v_deleted = ROW_COUNT;
    RAISE NOTICE '124_lf_cleanup: eliminadas % cotizaciones.', v_deleted;
END $$;

COMMIT;
