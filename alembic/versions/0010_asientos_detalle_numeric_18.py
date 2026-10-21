"""Amplía debe y haber del detalle de asiento a numeric(18,2)."""
from __future__ import annotations

from pathlib import Path

from alembic import op
from sqlalchemy import text

revision = "0010_asientos_detalle_numeric_18"
down_revision = "0009_fase_d_libros_tesoreria"
branch_labels = None
depends_on = None

_SQL = Path(__file__).resolve().parents[2] / "db" / "psql" / "145_asientos_detalle_numeric_18.sql"


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
    bind.execute(text("DROP VIEW IF EXISTS public.analytics_resultado_mes"))
    bind.execute(
        text(
            """
            ALTER TABLE public.asientos_detalle
                ALTER COLUMN debe TYPE numeric(14, 2),
                ALTER COLUMN haber TYPE numeric(14, 2)
            """
        )
    )
    bind.execute(
        text(
            """
            CREATE VIEW public.analytics_resultado_mes AS
            SELECT
                CAST(EXTRACT(YEAR FROM a.fecha) AS integer) AS anio,
                CAST(EXTRACT(MONTH FROM a.fecha) AS integer) AS mes,
                d.codigo_cuenta,
                SUM(d.debe) AS debe,
                SUM(d.haber) AS haber
            FROM public.asientos_contables a
            JOIN public.asientos_detalle d ON d.asiento_id = a.id
            GROUP BY 1, 2, 3
            """
        )
    )
