-- Requerido antes de create_all (modelo Proveedor con columna generada).
-- Debe ser IMMUTABLE para usarla en GENERATED ALWAYS AS ... STORED (PostgreSQL 14+).
CREATE OR REPLACE FUNCTION public.fn_normalizar_rut(p_rut TEXT)
RETURNS TEXT
LANGUAGE sql
IMMUTABLE
PARALLEL SAFE
AS $$
    SELECT UPPER(
        REPLACE(REPLACE(REPLACE(COALESCE(TRIM(p_rut), ''), '.', ''), '-', ''), ' ', '')
    );
$$;
