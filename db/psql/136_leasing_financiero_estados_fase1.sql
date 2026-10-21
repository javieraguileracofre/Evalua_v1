-- 136_leasing_financiero_estados_fase1.sql
-- Amplía chk_comercial_lf_estado con estados canónicos de Fase 1.
-- Idempotente. Requiere dueño de comercial_lf_cotizaciones.

BEGIN;

ALTER TABLE IF EXISTS public.comercial_lf_cotizaciones
    DROP CONSTRAINT IF EXISTS chk_comercial_lf_estado;

ALTER TABLE IF EXISTS public.comercial_lf_cotizaciones
    ADD CONSTRAINT chk_comercial_lf_estado CHECK (
        estado IN (
            'BORRADOR',
            'COTIZADA',
            'EN_ANALISIS_COMERCIAL',
            'EN_ANALISIS_CREDITO',
            'EN_EVALUACION',
            'APROBADA_CONDICIONES',
            'APROBADA',
            'RECHAZADA',
            'EN_FORMALIZACION',
            'DOCUMENTACION_COMPLETA',
            'ACUERDO_FIRMADO',
            'ACTIVO_PENDIENTE_COMPRA',
            'ACTIVO_ADQUIRIDO',
            'ACTIVADA',
            'VIGENTE',
            'ANULADA',
            'PERDIDA_CLIENTE'
        )
    );

COMMIT;
