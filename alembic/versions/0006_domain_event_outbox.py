"""Outbox transaccional de eventos de dominio."""
from __future__ import annotations

from pathlib import Path

from alembic import op
from sqlalchemy import text

revision = "0006_domain_event_outbox"
down_revision = "0005_asientos_origen_idempotente"
branch_labels = None
depends_on = None

_SQL = Path(__file__).resolve().parents[2] / "db" / "psql" / "141_domain_event_outbox.sql"


def upgrade() -> None:
    bind = op.get_bind()
    bind.execute(text(_SQL.read_text(encoding="utf-8")))
    from db.schema_revision import ERP_SCHEMA_REVISION, stamp_schema_revision

    stamp_schema_revision(bind, ERP_SCHEMA_REVISION)


def downgrade() -> None:
    op.execute(text("DROP TABLE IF EXISTS public.domain_event_outbox"))
