-- db/psql/125_credito_riesgo_empresarial.sql
-- Módulo crédito empresarial: segmentación PYME/Mediana/Gran Empresa,
-- evaluación financiera/cualitativa, documentos, límites y auditoría.
-- Idempotente. Requiere credito_solicitud (101/110).

BEGIN;

-- ============================================================
-- Solicitud: segmentación, variables empresariales, aprobación
-- ============================================================

ALTER TABLE IF EXISTS public.credito_solicitud
    ADD COLUMN IF NOT EXISTS segmento_cliente VARCHAR(30) NOT NULL DEFAULT 'PYME';

ALTER TABLE IF EXISTS public.credito_solicitud
    ADD COLUMN IF NOT EXISTS segmento_manual BOOLEAN NOT NULL DEFAULT FALSE;

ALTER TABLE IF EXISTS public.credito_solicitud
    ADD COLUMN IF NOT EXISTS numero_trabajadores INTEGER NOT NULL DEFAULT 0;

ALTER TABLE IF EXISTS public.credito_solicitud
    ADD COLUMN IF NOT EXISTS deuda_financiera NUMERIC(18, 2) NOT NULL DEFAULT 0;

ALTER TABLE IF EXISTS public.credito_solicitud
    ADD COLUMN IF NOT EXISTS gastos_financieros_anual NUMERIC(18, 2) NOT NULL DEFAULT 0;

ALTER TABLE IF EXISTS public.credito_solicitud
    ADD COLUMN IF NOT EXISTS concentracion_proveedores_pct NUMERIC(6, 2) NOT NULL DEFAULT 0;

ALTER TABLE IF EXISTS public.credito_solicitud
    ADD COLUMN IF NOT EXISTS score_buro INTEGER NULL;

ALTER TABLE IF EXISTS public.credito_solicitud
    ADD COLUMN IF NOT EXISTS score_buro_estado VARCHAR(20) NOT NULL DEFAULT 'SIN_INFO';

ALTER TABLE IF EXISTS public.credito_solicitud
    ADD COLUMN IF NOT EXISTS datos_buro_json JSONB NOT NULL DEFAULT '{}'::jsonb;

ALTER TABLE IF EXISTS public.credito_solicitud
    ADD COLUMN IF NOT EXISTS evaluacion_cualitativa_input JSONB NOT NULL DEFAULT '{}'::jsonb;

ALTER TABLE IF EXISTS public.credito_solicitud
    ADD COLUMN IF NOT EXISTS creado_por VARCHAR(200) NOT NULL DEFAULT 'sistema';

ALTER TABLE IF EXISTS public.credito_solicitud
    ADD COLUMN IF NOT EXISTS analista_asignado VARCHAR(200) NULL;

ALTER TABLE IF EXISTS public.credito_solicitud
    ADD COLUMN IF NOT EXISTS monto_aprobado NUMERIC(18, 2) NULL;

ALTER TABLE IF EXISTS public.credito_solicitud
    ADD COLUMN IF NOT EXISTS plazo_aprobado INTEGER NULL;

ALTER TABLE IF EXISTS public.credito_solicitud
    ADD COLUMN IF NOT EXISTS garantias_requeridas TEXT NOT NULL DEFAULT '';

ALTER TABLE IF EXISTS public.credito_solicitud
    ADD COLUMN IF NOT EXISTS condiciones_aprobacion TEXT NOT NULL DEFAULT '';

ALTER TABLE IF EXISTS public.credito_solicitud
    ADD COLUMN IF NOT EXISTS nivel_comite_requerido VARCHAR(40) NULL;

ALTER TABLE IF EXISTS public.credito_solicitud
    ADD COLUMN IF NOT EXISTS justificacion_decision TEXT NOT NULL DEFAULT '';

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'chk_credito_sol_segmento'
    ) THEN
        ALTER TABLE public.credito_solicitud
            ADD CONSTRAINT chk_credito_sol_segmento
            CHECK (segmento_cliente IN ('PYME', 'MEDIANA', 'GRAN_EMPRESA'));
    END IF;
END $$;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'chk_credito_sol_buro_estado'
    ) THEN
        ALTER TABLE public.credito_solicitud
            ADD CONSTRAINT chk_credito_sol_buro_estado
            CHECK (score_buro_estado IN ('SIN_INFO', 'FAVORABLE', 'NEUTRO', 'DESFAVORABLE', 'CRITICO'));
    END IF;
END $$;

CREATE INDEX IF NOT EXISTS ix_credito_sol_segmento
    ON public.credito_solicitud (segmento_cliente, estado);

-- ============================================================
-- Evaluación: desglose v2 empresarial
-- ============================================================

