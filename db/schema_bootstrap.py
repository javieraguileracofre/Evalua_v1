# db/schema_bootstrap.py
# -*- coding: utf-8 -*-
"""Aplica el esquema ERP real a una base de compañía. Idempotente."""
from __future__ import annotations

import logging
from pathlib import Path

from sqlalchemy import text
from sqlalchemy.engine import Connection, Engine

from db.schema_revision import ERP_SCHEMA_REVISION, stamp_schema_revision

logger = logging.getLogger("evalua.schema")
_ROOT = Path(__file__).resolve().parent.parent


def _exec_sql(engine: Engine, sql: str) -> None:
    with engine.connect() as conn:
        conn = conn.execution_options(isolation_level="AUTOCOMMIT")
        conn.exec_driver_sql(sql)


def _exec_company_sql(engine: Engine, sql: str) -> None:
    """Ejecuta SQL de arranque. CREATE EXTENSION ya lo hizo el administrador."""
    try:
        _exec_sql(engine, sql)
    except Exception as exc:
        message = str(exc).lower()
        if "extension" not in message and "pgcrypto" not in message and "citext" not in message:
            raise
        stripped = "\n".join(
            line for line in sql.splitlines() if "create extension" not in line.lower()
        )
        logger.warning("Se omite CREATE EXTENSION; el administrador ya instaló pgcrypto y citext.")
        _exec_sql(engine, stripped)


def apply_company_schema(bind: Engine | Connection) -> str:
    """Crea el esquema operacional actual y devuelve la revisión."""
    engine = bind.engine if isinstance(bind, Connection) else bind
    import models  # noqa: F401
    from db.base_class import Base
    from db.startup_schema import (
        ensure_ap_documento_contabilidad_columns,
        ensure_auth_identity_user_id,
        ensure_auth_password_reset_codes,
        ensure_auth_roles_seed,
        ensure_auth_usuario_modulos_visibles,
        ensure_auth_usuario_session_version,
        ensure_comercial_leasing_financiero_schema,
        ensure_credito_riesgo_empresarial_schema,
        ensure_credito_riesgo_schema,
        ensure_empleados_bootstrap,
        ensure_empleados_transferencia_bancaria_columns,
        ensure_fin_config_contable_seed,
        ensure_fondos_rendir_asiento_columns,
        ensure_leasing_financiero_plan_cuentas_min,
        ensure_leasing_operativo_schema,
        ensure_lf_cotizaciones_cleanup_prueba,
        ensure_mail_accounts_schema,
        ensure_ops_audit_backups_schema,
        ensure_postventa_crm_schema,
        ensure_remuneraciones_asiento_provision_column,
        ensure_remuneraciones_auditoria_schema,
        ensure_remuneraciones_bootstrap,
        ensure_remuneraciones_horas_periodo_schema,
        ensure_remuneraciones_parametros_periodo_schema,
        ensure_remuneraciones_seed,
        ensure_taller_ordenes_cotizacion_columns,
        ensure_transporte_fondos_control_schema,
        ensure_vehiculo_transporte_consumo_column,
    )

    if engine.dialect.name == "postgresql":
        with engine.connect() as conn:
            conn = conn.execution_options(isolation_level="AUTOCOMMIT")
            conn.execute(text("CREATE SCHEMA IF NOT EXISTS fin"))
        for sql_name in (
            "001_tenant_base.sql",
            "002a_fn_normalizar_rut.sql",
            "002b_fin_enum_types.sql",
        ):
            base_sql = _ROOT / "db" / "psql" / sql_name
            if not base_sql.is_file():
                continue
            sql = base_sql.read_text(encoding="utf-8").replace("%", "%%")
            _exec_company_sql(engine, sql)
    Base.metadata.create_all(bind=engine)
    for fn in (
        ensure_ap_documento_contabilidad_columns,
        ensure_taller_ordenes_cotizacion_columns,
        ensure_fondos_rendir_asiento_columns,
        ensure_vehiculo_transporte_consumo_column,
        ensure_transporte_fondos_control_schema,
        ensure_empleados_bootstrap,
        ensure_remuneraciones_bootstrap,
        ensure_remuneraciones_parametros_periodo_schema,
        ensure_remuneraciones_horas_periodo_schema,
        ensure_remuneraciones_auditoria_schema,
        ensure_remuneraciones_asiento_provision_column,
        ensure_empleados_transferencia_bancaria_columns,
        ensure_auth_roles_seed,
        ensure_auth_usuario_modulos_visibles,
        ensure_auth_usuario_session_version,
        ensure_auth_identity_user_id,
        ensure_auth_password_reset_codes,
        ensure_mail_accounts_schema,
        ensure_ops_audit_backups_schema,
        ensure_remuneraciones_seed,
        ensure_fin_config_contable_seed,
        ensure_comercial_leasing_financiero_schema,
        ensure_credito_riesgo_schema,
        ensure_leasing_operativo_schema,
        ensure_postventa_crm_schema,
        ensure_leasing_financiero_plan_cuentas_min,
        ensure_lf_cotizaciones_cleanup_prueba,
        ensure_credito_riesgo_empresarial_schema,
    ):
        try:
            fn(engine)
        except Exception as exc:
            logger.warning("Parche %s: %s", fn.__name__, type(exc).__name__)
    if engine.dialect.name == "postgresql":
        fase_d = _ROOT / "db" / "psql" / "144_fase_d_libros_tesoreria.sql"
        sql = fase_d.read_text(encoding="utf-8")
        with engine.begin() as conn:
            for raw in sql.split(";"):
                utiles = [
                    ln
                    for ln in raw.splitlines()
                    if ln.strip() and not ln.strip().startswith("--")
                ]
                if utiles:
                    conn.execute(text(raw.strip()))
        tesoreria = _ROOT / "db" / "psql" / "148_tesoreria_sii.sql"
        sql_sii = tesoreria.read_text(encoding="utf-8")
        with engine.begin() as conn:
            for raw in sql_sii.split(";"):
                utiles = [
                    ln
                    for ln in raw.splitlines()
                    if ln.strip() and not ln.strip().startswith("--")
                ]
                if utiles:
                    conn.execute(text(raw.strip()))
    stamp_schema_revision(engine)
    return ERP_SCHEMA_REVISION
