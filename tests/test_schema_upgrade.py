# -*- coding: utf-8 -*-
"""Upgrade de esquema: servicio + CLI sin tocar Postgres real."""
from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from db.schema_revision import ERP_SCHEMA_REVISION
from services.platform.schema_upgrade import (
    SchemaStatusRow,
    UpgradeResult,
    inspect_company_schema,
    upgrade_company,
    upgrade_database_url,
)
from tools import upgrade_company_schema as cli


def test_upgrade_database_url_aplica_alembic_y_sella() -> None:
    lock_engine = MagicMock()
    lock_engine.dialect.name = "postgresql"
    lock_conn = MagicMock()
    lock_conn.execute.return_value.scalar.return_value = True
    lock_engine.connect.return_value = lock_conn
    stamp_engine = MagicMock()
    with (
        patch("services.platform.schema_upgrade._alembic_upgrade") as up,
        patch("services.platform.schema_upgrade._alembic_stamp_head") as stamp_al,
        patch(
            "services.platform.schema_upgrade.create_engine",
            side_effect=[lock_engine, stamp_engine],
        ),
        patch(
            "services.platform.schema_upgrade.stamp_schema_revision",
            return_value=ERP_SCHEMA_REVISION,
        ) as stamp_md,
        patch(
            "services.platform.schema_upgrade.runtime_schema_version",
            return_value=ERP_SCHEMA_REVISION,
        ),
    ):
        rev = upgrade_database_url("postgresql+psycopg://u:p@localhost/db")
    assert rev == ERP_SCHEMA_REVISION
    up.assert_called_once()
    stamp_md.assert_called_once()
    stamp_al.assert_called_once()
    stamp_engine.dispose.assert_called_once()
    lock_engine.dispose.assert_called_once()
    lock_conn.close.assert_called_once()


def test_inspect_company_schema_outdated_without_runtime() -> None:
    record = SimpleNamespace(status="ACTIVE", schema_version="0001_baseline")
    company = SimpleNamespace(
        id=7,
        code="acme",
        status="ACTIVE",
        schema_version="0001_baseline",
        database=record,
    )
    with patch(
        "services.platform.schema_upgrade.company_database_url",
        side_effect=RuntimeError("no db"),
    ):
        row = inspect_company_schema(company)  # type: ignore[arg-type]
    assert isinstance(row, SchemaStatusRow)
    assert row.needs_upgrade is True
    assert row.is_current is False
    assert row.detail


def test_upgrade_company_success_updates_identity() -> None:
    record = SimpleNamespace(status="ACTIVE", schema_version="0001_baseline")
    company = SimpleNamespace(
        id=3,
        code="acme",
        status="ACTIVE",
        schema_version="0001_baseline",
        status_detail="viejo",
        database=record,
    )
    db = MagicMock()
    db.get.return_value = company
    actor = SimpleNamespace(id=99)

    with (
        patch(
            "services.platform.schema_upgrade.company_database_url",
            return_value="postgresql+psycopg://u:p@localhost/db",
        ),
        patch(
            "services.platform.schema_upgrade.upgrade_database_url",
            return_value=ERP_SCHEMA_REVISION,
        ),
        patch("services.platform.schema_upgrade.write_audit"),
        patch("db.company_engine.invalidate_company_engine"),
    ):
        result = upgrade_company(db, 3, actor=actor)

    assert result.ok is True
    assert result.revision == ERP_SCHEMA_REVISION
    assert company.schema_version == ERP_SCHEMA_REVISION
    assert record.schema_version == ERP_SCHEMA_REVISION
    assert company.status_detail is None
    db.commit.assert_called()


def test_upgrade_company_sin_base_active() -> None:
    company = SimpleNamespace(
        id=1,
        code="x",
        schema_version="",
        database=None,
    )
    db = MagicMock()
    db.get.return_value = company
    result = upgrade_company(db, 1)
    assert result.ok is False
    assert "ACTIVE" in result.detail


def test_cli_requires_action() -> None:
    with pytest.raises(SystemExit):
        cli.main([])


def test_cli_legacy_sin_database_url(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "core.config.settings",
        SimpleNamespace(database_url=""),
    )
    assert cli.main(["--legacy"]) == 1


def test_cli_status_ok(monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    row = SchemaStatusRow(
        company_id=1,
        code="acme",
        status="ACTIVE",
        identity_version=ERP_SCHEMA_REVISION,
        database_version=ERP_SCHEMA_REVISION,
        runtime_version=ERP_SCHEMA_REVISION,
        is_current=True,
        needs_upgrade=False,
    )
    fake_db = MagicMock()
    maker = MagicMock(return_value=fake_db)
    monkeypatch.setattr("db.identity_session.get_identity_sessionmaker", lambda: maker)
    with patch("services.platform.schema_upgrade.list_schema_status", return_value=[row]):
        code = cli.main(["--status"])
    out = capsys.readouterr().out
    assert code == 0
    assert "acme" in out
    assert "needs_upgrade=0" in out


def test_upgrade_result_dataclass() -> None:
    r = UpgradeResult(1, "x", False, "", "fail")
    assert r.ok is False