ALTER TABLE IF EXISTS public.credito_evaluacion
    ADD COLUMN IF NOT EXISTS segmento_cliente VARCHAR(30) NULL;

ALTER TABLE IF EXISTS public.credito_evaluacion
    ADD COLUMN IF NOT EXISTS nivel_riesgo VARCHAR(20) NULL;

ALTER TABLE IF EXISTS public.credito_evaluacion
    ADD COLUMN IF NOT EXISTS alertas_json JSONB NOT NULL DEFAULT '[]'::jsonb;

ALTER TABLE IF EXISTS public.credito_evaluacion
    ADD COLUMN IF NOT EXISTS condiciones_sugeridas_json JSONB NOT NULL DEFAULT '[]'::jsonb;

ALTER TABLE IF EXISTS public.credito_evaluacion
    ADD COLUMN IF NOT EXISTS motivos_json JSONB NOT NULL DEFAULT '[]'::jsonb;

ALTER TABLE IF EXISTS public.credito_evaluacion
    ADD COLUMN IF NOT EXISTS evaluacion_financiera_json JSONB NOT NULL DEFAULT '{}'::jsonb;

ALTER TABLE IF EXISTS public.credito_evaluacion
    ADD COLUMN IF NOT EXISTS evaluacion_cualitativa_json JSONB NOT NULL DEFAULT '{}'::jsonb;

ALTER TABLE IF EXISTS public.credito_evaluacion
    ADD COLUMN IF NOT EXISTS pricing_json JSONB NOT NULL DEFAULT '{}'::jsonb;

ALTER TABLE IF EXISTS public.credito_evaluacion
    ADD COLUMN IF NOT EXISTS comite_atribucion VARCHAR(40) NULL;

ALTER TABLE IF EXISTS public.credito_evaluacion
    ADD COLUMN IF NOT EXISTS evaluado_por VARCHAR(200) NOT NULL DEFAULT 'sistema';

-- Ampliar clasificación de riesgo (CRITICO)
ALTER TABLE public.credito_evaluacion DROP CONSTRAINT IF EXISTS chk_credito_eval_clasif;
ALTER TABLE public.credito_evaluacion
    ADD CONSTRAINT chk_credito_eval_clasif
    CHECK (clasificacion_riesgo IN ('BAJO', 'MEDIO', 'ALTO', 'CRITICO', 'RECHAZADO'));

-- Ampliar recomendaciones
ALTER TABLE public.credito_evaluacion DROP CONSTRAINT IF EXISTS chk_credito_eval_rec;
ALTER TABLE public.credito_evaluacion
    ADD CONSTRAINT chk_credito_eval_rec
    CHECK (recomendacion IN (
        'APROBAR', 'CONDICIONES', 'COMITE', 'RECHAZAR', 'SOLICITAR_ANTECEDENTES'
    ));

-- ============================================================
-- Documentos: gestión por segmento
-- ============================================================

ALTER TABLE IF EXISTS public.credito_documento
    ADD COLUMN IF NOT EXISTS estado VARCHAR(20) NOT NULL DEFAULT 'PENDIENTE';

ALTER TABLE IF EXISTS public.credito_documento
    ADD COLUMN IF NOT EXISTS requerido BOOLEAN NOT NULL DEFAULT TRUE;

ALTER TABLE IF EXISTS public.credito_documento
    ADD COLUMN IF NOT EXISTS observaciones TEXT NOT NULL DEFAULT '';

ALTER TABLE IF EXISTS public.credito_documento
    ADD COLUMN IF NOT EXISTS validado_por VARCHAR(200) NULL;

ALTER TABLE IF EXISTS public.credito_documento
    ADD COLUMN IF NOT EXISTS validado_en TIMESTAMPTZ NULL;

ALTER TABLE IF EXISTS public.credito_documento
    ADD COLUMN IF NOT EXISTS actualizado_en TIMESTAMPTZ NOT NULL DEFAULT NOW();

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'chk_credito_doc_estado'
    ) THEN
        ALTER TABLE public.credito_documento
            ADD CONSTRAINT chk_credito_doc_estado
            CHECK (estado IN ('PENDIENTE', 'RECIBIDO', 'VALIDADO', 'RECHAZADO', 'NO_APLICA'));
    END IF;
END $$;

-- ============================================================
-- Políticas parametrizables
-- ============================================================

