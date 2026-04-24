-- db/psql/086_fin_foreign_keys.sql

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM pg_constraint
        WHERE conname = 'fk_fin_ap_documento_proveedor'
    ) THEN
        ALTER TABLE fin.ap_documento
        ADD CONSTRAINT fk_fin_ap_documento_proveedor
        FOREIGN KEY (proveedor_id)
        REFERENCES fin.proveedor(id)
        ON UPDATE CASCADE
        ON DELETE RESTRICT;
    END IF;
END $$;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'fk_fin_ap_documento_det_documento'
    ) THEN
        ALTER TABLE fin.ap_documento_detalle
        ADD CONSTRAINT fk_fin_ap_documento_det_documento
        FOREIGN KEY (documento_id)
        REFERENCES fin.ap_documento(id)
        ON UPDATE CASCADE
        ON DELETE CASCADE;
    END IF;
END $$;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'fk_fin_ap_documento_det_categoria'
    ) THEN
        ALTER TABLE fin.ap_documento_detalle
        ADD CONSTRAINT fk_fin_ap_documento_det_categoria
        FOREIGN KEY (categoria_gasto_id)
        REFERENCES fin.categoria_gasto(id)
        ON UPDATE CASCADE
        ON DELETE SET NULL;
    END IF;
END $$;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'fk_fin_ap_documento_det_centro'
    ) THEN
        ALTER TABLE fin.ap_documento_detalle
        ADD CONSTRAINT fk_fin_ap_documento_det_centro
        FOREIGN KEY (centro_costo_id)
        REFERENCES fin.centro_costo(id)
        ON UPDATE CASCADE
        ON DELETE SET NULL;
    END IF;
END $$;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'fk_fin_ap_documento_impuesto_documento'
    ) THEN
        ALTER TABLE fin.ap_documento_impuesto
        ADD CONSTRAINT fk_fin_ap_documento_impuesto_documento
        FOREIGN KEY (documento_id)
        REFERENCES fin.ap_documento(id)
        ON UPDATE CASCADE
        ON DELETE CASCADE;
    END IF;
END $$;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'fk_fin_ap_pago_proveedor'
    ) THEN
        ALTER TABLE fin.ap_pago
        ADD CONSTRAINT fk_fin_ap_pago_proveedor
        FOREIGN KEY (proveedor_id)
        REFERENCES fin.proveedor(id)
        ON UPDATE CASCADE
        ON DELETE RESTRICT;
    END IF;
END $$;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'fk_fin_ap_pago_banco_proveedor'
    ) THEN
        ALTER TABLE fin.ap_pago
        ADD CONSTRAINT fk_fin_ap_pago_banco_proveedor
        FOREIGN KEY (banco_proveedor_id)
        REFERENCES fin.proveedor_banco(id)
        ON UPDATE CASCADE
        ON DELETE SET NULL;
    END IF;
END $$;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'fk_fin_ap_pago_aplicacion_pago'
    ) THEN
        ALTER TABLE fin.ap_pago_aplicacion
        ADD CONSTRAINT fk_fin_ap_pago_aplicacion_pago
        FOREIGN KEY (pago_id)
        REFERENCES fin.ap_pago(id)
        ON UPDATE CASCADE
        ON DELETE CASCADE;
    END IF;
END $$;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'fk_fin_ap_pago_aplicacion_documento'
    ) THEN
        ALTER TABLE fin.ap_pago_aplicacion
        ADD CONSTRAINT fk_fin_ap_pago_aplicacion_documento
        FOREIGN KEY (documento_id)
        REFERENCES fin.ap_documento(id)
        ON UPDATE CASCADE
        ON DELETE RESTRICT;
    END IF;
END $$;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'fk_fin_proveedor_banco_proveedor'
    ) THEN
        ALTER TABLE fin.proveedor_banco
        ADD CONSTRAINT fk_fin_proveedor_banco_proveedor
        FOREIGN KEY (proveedor_id)
        REFERENCES fin.proveedor(id)
        ON UPDATE CASCADE
        ON DELETE CASCADE;
    END IF;
END $$;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'fk_fin_proveedor_contacto_proveedor'
    ) THEN
        ALTER TABLE fin.proveedor_contacto
        ADD CONSTRAINT fk_fin_proveedor_contacto_proveedor
        FOREIGN KEY (proveedor_id)
        REFERENCES fin.proveedor(id)
        ON UPDATE CASCADE
        ON DELETE CASCADE;
    END IF;
END $$;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'fk_fin_proveedor_direccion_proveedor'
    ) THEN
        ALTER TABLE fin.proveedor_direccion
        ADD CONSTRAINT fk_fin_proveedor_direccion_proveedor
        FOREIGN KEY (proveedor_id)
        REFERENCES fin.proveedor(id)
        ON UPDATE CASCADE
        ON DELETE CASCADE;
    END IF;
END $$;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'ck_fin_periodo_mes'
    ) THEN
        ALTER TABLE fin.periodo
        ADD CONSTRAINT ck_fin_periodo_mes
        CHECK (mes BETWEEN 1 AND 12);
    END IF;
END $$;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'ck_fin_ap_documento_totales'
    ) THEN
        ALTER TABLE fin.ap_documento
        ADD CONSTRAINT ck_fin_ap_documento_totales
        CHECK (
            neto >= 0
            AND exento >= 0
            AND iva >= 0
            AND otros_impuestos >= 0
            AND total >= 0
            AND saldo_pendiente >= 0
        );
    END IF;
END $$;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'ck_fin_ap_pago_monto_total'
    ) THEN
        ALTER TABLE fin.ap_pago
        ADD CONSTRAINT ck_fin_ap_pago_monto_total
        CHECK (monto_total >= 0);
    END IF;
END $$;