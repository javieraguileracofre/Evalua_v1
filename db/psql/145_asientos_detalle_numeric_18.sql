-- 145_asientos_detalle_numeric_18.sql
-- El detalle del asiento admite la misma magnitud que documentos y CxP.
-- PostgreSQL no cambia el tipo de una columna usada por una vista: hay que
-- quitar analytics_resultado_mes y volver a crearla con la misma definición.

DROP VIEW IF EXISTS public.analytics_resultado_mes;

ALTER TABLE public.asientos_detalle
    ALTER COLUMN debe TYPE numeric(18, 2),
    ALTER COLUMN haber TYPE numeric(18, 2);

ALTER TABLE public.app_metadata
    ALTER COLUMN app_version TYPE varchar(64);

CREATE VIEW public.analytics_resultado_mes AS
SELECT
    CAST(EXTRACT(YEAR FROM a.fecha) AS integer) AS anio,
    CAST(EXTRACT(MONTH FROM a.fecha) AS integer) AS mes,
    d.codigo_cuenta,
    SUM(d.debe) AS debe,
    SUM(d.haber) AS haber
FROM public.asientos_contables a
JOIN public.asientos_detalle d ON d.asiento_id = a.id
GROUP BY 1, 2, 3;
