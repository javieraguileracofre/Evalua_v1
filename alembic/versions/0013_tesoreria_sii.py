"""Tesorería: credencial SII, ejecuciones y detalle del libro."""
from __future__ import annotations

from pathlib import Path

from alembic import op
from sqlalchemy import text

revision = "0013_tesoreria_sii"
down_revision = "0012_auth_login_attempts"
branch_labels = None
depends_on = None

_SQL = Path(__file__).resolve().parents[2] / "db" / "psql" / "148_tesoreria_sii.sql"


def _statements(sql: str) -> list[str]:
    partes: list[str] = []
    for raw in sql.split(";"):
        utiles = [
            ln for ln in raw.splitlines() if ln.strip() and not ln.strip().startswith("--")
        ]
        if utiles:
            partes.append(raw.strip())
    return partes


def upgrade() -> None:
    bind = op.get_bind()
    for statement in _statements(_SQL.read_text(encoding="utf-8")):
        bind.execute(text(statement))
    from db.schema_revision import stamp_schema_revision

    stamp_schema_revision(bind, revision)


def downgrade() -> None:
    bind = op.get_bind()
    bind.execute(text("DROP TABLE IF EXISTS fin.sii_archivo"))
    bind.execute(text("DROP TABLE IF EXISTS fin.sii_ejecucion"))
    bind.execute(text("DROP TABLE IF EXISTS fin.sii_credencial"))
