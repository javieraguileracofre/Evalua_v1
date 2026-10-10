"""Motor residual LOP: curvas, snapshots y overrides."""
from __future__ import annotations

from pathlib import Path

from alembic import op
from sqlalchemy import text

revision = "0003_lop_residual_engine"
down_revision = "0002_ops_audit_backups"
branch_labels = None
depends_on = None

_SQL = Path(__file__).resolve().parents[2] / "db" / "psql" / "139_leasing_operativo_residual_engine.sql"


def upgrade() -> None:
    bind = op.get_bind()
    raw = _SQL.read_text(encoding="utf-8")
    bind.execute(text(raw))
    from db.schema_revision import ERP_SCHEMA_REVISION, stamp_schema_revision

    stamp_schema_revision(bind, ERP_SCHEMA_REVISION)


def downgrade() -> None:
    op.execute(text("DROP TABLE IF EXISTS public.leasing_op_residual_override"))
    op.execute(text("DROP TABLE IF EXISTS public.leasing_op_market_valuation_snapshot"))
    op.execute(text("DROP TABLE IF EXISTS public.leasing_op_residual_value_curve"))
    op.execute(text("DELETE FROM public.leasing_op_politica WHERE clave = 'residual_value_v1'"))
