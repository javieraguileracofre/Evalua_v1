# db/startup_schema.py
# -*- coding: utf-8 -*-
"""Parches de esquema idempotentes al arrancar (BD ya existente sin migración SQL manual)."""
from __future__ import annotations

import logging
from pathlib import Path

from sqlalchemy import func, select, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import sessionmaker

logger = logging.getLogger("evalua.db.startup_schema")

_ROLES_SEED: tuple[tuple[str, str, str], ...] = (
    ("ADMIN", "Administrador", "Acceso completo a la suite ERP."),
    ("OPERACIONES", "Operaciones", "Ventas, taller, inventario y maestros operativos."),
    ("FINANZAS", "Finanzas", "Cobranza, cuentas por pagar y contabilidad."),
    ("RRHH", "Recursos humanos", "Nómina, contratos laborales y remuneraciones."),
    ("CONSULTA", "Consulta", "Rol base para políticas de solo lectura (evolución futura)."),
)

_ROOT = Path(__file__).resolve().parent.parent
_PATCH_093 = _ROOT / "db" / "psql" / "093_fin_ap_documento_contabilidad.sql"
_PATCH_097 = _ROOT / "db" / "psql" / "097_taller_ordenes_cotizacion_columns.sql"
_PATCH_099 = _ROOT / "db" / "psql" / "099_fondos_rendir_asientos.sql"
_PATCH_090 = _ROOT / "db" / "psql" / "090_fin_config_contable.sql"
_PATCH_091 = _ROOT / "db" / "psql" / "091_fin_inventario_recepcion_premium.sql"
_PATCH_092 = _ROOT / "db" / "psql" / "092_fin_ventas_costo_venta_premium.sql"
_PATCH_100 = _ROOT / "db" / "psql" / "100_comercial_leasing_financiero.sql"
_PATCH_101 = _ROOT / "db" / "psql" / "101_credito_riesgo.sql"
_PATCH_102 = _ROOT / "db" / "psql" / "102_leasing_operativo.sql"
_PATCH_103 = _ROOT / "db" / "psql" / "103_leasing_operativo_contrato_cuota.sql"
_PATCH_104 = _ROOT / "db" / "psql" / "104_leasing_operativo_activo_fijo.sql"
_PATCH_105 = _ROOT / "db" / "psql" / "105_leasing_operativo_parametros_tipo.sql"
_PATCH_106 = _ROOT / "db" / "psql" / "106_leasing_operativo_documentos.sql"
_PATCH_107 = _ROOT / "db" / "psql" / "107_leasing_operativo_contabilidad_base.sql"
_PATCH_109 = _ROOT / "db" / "psql" / "109_leasing_financiero_workflow.sql"
_PATCH_110 = _ROOT / "db" / "psql" / "110_credito_riesgo_flujos.sql"
_PATCH_111 = _ROOT / "db" / "psql" / "111_postventa_crm_cases.sql"
_PATCH_112 = _ROOT / "db" / "psql" / "112_transporte_fondos_control.sql"
_PATCH_115 = _ROOT / "db" / "psql" / "115_empleados_bootstrap.sql"
_PATCH_117 = _ROOT / "db" / "psql" / "117_remuneraciones_bootstrap.sql"
_PATCH_118 = _ROOT / "db" / "psql" / "118_remuneraciones_parametros_periodo.sql"
_PATCH_119 = _ROOT / "db" / "psql" / "119_remuneraciones_horas_periodo.sql"
_PATCH_120 = _ROOT / "db" / "psql" / "120_remuneraciones_auditoria.sql"
_PATCH_121 = _ROOT / "db" / "psql" / "121_remuneraciones_asiento_provision.sql"
_PATCH_122 = _ROOT / "db" / "psql" / "122_empleados_transferencia_bancaria.sql"
_PATCH_123 = _ROOT / "db" / "psql" / "123_fin_plan_cuenta_leasing_fin_min.sql"


def ensure_leasing_financiero_plan_cuentas_min(engine: Engine) -> None:
    """Upsert cuentas 113701, 210701, 210702, 410701, 110201 (+ agrupadores) para leasing financiero."""
    if engine.dialect.name != "postgresql":
        return
    if not _has_table(engine, schema="fin", table="plan_cuenta"):
        return
    if not _PATCH_123.is_file():
        return
    try:
        _run_sql_patch_autocommit(engine, _PATCH_123)
        logger.info("Plan de cuentas leasing financiero mínimo verificado (123).")
    except Exception as exc:
        logger.warning(
            "No se pudo aplicar 123_fin_plan_cuenta_leasing_fin_min.sql. Detalle: %s",
            exc,
        )


def ensure_vehiculo_transporte_consumo_column(engine: Engine) -> None:
    """Añade consumo_referencial_l100km en vehiculos_transporte si falta (PostgreSQL)."""
    if engine.dialect.name != "postgresql":
        return
    with engine.connect() as conn:
        has_table = conn.execute(
            text(
                """
                SELECT 1
                FROM information_schema.tables
                WHERE table_schema = 'public' AND table_name = 'vehiculos_transporte'
                LIMIT 1
                """
            )
        ).scalar()
        if not has_table:
            return
        has_col = conn.execute(
            text(
                """
                SELECT 1
                FROM information_schema.columns
                WHERE table_schema = 'public'
                  AND table_name = 'vehiculos_transporte'
                  AND column_name = 'consumo_referencial_l100km'
                LIMIT 1
                """
            )
        ).scalar()
        if has_col:
            return
    try:
        with engine.connect() as conn:
            conn = conn.execution_options(isolation_level="AUTOCOMMIT")
            conn.exec_driver_sql(
                "ALTER TABLE vehiculos_transporte "
                "ADD COLUMN IF NOT EXISTS consumo_referencial_l100km NUMERIC(8,2)"
            )
        logger.info("Columna consumo_referencial_l100km añadida en vehiculos_transporte.")
    except Exception as exc:
        logger.warning(
            "No se pudo añadir consumo_referencial_l100km en vehiculos_transporte: %s",
            exc,
        )


