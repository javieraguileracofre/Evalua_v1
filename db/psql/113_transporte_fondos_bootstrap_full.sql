-- 113_transporte_fondos_bootstrap_full.sql
-- Bootstrap integral, idempotente y tolerante para Transporte + Fondos por rendir.
-- Objetivo: ejecutar en bases incompletas sin romper por FKs faltantes.

BEGIN;

-- =========================================================
-- 1) TABLAS BASE (SIN DEPENDENCIAS DURAS INICIALES)
-- =========================================================

CREATE TABLE IF NOT EXISTS public.vehiculos_transporte (
  id BIGINT PRIMARY KEY,
  patente VARCHAR(20) NOT NULL UNIQUE,
  marca VARCHAR(80) NOT NULL,
  modelo VARCHAR(120) NOT NULL,
  anio INTEGER,
  observaciones VARCHAR(500),
  consumo_referencial_l100km NUMERIC(8,2),
  activo BOOLEAN NOT NULL DEFAULT TRUE,
  created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMP WITHOUT TIME ZONE NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS public.fondos_rendir (
  id BIGINT PRIMARY KEY,
  folio VARCHAR(32) NOT NULL UNIQUE,
  empleado_id BIGINT NOT NULL,
  vehiculo_transporte_id BIGINT,
  monto_anticipo NUMERIC(18,2) NOT NULL,
  fecha_entrega TIMESTAMP WITHOUT TIME ZONE NOT NULL,
  estado VARCHAR(32) NOT NULL DEFAULT 'ABIERTO',
  fecha_envio_rendicion TIMESTAMP WITHOUT TIME ZONE,
  fecha_aprobacion TIMESTAMP WITHOUT TIME ZONE,
  motivo_rechazo TEXT,
  observaciones TEXT,
  asiento_id_entrega BIGINT,
  asiento_id_liquidacion BIGINT,
  created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMP WITHOUT TIME ZONE NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS public.fondos_rendir_gastos (
  id BIGINT PRIMARY KEY,
  fondo_id BIGINT NOT NULL,
  linea INTEGER NOT NULL,
  fecha_gasto TIMESTAMP WITHOUT TIME ZONE NOT NULL,
  rubro VARCHAR(80) NOT NULL,
  descripcion VARCHAR(500),
  monto NUMERIC(18,2) NOT NULL,
  nro_documento VARCHAR(64),
  created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS public.transporte_viajes (
  id BIGINT PRIMARY KEY,
  folio VARCHAR(32) NOT NULL UNIQUE,
  empleado_id BIGINT NOT NULL,
  vehiculo_transporte_id BIGINT,
  cliente_id BIGINT,
  fondo_rendir_id BIGINT,
  estado VARCHAR(24) NOT NULL DEFAULT 'BORRADOR',
  origen VARCHAR(240) NOT NULL DEFAULT '',
  destino VARCHAR(240) NOT NULL DEFAULT '',
  referencia_carga VARCHAR(200),
  programado_salida TIMESTAMP WITHOUT TIME ZONE,
  programado_llegada TIMESTAMP WITHOUT TIME ZONE,
  real_salida TIMESTAMP WITHOUT TIME ZONE,
  real_llegada TIMESTAMP WITHOUT TIME ZONE,
  odometro_inicio INTEGER,
  odometro_fin INTEGER,
  litros_combustible NUMERIC(12,2),
  notas TEXT,
  motivo_anulacion TEXT,
  created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMP WITHOUT TIME ZONE NOT NULL DEFAULT NOW()
);

-- =========================================================
-- 2) AMPLIACIONES DE CONTROL (VEHICULO + VIAJE)
-- =========================================================

ALTER TABLE public.vehiculos_transporte ADD COLUMN IF NOT EXISTS tipo_vehiculo VARCHAR(40);
ALTER TABLE public.vehiculos_transporte ADD COLUMN IF NOT EXISTS capacidad_carga NUMERIC(12,2);
ALTER TABLE public.vehiculos_transporte ADD COLUMN IF NOT EXISTS odometro_actual INTEGER;
ALTER TABLE public.vehiculos_transporte ADD COLUMN IF NOT EXISTS estado_operativo VARCHAR(24) NOT NULL DEFAULT 'DISPONIBLE';
ALTER TABLE public.vehiculos_transporte ADD COLUMN IF NOT EXISTS fecha_revision_tecnica DATE;
ALTER TABLE public.vehiculos_transporte ADD COLUMN IF NOT EXISTS fecha_permiso_circulacion DATE;
ALTER TABLE public.vehiculos_transporte ADD COLUMN IF NOT EXISTS fecha_seguro DATE;
ALTER TABLE public.vehiculos_transporte ADD COLUMN IF NOT EXISTS fecha_proxima_mantencion DATE;
ALTER TABLE public.vehiculos_transporte ADD COLUMN IF NOT EXISTS km_proxima_mantencion INTEGER;

ALTER TABLE public.transporte_viajes ADD COLUMN IF NOT EXISTS tipo_carga VARCHAR(80);
ALTER TABLE public.transporte_viajes ADD COLUMN IF NOT EXISTS peso_carga NUMERIC(12,2);
ALTER TABLE public.transporte_viajes ADD COLUMN IF NOT EXISTS valor_flete NUMERIC(18,2);
ALTER TABLE public.transporte_viajes ADD COLUMN IF NOT EXISTS costo_estimado NUMERIC(18,2);
ALTER TABLE public.transporte_viajes ADD COLUMN IF NOT EXISTS costo_real NUMERIC(18,2);
ALTER TABLE public.transporte_viajes ADD COLUMN IF NOT EXISTS km_vacio INTEGER;
ALTER TABLE public.transporte_viajes ADD COLUMN IF NOT EXISTS km_cargado INTEGER;
ALTER TABLE public.transporte_viajes ADD COLUMN IF NOT EXISTS motivo_desvio TEXT;
ALTER TABLE public.transporte_viajes ADD COLUMN IF NOT EXISTS observaciones_cierre TEXT;
ALTER TABLE public.transporte_viajes ADD COLUMN IF NOT EXISTS alerta_consumo BOOLEAN NOT NULL DEFAULT FALSE;
ALTER TABLE public.transporte_viajes ADD COLUMN IF NOT EXISTS usuario_creacion VARCHAR(120);
ALTER TABLE public.transporte_viajes ADD COLUMN IF NOT EXISTS usuario_modificacion VARCHAR(120);

-- =========================================================
-- 3) MANTENCIONES DE FLOTA
-- =========================================================

CREATE TABLE IF NOT EXISTS public.flota_mantenciones (
  id BIGINT PRIMARY KEY,
  vehiculo_transporte_id BIGINT NOT NULL,
  fecha DATE NOT NULL,
  odometro INTEGER,
  tipo VARCHAR(24) NOT NULL DEFAULT 'PREVENTIVA',
  proveedor VARCHAR(160),
  documento VARCHAR(100),
  costo NUMERIC(18,2),
  observaciones TEXT,
  proxima_fecha DATE,
  proximo_km INTEGER,
  created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL DEFAULT NOW()
);

-- =========================================================
-- 4) INDICES
-- =========================================================

