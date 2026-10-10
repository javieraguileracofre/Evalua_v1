"""Esquema ERP actual. No reescribe la historia de db/psql: la aplica."""
from __future__ import annotations

from alembic import op

revision = "0001_baseline"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    from db.schema_bootstrap import apply_company_schema

    apply_company_schema(op.get_bind())


def downgrade() -> None:
    raise RuntimeError("El esquema base de EvaluaERP no se revierte de forma automática.")
