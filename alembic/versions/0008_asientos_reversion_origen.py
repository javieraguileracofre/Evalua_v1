"""Índice único de asientos incluye orígenes de reversión."""
from __future__ import annotations

from pathlib import Path

from alembic import op
from sqlalchemy import text

revision = "0008_asientos_reversion_origen"
down_revision = "0007_outbox_correlation_unique"
branch_labels = None
depends_on = None

_SQL = Path(__file__).resolve().parents[2] / "db" / "psql" / "143_asientos_reversion_origen.sql"


def upgrade() -> None:
    bind = op.get_bind()
    bind.execute(text(_SQL.read_text(encoding="utf-8")))
    from db.schema_revision import stamp_schema_revision

    stamp_schema_revision(bind, revision)


def downgrade() -> None:
    raise NotImplementedError(
        "0008 reemplaza el índice de idempotencia. Restaure un backup anterior a esta revisión."
    )
