-- Parche idempotente: IDs de asientos contables vinculados al anticipo.
ALTER TABLE fondos_rendir ADD COLUMN IF NOT EXISTS asiento_id_entrega BIGINT;
ALTER TABLE fondos_rendir ADD COLUMN IF NOT EXISTS asiento_id_liquidacion BIGINT;