CREATE INDEX IF NOT EXISTS ix_vehiculos_transporte_patente ON public.vehiculos_transporte(patente);
CREATE INDEX IF NOT EXISTS ix_vehiculos_transporte_activo ON public.vehiculos_transporte(activo);

CREATE INDEX IF NOT EXISTS ix_fondos_rendir_folio ON public.fondos_rendir(folio);
CREATE INDEX IF NOT EXISTS ix_fondos_rendir_empleado ON public.fondos_rendir(empleado_id);
CREATE INDEX IF NOT EXISTS ix_fondos_rendir_estado ON public.fondos_rendir(estado);
CREATE INDEX IF NOT EXISTS ix_fondos_rendir_fecha_entrega ON public.fondos_rendir(fecha_entrega);

CREATE UNIQUE INDEX IF NOT EXISTS uq_fondos_rendir_gastos_fondo_linea
  ON public.fondos_rendir_gastos(fondo_id, linea);
CREATE INDEX IF NOT EXISTS ix_fondos_rendir_gastos_fondo ON public.fondos_rendir_gastos(fondo_id);

CREATE INDEX IF NOT EXISTS ix_transporte_viajes_folio ON public.transporte_viajes(folio);
CREATE INDEX IF NOT EXISTS ix_transporte_viajes_empleado ON public.transporte_viajes(empleado_id);
CREATE INDEX IF NOT EXISTS ix_transporte_viajes_vehiculo ON public.transporte_viajes(vehiculo_transporte_id);
CREATE INDEX IF NOT EXISTS ix_transporte_viajes_estado ON public.transporte_viajes(estado);
CREATE INDEX IF NOT EXISTS ix_transporte_viajes_real_salida ON public.transporte_viajes(real_salida);
CREATE INDEX IF NOT EXISTS ix_transporte_viajes_fondo ON public.transporte_viajes(fondo_rendir_id);

CREATE INDEX IF NOT EXISTS ix_flota_mantenciones_vehiculo ON public.flota_mantenciones(vehiculo_transporte_id);
CREATE INDEX IF NOT EXISTS ix_flota_mantenciones_fecha ON public.flota_mantenciones(fecha);

