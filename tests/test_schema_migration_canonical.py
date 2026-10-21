# tests/test_schema_migration_canonical.py
# -*- coding: utf-8 -*-
"""Canonicidad Alembic / ERP_SCHEMA_REVISION / pack 0004."""
from __future__ import annotations

from pathlib import Path

from db.schema_revision import ERP_SCHEMA_REVISION, alembic_head_revision, schema_is_current

ROOT = Path(__file__).resolve().parents[1]
VERSIONS = ROOT / "alembic" / "versions"


def test_head_is_0013_tesoreria_sii():
    assert alembic_head_revision() == "0013_tesoreria_sii"
    assert ERP_SCHEMA_REVISION == "0013_tesoreria_sii"
    assert schema_is_current(ERP_SCHEMA_REVISION)


def test_revision_chain_linear():
    revisions: dict[str, str | None] = {}
    for path in sorted(VERSIONS.glob("*.py")):
        if path.name.startswith("__"):
            continue
        rev = down = None
        for line in path.read_text(encoding="utf-8").splitlines():
            s = line.strip()
            if s.startswith("revision") and "=" in s and "down_revision" not in s:
                rev = s.split("=", 1)[1].strip().strip("\"'")
            elif s.startswith("down_revision") and "=" in s:
                raw = s.split("=", 1)[1].strip()
                down = None if raw in {"None", "none"} else raw.strip("\"'")
        if rev:
            revisions[rev] = down
    assert "0001_baseline" in revisions
    assert revisions["0002_ops_audit_backups"] == "0001_baseline"
    assert revisions["0003_lop_residual_engine"] == "0002_ops_audit_backups"
    assert revisions["0004_platform_auth_mail_lf_lop"] == "0003_lop_residual_engine"
    assert revisions["0005_asientos_origen_idempotente"] == "0004_platform_auth_mail_lf_lop"
    assert revisions["0006_domain_event_outbox"] == "0005_asientos_origen_idempotente"
    assert revisions["0007_outbox_correlation_unique"] == "0006_domain_event_outbox"
    assert revisions["0008_asientos_reversion_origen"] == "0007_outbox_correlation_unique"
    assert revisions["0009_fase_d_libros_tesoreria"] == "0008_asientos_reversion_origen"
    assert revisions["0010_asientos_detalle_numeric_18"] == "0009_fase_d_libros_tesoreria"
    assert revisions["0011_asientos_cabecera_cuadre"] == "0010_asientos_detalle_numeric_18"
    assert revisions["0012_auth_login_attempts"] == "0011_asientos_cabecera_cuadre"
    assert revisions["0013_tesoreria_sii"] == "0012_auth_login_attempts"
    pointed = {d for d in revisions.values() if d}
    heads = [r for r in revisions if r not in pointed]
    assert heads == ["0013_tesoreria_sii"]


def test_0004_references_expected_sql_files():
    src = (VERSIONS / "0004_platform_auth_mail_lf_lop.py").read_text(encoding="utf-8")
    for name in (
        "132_auth_password_reset_codes.sql",
        "133_mail_accounts.sql",
        "134_auth_usuario_session_version.sql",
        "135_leasing_financiero_cotizacion_fase1.sql",
        "136_leasing_financiero_estados_fase1.sql",
        "138_leasing_operativo_tipos_flota.sql",
    ):
        assert name in src
        assert (ROOT / "db" / "psql" / name).is_file()


def test_0005_0006_0007_0008_0009_sql_present():
    assert "140_asientos_origen_idempotente.sql" in (
        VERSIONS / "0005_asientos_origen_idempotente.py"
    ).read_text(encoding="utf-8")
    assert "141_domain_event_outbox.sql" in (
        VERSIONS / "0006_domain_event_outbox.py"
    ).read_text(encoding="utf-8")
    assert "142_outbox_correlation_unique.sql" in (
        VERSIONS / "0007_outbox_correlation_unique.py"
    ).read_text(encoding="utf-8")
    assert "143_asientos_reversion_origen.sql" in (
        VERSIONS / "0008_asientos_reversion_origen.py"
    ).read_text(encoding="utf-8")
    assert "144_fase_d_libros_tesoreria.sql" in (
        VERSIONS / "0009_fase_d_libros_tesoreria.py"
    ).read_text(encoding="utf-8")
    assert (ROOT / "db" / "psql" / "140_asientos_origen_idempotente.sql").is_file()
    assert (ROOT / "db" / "psql" / "141_domain_event_outbox.sql").is_file()
    assert (ROOT / "db" / "psql" / "142_outbox_correlation_unique.sql").is_file()
    assert (ROOT / "db" / "psql" / "143_asientos_reversion_origen.sql").is_file()
    assert (ROOT / "db" / "psql" / "144_fase_d_libros_tesoreria.sql").is_file()
    assert "145_asientos_detalle_numeric_18.sql" in (
        VERSIONS / "0010_asientos_detalle_numeric_18.py"
    ).read_text(encoding="utf-8")
    assert (ROOT / "db" / "psql" / "145_asientos_detalle_numeric_18.sql").is_file()
    assert "146_asientos_cabecera_cuadre.sql" in (
        VERSIONS / "0011_asientos_cabecera_cuadre.py"
    ).read_text(encoding="utf-8")
    assert (ROOT / "db" / "psql" / "146_asientos_cabecera_cuadre.sql").is_file()
    assert "147_auth_login_attempts.sql" in (
        VERSIONS / "0012_auth_login_attempts.py"
    ).read_text(encoding="utf-8")
    assert (ROOT / "db" / "psql" / "147_auth_login_attempts.sql").is_file()
    assert "148_tesoreria_sii.sql" in (VERSIONS / "0013_tesoreria_sii.py").read_text(encoding="utf-8")
    assert (ROOT / "db" / "psql" / "148_tesoreria_sii.sql").is_file()


def test_upgrade_company_failure_not_ok():
    from services.platform.schema_upgrade import UpgradeResult

    failed = UpgradeResult(1, "DEMO", False, "", "fallo")
    assert failed.ok is False
    assert failed.revision == ""
