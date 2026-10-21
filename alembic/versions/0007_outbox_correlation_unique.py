"""Índice único de correlation_id en outbox (idempotencia de publicación)."""
from __future__ import annotations

from pathlib import Path

from alembic import op
from sqlalchemy import text

revision = "0007_outbox_correlation_unique"
down_revision = "0006_domain_event_outbox"
branch_labels = None
depends_on = None

_SQL = Path(__file__).resolve().parents[2] / "db" / "psql" / "142_outbox_correlation_unique.sql"


def upgrade() -> None:
    bind = op.get_bind()
    # Preflight: correlation_ids duplicados bloquean el índice (no se auto-limpia).
    try:
        rows = bind.execute(
            text(
                """
                SELECT correlation_id, COUNT(*)::int AS n, array_agg(id ORDER BY id) AS ids
                FROM public.domain_event_outbox
                WHERE correlation_id IS NOT NULL AND btrim(correlation_id) <> ''
                GROUP BY correlation_id
                HAVING COUNT(*) > 1
                LIMIT 20
                """
            )
        ).mappings().all()
    except Exception:
        rows = []
    if rows:
        sample = "; ".join(f"{r['correlation_id']} ids={list(r['ids'])}" for r in rows)
        raise RuntimeError(
            "No se puede crear ux_domain_event_outbox_correlation: hay correlation_id "
            f"duplicados. Revise manualmente. Muestra: {sample}"
        )
    bind.execute(text(_SQL.read_text(encoding="utf-8")))
    from db.schema_revision import ERP_SCHEMA_REVISION, stamp_schema_revision

    stamp_schema_revision(bind, ERP_SCHEMA_REVISION)


def downgrade() -> None:
    op.execute(text("DROP INDEX IF EXISTS public.ux_domain_event_outbox_correlation"))
