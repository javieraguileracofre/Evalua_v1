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
    ('110201', 'CAJA Y BANCOS', 3, NULL, 'ACTIVO', 'ACTIVO_CORRIENTE', 'DEUDORA', TRUE, FALSE, 'ACTIVO', 'Fondos disponibles'),
    ('110301', 'CLIENTES', 3, NULL, 'ACTIVO', 'ACTIVO_CORRIENTE', 'DEUDORA', TRUE, FALSE, 'ACTIVO', 'Cuentas por cobrar clientes'),
    ('110401', 'INVENTARIO MERCADERIA', 3, NULL, 'ACTIVO', 'ACTIVO_CORRIENTE', 'DEUDORA', TRUE, FALSE, 'ACTIVO', 'Inventario valorizado'),
    ('110501', 'IVA CREDITO FISCAL', 3, NULL, 'ACTIVO', 'ACTIVO_CORRIENTE', 'DEUDORA', TRUE, FALSE, 'ACTIVO', 'IVA crédito'),
    ('210000', 'PASIVOS CORRIENTES', 2, NULL, 'PASIVO', 'PASIVO_CORRIENTE', 'ACREEDORA', FALSE, FALSE, 'ACTIVO', 'Agrupador pasivos corrientes'),
    ('210101', 'PROVEEDORES', 3, NULL, 'PASIVO', 'PASIVO_CORRIENTE', 'ACREEDORA', TRUE, FALSE, 'ACTIVO', 'Proveedores por pagar'),
    ('210110', 'PROVEEDORES POR FACTURAR', 3, NULL, 'PASIVO', 'PASIVO_CORRIENTE', 'ACREEDORA', TRUE, FALSE, 'ACTIVO', 'Recepción sin factura'),
    ('210201', 'IVA DEBITO FISCAL', 3, NULL, 'PASIVO', 'PASIVO_CORRIENTE', 'ACREEDORA', TRUE, FALSE, 'ACTIVO', 'IVA débito'),
    ('410101', 'VENTAS', 3, NULL, 'INGRESO', 'INGRESO_OPERACIONAL', 'ACREEDORA', TRUE, TRUE, 'ACTIVO', 'Ingresos por ventas'),
    ('510000', 'COSTOS DE VENTAS', 2, NULL, 'COSTO', 'COSTO_VENTA', 'DEUDORA', FALSE, TRUE, 'ACTIVO', 'Agrupador costos'),
    ('510101', 'COSTO DE VENTAS', 3, NULL, 'COSTO', 'COSTO_VENTA', 'DEUDORA', TRUE, TRUE, 'ACTIVO', 'Costo mercadería vendida'),
    ('610104', 'GASTOS GENERALES', 3, NULL, 'GASTO', 'GASTO_ADMINISTRACION', 'DEUDORA', TRUE, TRUE, 'ACTIVO', 'Gastos de administración'),
    ('113701', 'CUENTAS POR COBRAR LEASING FINANCIERO', 3, NULL, 'ACTIVO', 'ACTIVO_CORRIENTE', 'DEUDORA', TRUE, FALSE, 'ACTIVO', 'Principal leasing financiero'),
    ('210701', 'OBLIGACIONES LEASING FINANCIERO', 3, NULL, 'PASIVO', 'PASIVO_CORRIENTE', 'ACREEDORA', TRUE, FALSE, 'ACTIVO', 'Pasivo leasing financiero'),
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
     WHERE h.codigo = '210110'
       AND p.codigo = '210000';

    UPDATE fin.plan_cuenta h
       SET cuenta_padre_id = p.id
      FROM fin.plan_cuenta p
     WHERE h.codigo = '510101'
       AND p.codigo = '510000';
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
    if has_cot and has_credit and leasing_cfg:
        return
    try:
        _run_sql_patch_autocommit(engine, _PATCH_100)
        logger.info("Parche aplicado: comercial leasing financiero (100).")
    except Exception as exc:
        logger.warning(
            "No se pudo aplicar 100_comercial_leasing_financiero.sql. "
            "Ejecute manualmente en la base si es necesario. Detalle: %s",
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
        return
    try:
        _run_sql_patch_autocommit(engine, _PATCH_101)
        logger.info("Parche aplicado: crédito y riesgo (101).")
    except Exception as exc:
        logger.warning(
            "No se pudo aplicar 101_credito_riesgo.sql. Ejecute manualmente en la base si es necesario. Detalle: %s",
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
