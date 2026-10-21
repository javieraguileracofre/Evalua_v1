"""Documento tributario interno, conciliación, FX, costo promedio y lecturas."""
from __future__ import annotations

from pathlib import Path

from alembic import op
from sqlalchemy import text

revision = "0009_fase_d_libros_tesoreria"
down_revision = "0008_asientos_reversion_origen"
branch_labels = None
depends_on = None

_SQL = Path(__file__).resolve().parents[2] / "db" / "psql" / "144_fase_d_libros_tesoreria.sql"


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
    raise NotImplementedError(
        "0009 agrega libros, conciliación y costo promedio. Restaure un backup anterior a esta revisión."
    )