INSERT INTO public.credito_politica (clave, valor_json, descripcion)
VALUES
(
    'segmentacion_empresarial_v1',
    '{
      "uf_referencia_clp": 38000,
      "pyme_ventas_max_uf": 25000,
      "pyme_trabajadores_max": 49,
      "mediana_ventas_max_uf": 100000,
      "mediana_trabajadores_max": 199,
      "sectores_alto_riesgo": ["construccion", "retail", "transporte"],
      "nota": "Umbrales referenciales SII/Chile. Ventas en UF anual; trabajadores según registro interno."
    }'::jsonb,
    'Clasificación automática PYME / Mediana / Gran Empresa.'
),
(
    'ponderaciones_pyme_v1',
    '{
      "capacidad_pago": 0.30,
      "historial_pago": 0.25,
      "endeudamiento": 0.10,
      "liquidez_flujo": 0.20,
      "antiguedad": 0.05,
      "garantias": 0.05,
      "macro_sectorial": 0.05
    }'::jsonb,
    'Pesos score segmento PYME (flujo caja, comportamiento pago).'
),
(
    'ponderaciones_mediana_v1',
    '{
      "capacidad_pago": 0.20,
      "historial_pago": 0.20,
      "endeudamiento": 0.20,
      "liquidez_flujo": 0.15,
      "antiguedad": 0.05,
      "garantias": 0.10,
      "macro_sectorial": 0.10
    }'::jsonb,
    'Pesos score segmento Mediana Empresa (EEFF, EBITDA, cobertura).'
),
(
    'ponderaciones_gran_v1',
    '{
      "capacidad_pago": 0.15,
      "historial_pago": 0.15,
      "endeudamiento": 0.25,
      "liquidez_flujo": 0.15,
      "antiguedad": 0.05,
      "garantias": 0.10,
      "macro_sectorial": 0.15
    }'::jsonb,
    'Pesos score segmento Gran Empresa (consolidado, sector, covenants).'
),
(
    'documentos_por_segmento_v1',
    '{
      "PYME": [
        "CARPETA_TRIBUTARIA", "IVA_F29", "BALANCE", "CERTIFICADO_DEUDA",
        "ESTADOS_FINANCIEROS", "DECLARACION_RENTA"
      ],
      "MEDIANA": [
        "CARPETA_TRIBUTARIA", "IVA_F29", "BALANCE", "ESTADOS_FINANCIEROS",
        "DECLARACION_RENTA", "CERTIFICADO_DEUDA", "DOCUMENTOS_SOCIETARIOS", "GARANTIAS"
      ],
      "GRAN_EMPRESA": [
        "CARPETA_TRIBUTARIA", "IVA_F29", "BALANCE", "ESTADOS_FINANCIEROS",
        "DECLARACION_RENTA", "CERTIFICADO_DEUDA", "DOCUMENTOS_SOCIETARIOS",
        "GARANTIAS", "EEFF_CONSOLIDADOS", "COVENANTS", "INFORME_DICOM"
      ],
      "labels": {
        "CARPETA_TRIBUTARIA": "Carpeta tributaria SII",
        "IVA_F29": "Formulario IVA F29",
        "BALANCE": "Balance general",
        "ESTADOS_FINANCIEROS": "Estados financieros auditados / firmados",
        "DECLARACION_RENTA": "Declaración de renta (F22)",
        "CERTIFICADO_DEUDA": "Certificado de deuda CMF/SBIF",
        "DOCUMENTOS_SOCIETARIOS": "Extracto / escritura societaria",
        "GARANTIAS": "Documentación de garantías",
        "EEFF_CONSOLIDADOS": "EEFF consolidados grupo",
        "COVENANTS": "Covenants financieros vigentes",
        "INFORME_DICOM": "Informe DICOM / boletín comercial (placeholder)"
      }
    }'::jsonb,
    'Checklist documental por segmento de cliente.'
),
(
    'atribuciones_comite_v1',
    '{
      "PYME": {"hasta_clp": 50000000, "nivel": "ANALISTA_SENIOR"},
      "MEDIANA": {"hasta_clp": 300000000, "nivel": "COMITE_LOCAL"},
      "GRAN_EMPRESA": {"hasta_clp": 2000000000, "nivel": "COMITE_CORPORATIVO"},
      "sobre_limite": "COMITE_DIRECTORIO",
      "nota": "Montos en CLP. Integración CMF/atribuciones internas."
    }'::jsonb,
    'Niveles de aprobación según segmento y monto (Chile).'
)
ON CONFLICT (clave) DO NOTHING;

-- Ampliar estados de solicitud
ALTER TABLE public.credito_solicitud DROP CONSTRAINT IF EXISTS chk_credito_sol_estado;
ALTER TABLE public.credito_solicitud
    ADD CONSTRAINT chk_credito_sol_estado
    CHECK (estado IN (
        'BORRADOR', 'EN_EVALUACION', 'APROBADA', 'RECHAZADA', 'COMITE',
        'CONDICIONES', 'ARCHIVADA', 'SOLICITAR_ANTECEDENTES'
    ));

COMMIT;
