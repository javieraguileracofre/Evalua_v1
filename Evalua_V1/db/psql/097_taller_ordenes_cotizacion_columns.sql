-- Columnas cotización / administrativo en ordenes_servicio (tablas ya existentes en BD).
ALTER TABLE ordenes_servicio ADD COLUMN IF NOT EXISTS ingreso_grua BOOLEAN;
ALTER TABLE ordenes_servicio ADD COLUMN IF NOT EXISTS ote_num VARCHAR(60);
ALTER TABLE ordenes_servicio ADD COLUMN IF NOT EXISTS email_contacto VARCHAR(150);
ALTER TABLE ordenes_servicio ADD COLUMN IF NOT EXISTS cotizacion_afecta_iva BOOLEAN NOT NULL DEFAULT true;
