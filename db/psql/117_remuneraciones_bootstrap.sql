-- 117_remuneraciones_bootstrap.sql
-- Esquema completo de remuneraciones + columnas empleados/periodo (idempotente).
-- Ejecutar en la BD del tenant (PostgreSQL) si /remuneraciones falla por tablas o columnas faltantes.

BEGIN;

-- --- conceptos (sin FK externas)
CREATE TABLE IF NOT EXISTS public.conceptos_remuneracion (
  id BIGSERIAL PRIMARY KEY,
  codigo VARCHAR(40) NOT NULL,
  nombre VARCHAR(160) NOT NULL,
  descripcion TEXT,
  tipo VARCHAR(40) NOT NULL,
  imponible BOOLEAN NOT NULL DEFAULT FALSE,
  tributable BOOLEAN NOT NULL DEFAULT FALSE,
  legal BOOLEAN NOT NULL DEFAULT FALSE,
  afecta_liquido BOOLEAN NOT NULL DEFAULT TRUE,
  formula VARCHAR(500),
  regla_calculo VARCHAR(80),
  origen VARCHAR(40),
  activo BOOLEAN NOT NULL DEFAULT TRUE,
  orden INTEGER NOT NULL DEFAULT 0,
  created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMP WITHOUT TIME ZONE NOT NULL DEFAULT NOW()
);
CREATE UNIQUE INDEX IF NOT EXISTS uq_conceptos_remuneracion_codigo
  ON public.conceptos_remuneracion (codigo);
CREATE INDEX IF NOT EXISTS ix_conceptos_remuneracion_activo
  ON public.conceptos_remuneracion (activo);

CREATE TABLE IF NOT EXISTS public.remuneracion_parametros (
  id BIGSERIAL PRIMARY KEY,
  clave VARCHAR(80) NOT NULL,
  valor_numerico NUMERIC(18,6),
  valor_texto VARCHAR(500),
  descripcion VARCHAR(255),
  updated_at TIMESTAMP WITHOUT TIME ZONE NOT NULL DEFAULT NOW()
);
CREATE UNIQUE INDEX IF NOT EXISTS uq_remuneracion_parametros_clave
  ON public.remuneracion_parametros (clave);