-- =========================================================
-- 5) FKS CONDICIONALES (SOLO SI EXISTE TABLA PADRE)
-- =========================================================

DO $$
BEGIN
  -- fondos_rendir -> empleados
  IF to_regclass('public.empleados') IS NOT NULL THEN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'fk_fondos_empleado') THEN
      ALTER TABLE public.fondos_rendir
        ADD CONSTRAINT fk_fondos_empleado
        FOREIGN KEY (empleado_id) REFERENCES public.empleados(id) ON DELETE RESTRICT;
    END IF;
  ELSE
    RAISE NOTICE 'No existe public.empleados; se omite fk_fondos_empleado';
  END IF;

  -- fondos_rendir -> vehiculos_transporte
  IF to_regclass('public.vehiculos_transporte') IS NOT NULL THEN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'fk_fondos_vehiculo') THEN
      ALTER TABLE public.fondos_rendir
        ADD CONSTRAINT fk_fondos_vehiculo
        FOREIGN KEY (vehiculo_transporte_id) REFERENCES public.vehiculos_transporte(id) ON DELETE SET NULL;
    END IF;
  END IF;

  -- gastos -> fondos_rendir
  IF to_regclass('public.fondos_rendir') IS NOT NULL THEN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'fk_fondos_gastos_fondo') THEN
      ALTER TABLE public.fondos_rendir_gastos
        ADD CONSTRAINT fk_fondos_gastos_fondo
        FOREIGN KEY (fondo_id) REFERENCES public.fondos_rendir(id) ON DELETE CASCADE;
    END IF;
  END IF;

  -- viajes -> empleados
  IF to_regclass('public.empleados') IS NOT NULL THEN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'fk_viajes_empleado') THEN
      ALTER TABLE public.transporte_viajes
        ADD CONSTRAINT fk_viajes_empleado
        FOREIGN KEY (empleado_id) REFERENCES public.empleados(id) ON DELETE RESTRICT;
    END IF;
  ELSE
    RAISE NOTICE 'No existe public.empleados; se omite fk_viajes_empleado';
  END IF;

  -- viajes -> vehiculos_transporte
  IF to_regclass('public.vehiculos_transporte') IS NOT NULL THEN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'fk_viajes_vehiculo') THEN
      ALTER TABLE public.transporte_viajes
        ADD CONSTRAINT fk_viajes_vehiculo
        FOREIGN KEY (vehiculo_transporte_id) REFERENCES public.vehiculos_transporte(id) ON DELETE SET NULL;
    END IF;
  END IF;

  -- viajes -> fondos_rendir
  IF to_regclass('public.fondos_rendir') IS NOT NULL THEN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'fk_viajes_fondo') THEN
      ALTER TABLE public.transporte_viajes
        ADD CONSTRAINT fk_viajes_fondo
        FOREIGN KEY (fondo_rendir_id) REFERENCES public.fondos_rendir(id) ON DELETE SET NULL;
    END IF;
  END IF;

  -- viajes -> clientes (si existe módulo comercial/maestro)
  IF to_regclass('public.clientes') IS NOT NULL THEN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'fk_viajes_cliente') THEN
      ALTER TABLE public.transporte_viajes
        ADD CONSTRAINT fk_viajes_cliente
        FOREIGN KEY (cliente_id) REFERENCES public.clientes(id) ON DELETE SET NULL;
    END IF;
  ELSE
    RAISE NOTICE 'No existe public.clientes; se omite fk_viajes_cliente';
  END IF;

  -- mantenciones -> vehiculos_transporte
  IF to_regclass('public.vehiculos_transporte') IS NOT NULL THEN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'fk_flota_mantencion_vehiculo') THEN
      ALTER TABLE public.flota_mantenciones
        ADD CONSTRAINT fk_flota_mantencion_vehiculo
        FOREIGN KEY (vehiculo_transporte_id) REFERENCES public.vehiculos_transporte(id) ON DELETE CASCADE;
    END IF;
  ELSE
    RAISE NOTICE 'No existe public.vehiculos_transporte; se omite fk_flota_mantencion_vehiculo';
  END IF;
END $$;

COMMIT;

-- =========================================================
-- 6) CHECKS RAPIDOS
-- =========================================================
-- SELECT to_regclass('public.vehiculos_transporte');
-- SELECT to_regclass('public.fondos_rendir');
-- SELECT to_regclass('public.fondos_rendir_gastos');
-- SELECT to_regclass('public.transporte_viajes');
-- SELECT to_regclass('public.flota_mantenciones');
