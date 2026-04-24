-- Tipos ENUM en fin.* requeridos por SQLAlchemy (create_type=False en modelos).
CREATE SCHEMA IF NOT EXISTS fin;

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_type t JOIN pg_namespace n ON n.oid = t.typnamespace
                   WHERE n.nspname = 'fin' AND t.typname = 'estado_simple') THEN
        CREATE TYPE fin.estado_simple AS ENUM ('ACTIVO', 'INACTIVO', 'BLOQUEADO');
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_type t JOIN pg_namespace n ON n.oid = t.typnamespace
                   WHERE n.nspname = 'fin' AND t.typname = 'categoria_gasto_tipo') THEN
        CREATE TYPE fin.categoria_gasto_tipo AS ENUM (
            'OPERACIONAL', 'ADMINISTRATIVO', 'VENTA', 'FINANCIERO', 'TRIBUTARIO', 'OTRO'
        );
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_type t JOIN pg_namespace n ON n.oid = t.typnamespace
                   WHERE n.nspname = 'fin' AND t.typname = 'periodo_estado') THEN
        CREATE TYPE fin.periodo_estado AS ENUM ('ABIERTO', 'CERRADO');
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_type t JOIN pg_namespace n ON n.oid = t.typnamespace
                   WHERE n.nspname = 'fin' AND t.typname = 'ap_doc_tipo') THEN
        CREATE TYPE fin.ap_doc_tipo AS ENUM ('FACTURA', 'BOLETA', 'NC', 'ND', 'OTRO');
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_type t JOIN pg_namespace n ON n.oid = t.typnamespace
                   WHERE n.nspname = 'fin' AND t.typname = 'ap_doc_estado') THEN
        CREATE TYPE fin.ap_doc_estado AS ENUM (
            'BORRADOR', 'INGRESADO', 'PAGADO', 'ANULADO', 'VENCIDO'
        );
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_type t JOIN pg_namespace n ON n.oid = t.typnamespace
                   WHERE n.nspname = 'fin' AND t.typname = 'moneda_iso') THEN
        CREATE TYPE fin.moneda_iso AS ENUM ('CLP', 'USD', 'EUR', 'UF');
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_type t JOIN pg_namespace n ON n.oid = t.typnamespace
                   WHERE n.nspname = 'fin' AND t.typname = 'impuesto_tipo') THEN
        CREATE TYPE fin.impuesto_tipo AS ENUM ('IVA', 'RETENCION', 'PERCEPCION', 'OTRO');
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_type t JOIN pg_namespace n ON n.oid = t.typnamespace
                   WHERE n.nspname = 'fin' AND t.typname = 'ap_pago_estado') THEN
        CREATE TYPE fin.ap_pago_estado AS ENUM ('BORRADOR', 'APLICADO', 'CONFIRMADO', 'ANULADO');
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_type t JOIN pg_namespace n ON n.oid = t.typnamespace
                   WHERE n.nspname = 'fin' AND t.typname = 'medio_pago') THEN
        CREATE TYPE fin.medio_pago AS ENUM (
            'TRANSFERENCIA', 'EFECTIVO', 'CHEQUE', 'TARJETA', 'DEPOSITO', 'OTRO'
        );
    END IF;
END $$;