def ensure_ap_documento_contabilidad_columns(engine: Engine) -> None:
    """
    fin.ap_documento creada antes por SQLAlchemy sin las columnas de CxP contable:
    aplica 093 si faltan. Requiere permiso ALTER en la tabla (mismo rol que la app).
    """
    with engine.connect() as conn:
        has_table = conn.execute(
            text(
                """
                SELECT 1
                FROM information_schema.tables
                WHERE table_schema = 'fin' AND table_name = 'ap_documento'
                LIMIT 1
                """
            )
        ).scalar()
        if not has_table:
            return

        has_col = conn.execute(
            text(
                """
                SELECT 1
                FROM information_schema.columns
                WHERE table_schema = 'fin'
                  AND table_name = 'ap_documento'
                  AND column_name = 'tipo_compra_contable'
                LIMIT 1
                """
            )
        ).scalar()
        if has_col:
            return

    if not _PATCH_093.is_file():
        logger.warning("No se encontró %s; omitiendo parche AP contabilidad.", _PATCH_093)
        return

    sql = _PATCH_093.read_text(encoding="utf-8")
    try:
        with engine.connect() as conn:
            conn = conn.execution_options(isolation_level="AUTOCOMMIT")
            conn.exec_driver_sql(sql)
        logger.info(
            "Parche aplicado: columnas contables en fin.ap_documento (093_fin_ap_documento_contabilidad)."
        )
    except Exception as exc:
        logger.warning(
            "No se pudo aplicar el parche fin.ap_documento (093). "
            "Ejecute como dueño de la tabla: python tools/apply_fin_sql_file.py. Detalle: %s",
            exc,
        )


def ensure_taller_ordenes_cotizacion_columns(engine: Engine) -> None:
    """Añade columnas de cotización en ordenes_servicio si la tabla ya existía sin ellas."""
    if engine.dialect.name != "postgresql":
        return
    if not _PATCH_097.is_file():
        return
    with engine.connect() as conn:
        has_table = conn.execute(
            text(
                """
                SELECT 1
                FROM information_schema.tables
                WHERE table_schema = 'public' AND table_name = 'ordenes_servicio'
                LIMIT 1
                """
            )
        ).scalar()
        if not has_table:
            return
        has_col = conn.execute(
            text(
                """
                SELECT 1
                FROM information_schema.columns
                WHERE table_schema = 'public'
                  AND table_name = 'ordenes_servicio'
                  AND column_name = 'cotizacion_afecta_iva'
                LIMIT 1
                """
            )
        ).scalar()
        if has_col:
            return

    sql = _PATCH_097.read_text(encoding="utf-8")
    try:
        with engine.connect() as conn:
            conn = conn.execution_options(isolation_level="AUTOCOMMIT")
            conn.exec_driver_sql(sql)
        logger.info("Parche aplicado: columnas cotización en ordenes_servicio (097).")
    except Exception as exc:
        logger.warning(
            "No se pudo aplicar el parche taller 097 (ordenes_servicio). Detalle: %s",
            exc,
        )


def ensure_fondos_rendir_asiento_columns(engine: Engine) -> None:
    """Añade columnas de asiento contable en fondos_rendir si la tabla ya existía sin ellas."""
    if engine.dialect.name != "postgresql":
        return
    if not _PATCH_099.is_file():
        return
    with engine.connect() as conn:
        has_table = conn.execute(
            text(
                """
                SELECT 1
                FROM information_schema.tables
                WHERE table_schema = 'public' AND table_name = 'fondos_rendir'
                LIMIT 1
                """
            )
        ).scalar()
        if not has_table:
            return
        has_col = conn.execute(
            text(
                """
                SELECT 1
                FROM information_schema.columns
                WHERE table_schema = 'public'
                  AND table_name = 'fondos_rendir'
                  AND column_name = 'asiento_id_entrega'
                LIMIT 1
                """
            )
        ).scalar()
        if has_col:
            return

    sql = _PATCH_099.read_text(encoding="utf-8")
    try:
        with engine.connect() as conn:
            conn = conn.execution_options(isolation_level="AUTOCOMMIT")
            conn.exec_driver_sql(sql)
        logger.info("Parche aplicado: columnas asiento en fondos_rendir (099).")
    except Exception as exc:
        logger.warning(
            "No se pudo aplicar el parche fondos_rendir 099. Detalle: %s",
            exc,
        )


def ensure_auth_roles_seed(engine: Engine) -> None:
    """Inserta roles por defecto si la tabla existe y está vacía o faltan códigos."""
    try:
        from models.auth.usuario import Rol, Usuario
    except Exception as exc:
        logger.debug("Modelos auth no disponibles: %s", exc)
        return

    SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
    with SessionLocal() as db:
        try:
            has_table = db.execute(
                text(
                    """
                    SELECT 1 FROM information_schema.tables
                    WHERE table_schema = 'public' AND table_name = 'auth_roles'
                    LIMIT 1
                    """
                )
            ).scalar()
            if not has_table:
                return
            for codigo, nombre, descripcion in _ROLES_SEED:
                exists = db.scalars(select(Rol.id).where(Rol.codigo == codigo)).first()
                if exists is None:
                    db.add(Rol(codigo=codigo, nombre=nombre, descripcion=descripcion))
            db.commit()
        except Exception as exc:
            db.rollback()
            logger.warning("No se pudo sembrar auth_roles: %s", exc)
            return

    with SessionLocal() as db:
        try:
            n_users = db.scalar(select(func.count()).select_from(Usuario)) or 0
            if int(n_users) == 0:
                logger.warning(
                    "No hay usuarios en auth_usuarios. Cree el primero con: "
                    "python tools/create_admin_user.py --email admin@empresa.cl --password '...' "
                    "--nombre 'Administrador'"
                )
        except Exception:
            pass


