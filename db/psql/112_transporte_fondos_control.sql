-- Transporte + Fondos por rendir: ampliación gerencial (idempotente)
ALTER TABLE vehiculos_transporte ADD COLUMN IF NOT EXISTS tipo_vehiculo VARCHAR(40);
ALTER TABLE vehiculos_transporte ADD COLUMN IF NOT EXISTS capacidad_carga NUMERIC(12,2);
ALTER TABLE vehiculos_transporte ADD COLUMN IF NOT EXISTS odometro_actual INTEGER;
ALTER TABLE vehiculos_transporte ADD COLUMN IF NOT EXISTS estado_operativo VARCHAR(24) NOT NULL DEFAULT 'DISPONIBLE';
ALTER TABLE vehiculos_transporte ADD COLUMN IF NOT EXISTS fecha_revision_tecnica DATE;
ALTER TABLE vehiculos_transporte ADD COLUMN IF NOT EXISTS fecha_permiso_circulacion DATE;
ALTER TABLE vehiculos_transporte ADD COLUMN IF NOT EXISTS fecha_seguro DATE;
ALTER TABLE vehiculos_transporte ADD COLUMN IF NOT EXISTS fecha_proxima_mantencion DATE;
ALTER TABLE vehiculos_transporte ADD COLUMN IF NOT EXISTS km_proxima_mantencion INTEGER;

ALTER TABLE transporte_viajes ADD COLUMN IF NOT EXISTS tipo_carga VARCHAR(80);
ALTER TABLE transporte_viajes ADD COLUMN IF NOT EXISTS peso_carga NUMERIC(12,2);
ALTER TABLE transporte_viajes ADD COLUMN IF NOT EXISTS valor_flete NUMERIC(18,2);
ALTER TABLE transporte_viajes ADD COLUMN IF NOT EXISTS costo_estimado NUMERIC(18,2);
ALTER TABLE transporte_viajes ADD COLUMN IF NOT EXISTS costo_real NUMERIC(18,2);
ALTER TABLE transporte_viajes ADD COLUMN IF NOT EXISTS km_vacio INTEGER;
ALTER TABLE transporte_viajes ADD COLUMN IF NOT EXISTS km_cargado INTEGER;
ALTER TABLE transporte_viajes ADD COLUMN IF NOT EXISTS motivo_desvio TEXT;
ALTER TABLE transporte_viajes ADD COLUMN IF NOT EXISTS observaciones_cierre TEXT;
ALTER TABLE transporte_viajes ADD COLUMN IF NOT EXISTS alerta_consumo BOOLEAN NOT NULL DEFAULT FALSE;
ALTER TABLE transporte_viajes ADD COLUMN IF NOT EXISTS usuario_creacion VARCHAR(120);
ALTER TABLE transporte_viajes ADD COLUMN IF NOT EXISTS usuario_modificacion VARCHAR(120);

DO $$
BEGIN
  IF to_regclass('public.vehiculos_transporte') IS NOT NULL THEN
    EXECUTE $ddl$
      CREATE TABLE IF NOT EXISTS flota_mantenciones (
        id BIGINT PRIMARY KEY,
        vehiculo_transporte_id BIGINT NOT NULL REFERENCES public.vehiculos_transporte(id) ON DELETE CASCADE,
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
      )
    $ddl$;
    EXECUTE 'CREATE INDEX IF NOT EXISTS ix_flota_mantenciones_vehiculo ON flota_mantenciones (vehiculo_transporte_id)';
    EXECUTE 'CREATE INDEX IF NOT EXISTS ix_flota_mantenciones_fecha ON flota_mantenciones (fecha)';
  ELSE
    RAISE NOTICE 'Se omite flota_mantenciones: no existe public.vehiculos_transporte';
  END IF;
END $$;
