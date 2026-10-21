"""Alinea la cabecera del asiento con el código y exige el cuadre al commit."""
from __future__ import annotations

from pathlib import Path

from alembic import op
from sqlalchemy import text

revision = "0011_asientos_cabecera_cuadre"
down_revision = "0010_asientos_detalle_numeric_18"
branch_labels = None
depends_on = None

_SQL = Path(__file__).resolve().parents[2] / "db" / "psql" / "146_asientos_cabecera_cuadre.sql"


def upgrade() -> None:
    bind = op.get_bind()
    # El archivo incluye funciones y bloques DO; no se puede cortar por ';'.
    bind.execute(text(_SQL.read_text(encoding="utf-8")))
    from db.schema_revision import stamp_schema_revision

    stamp_schema_revision(bind, revision)


def downgrade() -> None:
    bind = op.get_bind()
    bind.execute(text("DROP TRIGGER IF EXISTS trg_validar_asiento_cuadrado ON public.asientos_detalle"))
    bind.execute(text("DROP FUNCTION IF EXISTS public.fn_validar_asiento_cuadrado()"))
    for name in (
        "chk_asiento_detalle_un_lado",
        "chk_asiento_detalle_haber_nonneg",
        "chk_asiento_detalle_debe_nonneg",
        "chk_asiento_estado",
    ):
        bind.execute(text(f"ALTER TABLE public.asientos_detalle DROP CONSTRAINT IF EXISTS {name}"))
        bind.execute(text(f"ALTER TABLE public.asientos_contables DROP CONSTRAINT IF EXISTS {name}"))
    bind.execute(
        text(
            """
            ALTER TABLE public.asientos_contables
                DROP COLUMN IF EXISTS moneda,
                DROP COLUMN IF EXISTS estado,
                DROP COLUMN IF EXISTS usuario,
                DROP COLUMN IF EXISTS fecha_actualizacion
            """
        )
    )