def _has_table(engine: Engine, *, schema: str, table: str) -> bool:
    with engine.connect() as conn:
        return bool(
            conn.execute(
                text(
                    """
                    SELECT 1
                    FROM information_schema.tables
                    WHERE table_schema = :schema
                      AND table_name = :table
                    LIMIT 1
                    """
                ),
                {"schema": schema, "table": table},
            ).scalar()
        )


def _run_sql_patch_autocommit(engine: Engine, path: Path) -> None:
    sql = path.read_text(encoding="utf-8")
    with engine.connect() as conn:
        conn = conn.execution_options(isolation_level="AUTOCOMMIT")
        conn.exec_driver_sql(sql)


def _ensure_plan_cuenta_minima_for_contabilidad_seed(engine: Engine) -> None:
    """
    Crea/actualiza cuentas mínimas requeridas por 090/091/092 para evitar fallos FK
    al sembrar configuración contable en bases nuevas.
    """
    if not _has_table(engine, schema="fin", table="plan_cuenta"):
        return

    sql = """
    INSERT INTO fin.plan_cuenta (
        codigo, nombre, nivel, cuenta_padre_id, tipo, clasificacion, naturaleza,
        acepta_movimiento, requiere_centro_costo, estado, descripcion
    ) VALUES
    ('100000', 'ACTIVO', 1, NULL, 'ACTIVO', 'ACTIVO', 'DEUDORA', FALSE, FALSE, 'ACTIVO', 'Grupo activo'),
    ('200000', 'PASIVO', 1, NULL, 'PASIVO', 'PASIVO', 'ACREEDORA', FALSE, FALSE, 'ACTIVO', 'Grupo pasivo'),
    ('400000', 'INGRESOS', 1, NULL, 'INGRESO', 'INGRESOS', 'ACREEDORA', FALSE, FALSE, 'ACTIVO', 'Grupo ingresos'),
    ('500000', 'COSTOS', 1, NULL, 'COSTO', 'COSTOS', 'DEUDORA', FALSE, FALSE, 'ACTIVO', 'Grupo costos'),
    ('110000', 'ACTIVO CORRIENTE', 2, NULL, 'ACTIVO', 'ACTIVO_CORRIENTE', 'DEUDORA', FALSE, FALSE, 'ACTIVO', 'Agrupador activos corrientes'),
    ('120000', 'ACTIVO NO CORRIENTE', 2, NULL, 'ACTIVO', 'ACTIVO_NO_CORRIENTE', 'DEUDORA', FALSE, FALSE, 'ACTIVO', 'Agrupador activos no corrientes'),
    ('110201', 'CAJA Y BANCOS', 3, NULL, 'ACTIVO', 'ACTIVO_CORRIENTE', 'DEUDORA', TRUE, FALSE, 'ACTIVO', 'Fondos disponibles'),
    ('110301', 'CLIENTES', 3, NULL, 'ACTIVO', 'ACTIVO_CORRIENTE', 'DEUDORA', TRUE, FALSE, 'ACTIVO', 'Cuentas por cobrar clientes'),
    ('110401', 'INVENTARIO MERCADERIA', 3, NULL, 'ACTIVO', 'ACTIVO_CORRIENTE', 'DEUDORA', TRUE, FALSE, 'ACTIVO', 'Inventario valorizado'),
    ('110501', 'IVA CREDITO FISCAL', 3, NULL, 'ACTIVO', 'ACTIVO_CORRIENTE', 'DEUDORA', TRUE, FALSE, 'ACTIVO', 'IVA crédito'),
    ('210000', 'PASIVOS CORRIENTES', 2, NULL, 'PASIVO', 'PASIVO_CORRIENTE', 'ACREEDORA', FALSE, FALSE, 'ACTIVO', 'Agrupador pasivos corrientes'),
    ('210101', 'PROVEEDORES', 3, NULL, 'PASIVO', 'PASIVO_CORRIENTE', 'ACREEDORA', TRUE, FALSE, 'ACTIVO', 'Proveedores por pagar'),
    ('210110', 'PROVEEDORES POR FACTURAR', 3, NULL, 'PASIVO', 'PASIVO_CORRIENTE', 'ACREEDORA', TRUE, FALSE, 'ACTIVO', 'Recepción sin factura'),
    ('210201', 'IVA DEBITO FISCAL', 3, NULL, 'PASIVO', 'PASIVO_CORRIENTE', 'ACREEDORA', TRUE, FALSE, 'ACTIVO', 'IVA débito'),
    ('410000', 'INGRESOS OPERACIONALES', 2, NULL, 'INGRESO', 'INGRESO_OPERACIONAL', 'ACREEDORA', FALSE, FALSE, 'ACTIVO', 'Agrupador ingresos operacionales'),
    ('410101', 'VENTAS', 3, NULL, 'INGRESO', 'INGRESO_OPERACIONAL', 'ACREEDORA', TRUE, TRUE, 'ACTIVO', 'Ingresos por ventas'),
    ('510000', 'COSTOS DE VENTAS', 2, NULL, 'COSTO', 'COSTO_VENTA', 'DEUDORA', FALSE, TRUE, 'ACTIVO', 'Agrupador costos'),
    ('510101', 'COSTO DE VENTAS', 3, NULL, 'COSTO', 'COSTO_VENTA', 'DEUDORA', TRUE, TRUE, 'ACTIVO', 'Costo mercadería vendida'),
    ('610102', 'COMBUSTIBLES', 3, NULL, 'GASTO', 'GASTO_ADMINISTRACION', 'DEUDORA', TRUE, TRUE, 'ACTIVO', 'Gasto de combustibles'),
    ('610103', 'PEAJES Y ESTACIONAMIENTOS', 3, NULL, 'GASTO', 'GASTO_ADMINISTRACION', 'DEUDORA', TRUE, TRUE, 'ACTIVO', 'Gasto de peajes y estacionamientos'),
    ('610104', 'GASTOS GENERALES', 3, NULL, 'GASTO', 'GASTO_ADMINISTRACION', 'DEUDORA', TRUE, TRUE, 'ACTIVO', 'Gastos de administración'),
    ('610105', 'VIATICOS Y GASTOS DE VIAJE', 3, NULL, 'GASTO', 'GASTO_ADMINISTRACION', 'DEUDORA', TRUE, TRUE, 'ACTIVO', 'Viaticos y gastos de viaje'),
    ('620101', 'MANTENCION Y REPARACIONES', 3, NULL, 'GASTO', 'GASTO_VENTA', 'DEUDORA', TRUE, TRUE, 'ACTIVO', 'Mantencion y reparaciones'),
    ('113701', 'CUENTAS POR COBRAR LEASING FINANCIERO', 3, NULL, 'ACTIVO', 'ACTIVO_CORRIENTE', 'DEUDORA', TRUE, FALSE, 'ACTIVO', 'Principal leasing financiero'),
    ('210701', 'OBLIGACIONES LEASING FINANCIERO', 3, NULL, 'PASIVO', 'PASIVO_CORRIENTE', 'ACREEDORA', TRUE, FALSE, 'ACTIVO', 'Pasivo leasing financiero'),
    ('210702', 'INTERESES DIFERIDOS LEASING FINANCIERO', 3, NULL, 'PASIVO', 'PASIVO_CORRIENTE', 'ACREEDORA', TRUE, FALSE, 'ACTIVO', 'Intereses financieros por devengar de leasing financiero'),
    ('410701', 'INGRESOS FINANCIEROS LEASING', 3, NULL, 'INGRESO', 'INGRESO_OPERACIONAL', 'ACREEDORA', TRUE, FALSE, 'ACTIVO', 'Intereses leasing financiero')
    ON CONFLICT (codigo) DO UPDATE SET
        nombre = EXCLUDED.nombre,
        nivel = EXCLUDED.nivel,
        tipo = EXCLUDED.tipo,
        clasificacion = EXCLUDED.clasificacion,
        naturaleza = EXCLUDED.naturaleza,
        acepta_movimiento = EXCLUDED.acepta_movimiento,
        requiere_centro_costo = EXCLUDED.requiere_centro_costo,
        estado = EXCLUDED.estado,
        descripcion = EXCLUDED.descripcion;

    UPDATE fin.plan_cuenta h
       SET cuenta_padre_id = p.id
      FROM fin.plan_cuenta p
     WHERE h.codigo = '110201'
       AND p.codigo = '110000';

    UPDATE fin.plan_cuenta h
       SET cuenta_padre_id = p.id
      FROM fin.plan_cuenta p
     WHERE h.codigo = '110301'
       AND p.codigo = '110000';

    UPDATE fin.plan_cuenta h
       SET cuenta_padre_id = p.id
      FROM fin.plan_cuenta p
     WHERE h.codigo = '110401'
       AND p.codigo = '110000';

    UPDATE fin.plan_cuenta h
       SET cuenta_padre_id = p.id
      FROM fin.plan_cuenta p
     WHERE h.codigo = '110501'
       AND p.codigo = '110000';

    UPDATE fin.plan_cuenta h
       SET cuenta_padre_id = p.id
      FROM fin.plan_cuenta p
     WHERE h.codigo = '210110'
       AND p.codigo = '210000';

    UPDATE fin.plan_cuenta h
       SET cuenta_padre_id = p.id
      FROM fin.plan_cuenta p
     WHERE h.codigo = '210101'
       AND p.codigo = '210000';

    UPDATE fin.plan_cuenta h
       SET cuenta_padre_id = p.id
      FROM fin.plan_cuenta p
     WHERE h.codigo = '210201'
       AND p.codigo = '210000';

    UPDATE fin.plan_cuenta h
       SET cuenta_padre_id = p.id
      FROM fin.plan_cuenta p
     WHERE h.codigo = '510101'
       AND p.codigo = '510000';

    UPDATE fin.plan_cuenta h
       SET cuenta_padre_id = p.id
      FROM fin.plan_cuenta p
     WHERE h.codigo = '610102'
       AND p.codigo = '610000';

    UPDATE fin.plan_cuenta h
       SET cuenta_padre_id = p.id
      FROM fin.plan_cuenta p
     WHERE h.codigo = '610103'
       AND p.codigo = '610000';

    UPDATE fin.plan_cuenta h
       SET cuenta_padre_id = p.id
      FROM fin.plan_cuenta p
     WHERE h.codigo = '610104'
       AND p.codigo = '610000';

    UPDATE fin.plan_cuenta h
       SET cuenta_padre_id = p.id
      FROM fin.plan_cuenta p
     WHERE h.codigo = '610105'
       AND p.codigo = '610000';

    UPDATE fin.plan_cuenta h
       SET cuenta_padre_id = p.id
      FROM fin.plan_cuenta p
     WHERE h.codigo = '620101'
       AND p.codigo = '620000';

    UPDATE fin.plan_cuenta h
       SET cuenta_padre_id = p.id
      FROM fin.plan_cuenta p
     WHERE h.codigo = '410101'
       AND p.codigo = '410000';

    UPDATE fin.plan_cuenta h
       SET cuenta_padre_id = p.id
      FROM fin.plan_cuenta p
     WHERE h.codigo = '113701'
       AND p.codigo = '110000';

    UPDATE fin.plan_cuenta h
       SET cuenta_padre_id = p.id
      FROM fin.plan_cuenta p
     WHERE h.codigo = '210701'
       AND p.codigo = '210000';

    UPDATE fin.plan_cuenta h
       SET cuenta_padre_id = p.id
      FROM fin.plan_cuenta p
     WHERE h.codigo = '210702'
       AND p.codigo = '210000';

    UPDATE fin.plan_cuenta h
       SET cuenta_padre_id = p.id
      FROM fin.plan_cuenta p
     WHERE h.codigo = '410701'
       AND p.codigo = '410000';
    """
    with engine.connect() as conn:
        conn = conn.execution_options(isolation_level="AUTOCOMMIT")
        conn.exec_driver_sql(sql)