-- --- contratos (FKs en bloque DO)
CREATE TABLE IF NOT EXISTS public.contratos_laborales (
  id BIGSERIAL PRIMARY KEY,
  empleado_id BIGINT NOT NULL,
  fecha_inicio DATE NOT NULL,
  fecha_fin DATE,
  tipo_contrato VARCHAR(40),
  jornada VARCHAR(40),
  sueldo_base NUMERIC(18,2) NOT NULL,
  centro_costo_id BIGINT,
  estado VARCHAR(20) NOT NULL DEFAULT 'VIGENTE',
  observaciones TEXT,
  created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMP WITHOUT TIME ZONE NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS ix_contratos_laborales_empleado ON public.contratos_laborales (empleado_id);
CREATE INDEX IF NOT EXISTS ix_contratos_laborales_vigencia ON public.contratos_laborales (estado, fecha_inicio);

CREATE TABLE IF NOT EXISTS public.periodos_remuneracion (
  id BIGSERIAL PRIMARY KEY,
  anio INTEGER NOT NULL,
  mes INTEGER NOT NULL,
  fecha_inicio DATE NOT NULL,
  fecha_fin DATE NOT NULL,
  estado VARCHAR(32) NOT NULL DEFAULT 'BORRADOR',
  fecha_calculo TIMESTAMP WITHOUT TIME ZONE,
  fecha_cierre TIMESTAMP WITHOUT TIME ZONE,
  fecha_pago TIMESTAMP WITHOUT TIME ZONE,
  usuario_creador_id BIGINT,
  usuario_aprobador_rrhh_id BIGINT,
  usuario_aprobador_finanzas_id BIGINT,
  observaciones TEXT,
  asiento_pago_id BIGINT,
  created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMP WITHOUT TIME ZONE NOT NULL DEFAULT NOW()
);
CREATE UNIQUE INDEX IF NOT EXISTS uq_periodos_remuneracion_anio_mes
  ON public.periodos_remuneracion (anio, mes);
CREATE INDEX IF NOT EXISTS ix_periodos_remuneracion_estado ON public.periodos_remuneracion (estado);

CREATE TABLE IF NOT EXISTS public.detalle_remuneraciones (
  id BIGSERIAL PRIMARY KEY,
  periodo_remuneracion_id BIGINT NOT NULL,
  empleado_id BIGINT NOT NULL,
  contrato_laboral_id BIGINT,
  cargo_snapshot VARCHAR(120),
  centro_costo_id BIGINT,
  camion_id BIGINT,
  dias_trabajados INTEGER NOT NULL DEFAULT 0,
  dias_ausencia INTEGER NOT NULL DEFAULT 0,
  horas_ordinarias NUMERIC(12,2) NOT NULL DEFAULT 0,
  horas_extras NUMERIC(12,2) NOT NULL DEFAULT 0,
  horas_nocturnas NUMERIC(12,2) NOT NULL DEFAULT 0,
  total_haberes_imponibles NUMERIC(18,2) NOT NULL DEFAULT 0,
  total_haberes_no_imponibles NUMERIC(18,2) NOT NULL DEFAULT 0,
  total_descuentos_legales NUMERIC(18,2) NOT NULL DEFAULT 0,
  total_otros_descuentos NUMERIC(18,2) NOT NULL DEFAULT 0,
  total_aportes_empresa NUMERIC(18,2) NOT NULL DEFAULT 0,
  liquido_a_pagar NUMERIC(18,2) NOT NULL DEFAULT 0,
  estado VARCHAR(24) NOT NULL DEFAULT 'CALCULADO',
  observaciones TEXT,
  created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMP WITHOUT TIME ZONE NOT NULL DEFAULT NOW()
);
CREATE UNIQUE INDEX IF NOT EXISTS uq_detalle_periodo_empleado
  ON public.detalle_remuneraciones (periodo_remuneracion_id, empleado_id);
CREATE INDEX IF NOT EXISTS ix_detalle_remuneraciones_periodo ON public.detalle_remuneraciones (periodo_remuneracion_id);
CREATE INDEX IF NOT EXISTS ix_detalle_remuneraciones_empleado ON public.detalle_remuneraciones (empleado_id);

CREATE TABLE IF NOT EXISTS public.items_remuneracion (
  id BIGSERIAL PRIMARY KEY,
  detalle_remuneracion_id BIGINT NOT NULL,
  concepto_remuneracion_id BIGINT NOT NULL,
  cantidad NUMERIC(18,4) NOT NULL DEFAULT 1,
  valor_unitario NUMERIC(18,4) NOT NULL DEFAULT 0,
  monto_total NUMERIC(18,2) NOT NULL,
  origen VARCHAR(40),
  referencia_tipo VARCHAR(40),
  referencia_id BIGINT,
  es_ajuste_manual BOOLEAN NOT NULL DEFAULT FALSE,
  usuario_ajuste_id BIGINT,
  motivo_ajuste TEXT,
  observaciones TEXT,
  created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMP WITHOUT TIME ZONE NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS ix_items_remuneracion_detalle ON public.items_remuneracion (detalle_remuneracion_id);
CREATE INDEX IF NOT EXISTS ix_items_remuneracion_concepto ON public.items_remuneracion (concepto_remuneracion_id);
CREATE INDEX IF NOT EXISTS ix_items_remuneracion_ref ON public.items_remuneracion (referencia_tipo, referencia_id);

-- --- FKs condicionales
DO $$
BEGIN
  IF to_regclass('public.empleados') IS NOT NULL THEN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'fk_contratos_laborales_empleado') THEN
      ALTER TABLE public.contratos_laborales
        ADD CONSTRAINT fk_contratos_laborales_empleado
        FOREIGN KEY (empleado_id) REFERENCES public.empleados(id) ON DELETE RESTRICT;
    END IF;
  END IF;

  IF to_regclass('fin.centro_costo') IS NOT NULL THEN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'fk_contratos_laborales_centro_costo') THEN
      ALTER TABLE public.contratos_laborales
        ADD CONSTRAINT fk_contratos_laborales_centro_costo
        FOREIGN KEY (centro_costo_id) REFERENCES fin.centro_costo(id) ON DELETE SET NULL;
    END IF;
  END IF;

  IF to_regclass('public.auth_usuarios') IS NOT NULL THEN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'fk_periodos_rem_usuario_creador') THEN
      ALTER TABLE public.periodos_remuneracion
        ADD CONSTRAINT fk_periodos_rem_usuario_creador
        FOREIGN KEY (usuario_creador_id) REFERENCES public.auth_usuarios(id) ON DELETE SET NULL;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'fk_periodos_rem_usuario_apr_rrhh') THEN
      ALTER TABLE public.periodos_remuneracion
        ADD CONSTRAINT fk_periodos_rem_usuario_apr_rrhh
        FOREIGN KEY (usuario_aprobador_rrhh_id) REFERENCES public.auth_usuarios(id) ON DELETE SET NULL;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'fk_periodos_rem_usuario_apr_fin') THEN
      ALTER TABLE public.periodos_remuneracion
        ADD CONSTRAINT fk_periodos_rem_usuario_apr_fin
        FOREIGN KEY (usuario_aprobador_finanzas_id) REFERENCES public.auth_usuarios(id) ON DELETE SET NULL;
    END IF;
  END IF;

  IF to_regclass('public.periodos_remuneracion') IS NOT NULL AND to_regclass('public.empleados') IS NOT NULL THEN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'fk_detalle_rem_periodo') THEN
      ALTER TABLE public.detalle_remuneraciones
        ADD CONSTRAINT fk_detalle_rem_periodo
        FOREIGN KEY (periodo_remuneracion_id) REFERENCES public.periodos_remuneracion(id) ON DELETE CASCADE;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'fk_detalle_rem_empleado') THEN
      ALTER TABLE public.detalle_remuneraciones
        ADD CONSTRAINT fk_detalle_rem_empleado
        FOREIGN KEY (empleado_id) REFERENCES public.empleados(id) ON DELETE RESTRICT;
    END IF;
  END IF;

  IF to_regclass('public.contratos_laborales') IS NOT NULL THEN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'fk_detalle_rem_contrato') THEN
      ALTER TABLE public.detalle_remuneraciones
        ADD CONSTRAINT fk_detalle_rem_contrato
        FOREIGN KEY (contrato_laboral_id) REFERENCES public.contratos_laborales(id) ON DELETE SET NULL;
    END IF;
  END IF;

  IF to_regclass('fin.centro_costo') IS NOT NULL THEN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'fk_detalle_rem_centro_costo') THEN
      ALTER TABLE public.detalle_remuneraciones
        ADD CONSTRAINT fk_detalle_rem_centro_costo
        FOREIGN KEY (centro_costo_id) REFERENCES fin.centro_costo(id) ON DELETE SET NULL;
    END IF;
  END IF;

  IF to_regclass('public.vehiculos_transporte') IS NOT NULL THEN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'fk_detalle_rem_camion') THEN
      ALTER TABLE public.detalle_remuneraciones
        ADD CONSTRAINT fk_detalle_rem_camion
        FOREIGN KEY (camion_id) REFERENCES public.vehiculos_transporte(id) ON DELETE SET NULL;
    END IF;
  END IF;

  IF to_regclass('public.detalle_remuneraciones') IS NOT NULL AND to_regclass('public.conceptos_remuneracion') IS NOT NULL THEN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'fk_items_rem_detalle') THEN
      ALTER TABLE public.items_remuneracion
        ADD CONSTRAINT fk_items_rem_detalle
        FOREIGN KEY (detalle_remuneracion_id) REFERENCES public.detalle_remuneraciones(id) ON DELETE CASCADE;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'fk_items_rem_concepto') THEN
      ALTER TABLE public.items_remuneracion
        ADD CONSTRAINT fk_items_rem_concepto
        FOREIGN KEY (concepto_remuneracion_id) REFERENCES public.conceptos_remuneracion(id) ON DELETE RESTRICT;
    END IF;
  END IF;

  IF to_regclass('public.auth_usuarios') IS NOT NULL THEN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'fk_items_rem_usuario_ajuste') THEN
      ALTER TABLE public.items_remuneracion
        ADD CONSTRAINT fk_items_rem_usuario_ajuste
        FOREIGN KEY (usuario_ajuste_id) REFERENCES public.auth_usuarios(id) ON DELETE SET NULL;
    END IF;
  END IF;
END $$;

-- --- Columnas en tablas ya existentes (migración incremental)
ALTER TABLE public.periodos_remuneracion ADD COLUMN IF NOT EXISTS asiento_pago_id BIGINT;

DO $$
BEGIN
  IF to_regclass('public.empleados') IS NOT NULL THEN
    ALTER TABLE public.empleados ADD COLUMN IF NOT EXISTS auth_usuario_id BIGINT;

    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'fk_empleados_auth_usuario') THEN
      IF to_regclass('public.auth_usuarios') IS NOT NULL THEN
        ALTER TABLE public.empleados
          ADD CONSTRAINT fk_empleados_auth_usuario
          FOREIGN KEY (auth_usuario_id) REFERENCES public.auth_usuarios(id) ON DELETE SET NULL;
      END IF;
    END IF;

    CREATE INDEX IF NOT EXISTS ix_empleados_auth_usuario_id ON public.empleados (auth_usuario_id);
    CREATE UNIQUE INDEX IF NOT EXISTS uq_empleados_auth_usuario_id
      ON public.empleados (auth_usuario_id)
      WHERE auth_usuario_id IS NOT NULL;
  END IF;
END $$;

COMMIT;
