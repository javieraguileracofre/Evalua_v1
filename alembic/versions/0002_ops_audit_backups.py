"""Auditoría operacional y metadatos de respaldos."""
from __future__ import annotations

from pathlib import Path

from alembic import op
from sqlalchemy import text

revision = "0002_ops_audit_backups"
down_revision = "0001_baseline"
branch_labels = None
depends_on = None

_SQL = Path(__file__).resolve().parents[2] / "db" / "psql" / "137_ops_audit_backups.sql"


def upgrade() -> None:
    bind = op.get_bind()
    raw = _SQL.read_text(encoding="utf-8")
    bind.execute(text(raw))
    from db.schema_revision import stamp_schema_revision

    stamp_schema_revision(bind, "0002_ops_audit_backups")


def downgrade() -> None:
    op.execute(text("DROP TABLE IF EXISTS public.ops_database_backup"))
    op.execute(text("DROP TABLE IF EXISTS public.auth_audit_event"))