def ensure_comercial_leasing_financiero_schema(engine: Engine) -> None:
    """
    Tablas comercial_lf_* + cuentas/config leasing (100) si aún no están aplicadas.
    Idempotente con el contenido de 100_comercial_leasing_financiero.sql.
    """
    if engine.dialect.name != "postgresql" or not _PATCH_100.is_file():
        return
    if not _has_table(engine, schema="fin", table="plan_cuenta"):
        return
    ensure_leasing_financiero_plan_cuentas_min(engine)
    with engine.connect() as conn:
        has_cot = conn.execute(
            text(
                """
                SELECT 1 FROM information_schema.tables
                WHERE table_schema = 'public' AND table_name = 'comercial_lf_cotizaciones'
                LIMIT 1
                """
            )
        ).scalar()
        has_credit = conn.execute(
            text(
                """
                SELECT 1 FROM information_schema.tables
                WHERE table_schema = 'public' AND table_name = 'comercial_lf_analisis_credito'
                LIMIT 1
                """
            )
        ).scalar()
        leasing_cfg = None
        if _has_table(engine, schema="fin", table="config_contable_detalle_modulo"):
            leasing_cfg = conn.execute(
                text(
                    """
                    SELECT 1 FROM fin.config_contable_detalle_modulo
                    WHERE modulo = 'COMERCIAL' AND submodulo = 'LEASING_FIN'
                    LIMIT 1
                    """
                )
            ).scalar()
        parent_ok = conn.execute(
            text(
                """
                SELECT CASE
                    WHEN EXISTS (
                        SELECT 1
                        FROM fin.plan_cuenta h
                        JOIN fin.plan_cuenta p ON p.id = h.cuenta_padre_id
                        WHERE h.codigo = '113701' AND p.codigo = '110000'
                    )
                    AND EXISTS (
                        SELECT 1
                        FROM fin.plan_cuenta h
                        JOIN fin.plan_cuenta p ON p.id = h.cuenta_padre_id
                        WHERE h.codigo = '210701' AND p.codigo = '210000'
                    )
                    AND EXISTS (
                        SELECT 1
                        FROM fin.plan_cuenta h
                        JOIN fin.plan_cuenta p ON p.id = h.cuenta_padre_id
                        WHERE h.codigo = '210702' AND p.codigo = '210000'
                    )
                    AND EXISTS (
                        SELECT 1
                        FROM fin.plan_cuenta h
                        JOIN fin.plan_cuenta p ON p.id = h.cuenta_padre_id
                        WHERE h.codigo = '410701' AND p.codigo = '410000'
                    )
                    THEN 1 ELSE 0
                END
                """
            )
        ).scalar()
    if not (has_cot and has_credit and leasing_cfg and bool(parent_ok)):
        try:
            _run_sql_patch_autocommit(engine, _PATCH_100)
            logger.info("Parche aplicado: comercial leasing financiero (100).")
        except Exception as exc:
            logger.warning(
                "No se pudo aplicar 100_comercial_leasing_financiero.sql. "
                "Ejecute manualmente en la base si es necesario. Detalle: %s",
                exc,
            )
    if _PATCH_109.is_file() and _has_table(engine, schema="public", table="comercial_lf_cotizaciones"):
        try:
            _run_sql_patch_autocommit(engine, _PATCH_109)
            logger.info("Parche aplicado: workflow post-cotización leasing financiero (109).")
        except Exception as exc:
            logger.warning(
                "No se pudo aplicar 109_leasing_financiero_workflow.sql. Detalle: %s",
                exc,
            )


