# -*- coding: utf-8 -*-
"""ERP_SCHEMA_REVISION debe ser el head de Alembic."""
from __future__ import annotations

from db.schema_revision import ERP_SCHEMA_REVISION, alembic_head_revision, schema_is_current


def test_erp_schema_revision_matches_alembic_head() -> None:
    assert alembic_head_revision() == ERP_SCHEMA_REVISION
    assert schema_is_current(ERP_SCHEMA_REVISION)
    assert not schema_is_current("0001_baseline")