def ensure_credito_riesgo_schema(engine: Engine) -> None:
    """
    Tablas credito_* (101) si aún no están aplicadas.
    Requiere public.clientes. Idempotente con 101_credito_riesgo.sql.
    """
    if engine.dialect.name != "postgresql" or not _PATCH_101.is_file():
        return
    if not _has_table(engine, schema="public", table="clientes"):
        return
    with engine.connect() as conn:
        has = conn.execute(
            text(
                """
                SELECT 1 FROM information_schema.tables
                WHERE table_schema = 'public' AND table_name = 'credito_solicitud'
                LIMIT 1
                """
            )
        ).scalar()
    if has:
        if _PATCH_110.is_file():
            try:
                _run_sql_patch_autocommit(engine, _PATCH_110)
                logger.info("Parche aplicado: mejoras de flujos crédito y riesgo (110).")
            except Exception as exc:
                logger.warning(
                    "No se pudo aplicar 110_credito_riesgo_flujos.sql. Detalle: %s",
                    exc,
                )
        return
    try:
        _run_sql_patch_autocommit(engine, _PATCH_101)
        logger.info("Parche aplicado: crédito y riesgo (101).")
        if _PATCH_110.is_file():
            _run_sql_patch_autocommit(engine, _PATCH_110)
            logger.info("Parche aplicado: mejoras de flujos crédito y riesgo (110).")
    except Exception as exc:
        logger.warning(
            "No se pudo aplicar 101/110 crédito y riesgo. Ejecute manualmente en la base si es necesario. Detalle: %s",
            exc,
        )


def ensure_leasing_operativo_schema(engine: Engine) -> None:
    """
    Tablas leasing_op_* (102) y contrato/cuota (103) si aún no están aplicadas.
    Requiere public.clientes. Idempotente.
    """
    if engine.dialect.name != "postgresql":
        return
    if not _has_table(engine, schema="public", table="clientes"):
        return
    if _PATCH_102.is_file() and not _has_table(engine, schema="public", table="leasing_op_simulacion"):
        try:
            _run_sql_patch_autocommit(engine, _PATCH_102)
            logger.info("Parche aplicado: leasing operativo (102).")
        except Exception as exc:
            logger.warning(
                "No se pudo aplicar 102_leasing_operativo.sql. Ejecute manualmente en la base si es necesario. Detalle: %s",
                exc,
            )
    if _PATCH_103.is_file() and not _has_table(engine, schema="public", table="leasing_op_contrato"):
        try:
            _run_sql_patch_autocommit(engine, _PATCH_103)
            logger.info("Parche aplicado: leasing operativo contrato/cuota (103).")
        except Exception as exc:
            logger.warning(
                "No se pudo aplicar 103_leasing_operativo_contrato_cuota.sql. Detalle: %s",
                exc,
            )
    if _PATCH_104.is_file() and not _has_table(engine, schema="public", table="leasing_op_activo_fijo"):
        try:
            _run_sql_patch_autocommit(engine, _PATCH_104)
            logger.info("Parche aplicado: leasing operativo activo fijo (104).")
        except Exception as exc:
            logger.warning(
                "No se pudo aplicar 104_leasing_operativo_activo_fijo.sql. Detalle: %s",
                exc,
            )
    if _PATCH_105.is_file() and not _has_table(engine, schema="public", table="leasing_op_param_tipo"):
        try:
            _run_sql_patch_autocommit(engine, _PATCH_105)
            logger.info("Parche aplicado: leasing operativo parámetros por tipo (105).")
        except Exception as exc:
            logger.warning(
                "No se pudo aplicar 105_leasing_operativo_parametros_tipo.sql. Detalle: %s",
                exc,
            )
    if _PATCH_106.is_file() and not _has_table(engine, schema="public", table="leasing_op_documento_proceso"):
        try:
            _run_sql_patch_autocommit(engine, _PATCH_106)
            logger.info("Parche aplicado: leasing operativo documentos de proceso (106).")
        except Exception as exc:
            logger.warning(
                "No se pudo aplicar 106_leasing_operativo_documentos.sql. Detalle: %s",
                exc,
            )
    # Config contable base LOP (usa tablas fin.config_* existentes).
    # Se aplica siempre porque el patch es idempotente y también corrige mapeos históricos.
    if _PATCH_107.is_file() and _has_table(engine, schema="fin", table="config_contable_detalle_modulo"):
        try:
            _run_sql_patch_autocommit(engine, _PATCH_107)
            logger.info("Parche aplicado: configuración contable base leasing operativo (107).")
        except Exception as exc:
            logger.warning(
                "No se pudo aplicar 107_leasing_operativo_contabilidad_base.sql. Detalle: %s",
                exc,
            )
    # Re-seed catálogos si existen tablas pero quedaron vacías por patch parcial/manual.
    if _has_table(engine, schema="public", table="leasing_op_tipo_activo") and _PATCH_102.is_file():
        with engine.connect() as conn:
            tipos_n = int(
                conn.execute(text("SELECT COUNT(*) FROM public.leasing_op_tipo_activo")).scalar() or 0
            )
        if tipos_n == 0:
            try:
                _run_sql_patch_autocommit(engine, _PATCH_102)
                logger.info("Re-seed leasing operativo aplicado (102) por catálogo tipo_activo vacío.")
            except Exception as exc:
                logger.warning("No se pudo re-seed 102_leasing_operativo.sql: %s", exc)
    if _has_table(engine, schema="public", table="leasing_op_param_tipo") and _PATCH_105.is_file():
        with engine.connect() as conn:
            param_n = int(
                conn.execute(text("SELECT COUNT(*) FROM public.leasing_op_param_tipo")).scalar() or 0
            )
        if param_n == 0:
            try:
                _run_sql_patch_autocommit(engine, _PATCH_105)
                logger.info("Re-seed leasing operativo aplicado (105) por parámetros vacíos.")
            except Exception as exc:
                logger.warning("No se pudo re-seed 105_leasing_operativo_parametros_tipo.sql: %s", exc)


def ensure_fin_config_contable_seed(engine: Engine) -> None:
    """
    Garantiza configuración contable mínima para:
    - Inventario recepción sin factura (asientos al ingresar stock)
    - Ventas nota de venta (ingreso + costo de venta)

    Si faltan reglas, aplica 090/091/092 de forma idempotente.
    """
    if engine.dialect.name != "postgresql":
        return

    for p in (_PATCH_090, _PATCH_091, _PATCH_092):
        if not p.is_file():
            logger.warning("No se encontró %s; no se puede sembrar config contable.", p)
            return
    try:
        _ensure_plan_cuenta_minima_for_contabilidad_seed(engine)
    except Exception as exc:
        logger.warning("No se pudo preparar plan de cuentas mínimo para seed contable: %s", exc)
        return

    if not _has_table(engine, schema="fin", table="config_contable_detalle_modulo"):
        try:
            logger.info("Aplicando seed contable 090/091/092 (tablas fin.config_* no existen).")
            for p in (_PATCH_090, _PATCH_091, _PATCH_092):
                _run_sql_patch_autocommit(engine, p)
        except Exception as exc:
            logger.warning("No se pudo aplicar seed contable 090/091/092: %s", exc)
        return

    with engine.connect() as conn:
        inv_ok = bool(
            conn.execute(
                text(
                    """
                    SELECT 1
                    FROM fin.config_contable_detalle_modulo
                    WHERE modulo = 'INVENTARIO'
                      AND submodulo = 'RECEPCION'
                      AND tipo_documento = 'COMPRA_SIN_FACTURA'
                      AND codigo_evento = 'INGRESO_COMPRA_SIN_FACTURA'
                      AND estado = 'ACTIVO'
                    LIMIT 1
                    """
                )
            ).scalar()
        )
        venta_ok = bool(
            conn.execute(
                text(
                    """
                    SELECT 1
                    FROM fin.config_contable_detalle_modulo
                    WHERE modulo = 'VENTAS'
                      AND submodulo = 'NOTA_VENTA'
                      AND codigo_evento IN ('VENTA_CONTADO', 'VENTA_CREDITO')
                      AND estado = 'ACTIVO'
                    LIMIT 1
                    """
                )
            ).scalar()
        )

    if inv_ok and venta_ok:
        return

    try:
        logger.info(
            "Reglas contables faltantes (inventario=%s, ventas=%s). Aplicando 090/091/092...",
            inv_ok,
            venta_ok,
        )
        for p in (_PATCH_090, _PATCH_091, _PATCH_092):
            _run_sql_patch_autocommit(engine, p)
        logger.info("Seed contable 090/091/092 aplicado correctamente.")
    except Exception as exc:
        logger.warning("No se pudo aplicar seed contable 090/091/092: %s", exc)


def ensure_postventa_crm_schema(engine: Engine) -> None:
    """Aplica migración SQL idempotente de Postventa CRM."""
    if engine.dialect.name != "postgresql":
        return
    if not _PATCH_111.is_file():
        msg = f"No se encontró el patch requerido de Postventa CRM: {_PATCH_111}"
        logger.error(msg)
        raise RuntimeError(msg)
    try:
        _run_sql_patch_autocommit(engine, _PATCH_111)
        logger.info("Parche aplicado/verificado: postventa CRM cases (111).")
    except Exception as exc:
        logger.error(
            "Fallo aplicando 111_postventa_crm_cases.sql. "
            "Postventa CRM puede fallar hasta corregir el esquema. Detalle: %s",
            exc,
            exc_info=True,
        )
        raise


def ensure_empleados_bootstrap(engine: Engine) -> None:
    """Crea public.empleados si no existe (115). Requerido para nómina/transferencias en bases solo-SQL."""
    if engine.dialect.name != "postgresql":
        return
    if not _PATCH_115.is_file():
        logger.warning("No se encontró %s; omitiendo bootstrap empleados.", _PATCH_115)
        return
    try:
        _run_sql_patch_autocommit(engine, _PATCH_115)
        logger.info("Bootstrap empleados aplicado/verificado (115).")
    except Exception as exc:
        logger.warning(
            "No se pudo aplicar 115_empleados_bootstrap.sql. Detalle: %s",
            exc,
            exc_info=True,
        )


def ensure_remuneraciones_bootstrap(engine: Engine) -> None:
    """
    Tablas y columnas de remuneraciones (117). Idempotente; necesario si AUTO_MIGRATE_ON_STARTUP=false.
    Incluye empleados.auth_usuario_id y periodos_remuneracion.asiento_pago_id.
    """
    if engine.dialect.name != "postgresql":
        return
    if not _PATCH_117.is_file():
        logger.warning("No se encontró %s; omitiendo bootstrap remuneraciones.", _PATCH_117)
        return
    try:
        _run_sql_patch_autocommit(engine, _PATCH_117)
        logger.info("Bootstrap remuneraciones aplicado/verificado (117).")
    except Exception as exc:
        logger.warning(
            "No se pudo aplicar 117_remuneraciones_bootstrap.sql (revise permisos DDL en la BD). Detalle: %s",
            exc,
            exc_info=True,
        )


def ensure_remuneraciones_parametros_periodo_schema(engine: Engine) -> None:
    """Aplica schema de parámetros de remuneración por período (118)."""
    if engine.dialect.name != "postgresql":
        return
    if not _PATCH_118.is_file():
        logger.warning("No se encontró %s; omitiendo schema de parámetros por período.", _PATCH_118)
        return
    try:
        _run_sql_patch_autocommit(engine, _PATCH_118)
        logger.info("Schema remuneracion_parametros_periodo aplicado/verificado (118).")
    except Exception as exc:
        logger.warning("No se pudo aplicar 118_remuneraciones_parametros_periodo.sql. Detalle: %s", exc)


def ensure_remuneraciones_horas_periodo_schema(engine: Engine) -> None:
    """Aplica schema de carga mensual de horas de remuneración (119)."""
    if engine.dialect.name != "postgresql":
        return
    if not _PATCH_119.is_file():
        logger.warning("No se encontró %s; omitiendo schema de horas por período.", _PATCH_119)
        return
    try:
        _run_sql_patch_autocommit(engine, _PATCH_119)
        logger.info("Schema remuneracion_horas_periodo aplicado/verificado (119).")
    except Exception as exc:
        logger.warning("No se pudo aplicar 119_remuneraciones_horas_periodo.sql. Detalle: %s", exc)


def ensure_remuneraciones_auditoria_schema(engine: Engine) -> None:
    """Tabla de auditoría de acciones en nómina (120)."""
    if engine.dialect.name != "postgresql":
        return
    if not _PATCH_120.is_file():
        logger.warning("No se encontró %s; omitiendo auditoría remuneraciones.", _PATCH_120)
        return
    try:
        _run_sql_patch_autocommit(engine, _PATCH_120)
        logger.info("Schema remuneracion_audit_log aplicado/verificado (120).")
    except Exception as exc:
        logger.warning("No se pudo aplicar 120_remuneraciones_auditoria.sql. Detalle: %s", exc)


def ensure_remuneraciones_asiento_provision_column(engine: Engine) -> None:
    """Columna asiento_provision_id en periodos_remuneracion (121)."""
    if engine.dialect.name != "postgresql":
        return
    if not _PATCH_121.is_file():
        logger.warning("No se encontró %s; omitiendo columna provisión nómina.", _PATCH_121)
        return
    try:
        _run_sql_patch_autocommit(engine, _PATCH_121)
        logger.info("Columna asiento_provision_id remuneraciones aplicada/verificada (121).")
    except Exception as exc:
        logger.warning("No se pudo aplicar 121_remuneraciones_asiento_provision.sql. Detalle: %s", exc)


def ensure_empleados_transferencia_bancaria_columns(engine: Engine) -> None:
    """Columnas opcionales de transferencia en empleados (122)."""
    if engine.dialect.name != "postgresql":
        return
    if not _PATCH_122.is_file():
        logger.warning("No se encontró %s; omitiendo columnas transferencia empleados.", _PATCH_122)
        return
    try:
        _run_sql_patch_autocommit(engine, _PATCH_122)
        logger.info("Columnas transferencia empleados aplicadas/verificadas (122).")
    except Exception as exc:
        logger.warning("No se pudo aplicar 122_empleados_transferencia_bancaria.sql. Detalle: %s", exc)


def ensure_transporte_fondos_control_schema(engine: Engine) -> None:
    """Aplica ampliaciones idempotentes de transporte/fondos y tabla de mantenciones."""
    if engine.dialect.name != "postgresql":
        return
    if not _PATCH_112.is_file():
        return
    try:
        _run_sql_patch_autocommit(engine, _PATCH_112)
        logger.info("Parche aplicado/verificado: transporte/fondos control (112).")
    except Exception as exc:
        logger.warning("No se pudo aplicar 112_transporte_fondos_control.sql. Detalle: %s", exc)


def ensure_remuneraciones_seed(engine: Engine) -> None:
    """Conceptos mínimos de remuneración y parámetro de bono por viaje (idempotente)."""
    if not _has_table(engine, schema="public", table="conceptos_remuneracion"):
        return
    try:
        from decimal import Decimal

        from models.remuneraciones.models import ConceptoRemuneracion, RemuneracionParametro
    except Exception as exc:
        logger.debug("Modelos remuneraciones no disponibles: %s", exc)
        return

    # (codigo, nombre, tipo, imponible, tributable, legal, afecta_liquido, origen, orden)
    conceptos: tuple[tuple, ...] = (
        ("SUELDO_BASE", "Sueldo base", "haber_imponible", True, True, False, True, "contrato", 10),
        ("GRATIFICACION", "Gratificación", "haber_imponible", True, True, False, True, "sistema", 20),
        ("HORAS_EXTRAS", "Horas extras", "haber_imponible", True, True, False, True, "asistencia", 30),
        ("BONO_VIAJE", "Bono por viaje", "haber_imponible", True, True, False, True, "viaje", 40),
        ("BONO_KM", "Bono por kilómetros", "haber_imponible", True, True, False, True, "viaje", 50),
        ("BONO_NOCTURNO", "Bono nocturno", "haber_imponible", True, True, False, True, "asistencia", 60),
        ("BONO_ASISTENCIA", "Bono asistencia", "haber_no_imponible", False, False, False, True, "asistencia", 70),
        ("VIATICO", "Viático", "haber_no_imponible", False, False, False, True, "viatico", 80),
        ("ANTICIPO", "Anticipo (fondo por rendir)", "descuento_interno", False, False, False, True, "anticipo", 90),
        ("AFP", "Descuento AFP", "descuento_legal", True, True, True, True, "sistema", 100),
        ("SALUD", "Descuento salud", "descuento_legal", True, True, True, True, "sistema", 110),
        ("AFC", "Descuento AFC", "descuento_legal", True, True, True, True, "sistema", 120),
        ("IMPUESTO_UNICO", "Impuesto único", "descuento_legal", True, True, True, True, "sistema", 130),
        ("PRESTAMO_EMPRESA", "Préstamo empresa", "descuento_interno", False, False, False, True, "manual", 140),
        ("DESCUENTO_JUDICIAL", "Descuento judicial", "descuento_interno", False, False, False, True, "manual", 150),
        ("OTROS_DESCUENTOS", "Otros descuentos", "descuento_interno", False, False, False, True, "manual", 160),
        ("APORTE_EMPRESA_INFORMATIVO", "Aporte empresa (informativo)", "informativo", False, False, False, False, "sistema", 170),
    )

    SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
    with SessionLocal() as db:
        try:
            for row in conceptos:
                cod, nombre, tipo, imp, trib, leg, liq, orig, orden = row
                ex = db.scalars(select(ConceptoRemuneracion.id).where(ConceptoRemuneracion.codigo == cod)).first()
                if ex is not None:
                    continue
                db.add(
                    ConceptoRemuneracion(
                        codigo=cod,
                        nombre=nombre,
                        tipo=tipo,
                        imponible=imp,
                        tributable=trib,
                        legal=leg,
                        afecta_liquido=liq,
                        origen_catalogo=orig,
                        orden=orden,
                        activo=True,
                    )
                )
            pex = db.scalars(
                select(RemuneracionParametro.id).where(RemuneracionParametro.clave == "BONO_VIAJE_PCT_VALOR_FLETE")
            ).first()
            if pex is None:
                db.add(
                    RemuneracionParametro(
                        clave="BONO_VIAJE_PCT_VALOR_FLETE",
                        valor_numerico=Decimal("0"),
                        descripcion="Porcentaje sobre suma valor_flete de viajes CERRADOS en el periodo (0 = solo manual).",
                    )
                )
            for clave, val, desc in (
                (
                    "DESCUENTO_AFP_PCT_IMPOSABLE",
                    Decimal("0"),
                    "% sobre suma de ítems imponibles (0 = no automático). Orden legal típico no modelado en MVP.",
                ),
                (
                    "DESCUENTO_SALUD_PCT_IMPOSABLE",
                    Decimal("0"),
                    "% sobre suma de ítems imponibles (0 = no automático).",
                ),
                (
                    "VALOR_HORA_EXTRA",
                    Decimal("0"),
                    "Valor por hora extra. Si es 0, se calcula automáticamente como sueldo_base/180*1.5.",
                ),
                (
                    "BONO_NOCTURNO_VALOR_HORA",
                    Decimal("0"),
                    "Valor por hora nocturna (0 = no aplica bono nocturno automático).",
                ),
            ):
                ex2 = db.scalars(select(RemuneracionParametro.id).where(RemuneracionParametro.clave == clave)).first()
                if ex2 is None:
                    db.add(
                        RemuneracionParametro(
                            clave=clave,
                            valor_numerico=val,
                            descripcion=desc,
                        )
                    )
            db.commit()
        except Exception as exc:
            db.rollback()
            logger.warning("No se pudo sembrar conceptos/parametros de remuneración: %s", exc)
