"""Índice único parcial para idempotencia contable concurrente."""
from __future__ import annotations

from pathlib import Path

from alembic import op
from sqlalchemy import text

revision = "0005_asientos_origen_idempotente"
down_revision = "0004_platform_auth_mail_lf_lop"
branch_labels = None
depends_on = None

_SQL = Path(__file__).resolve().parents[2] / "db" / "psql" / "140_asientos_origen_idempotente.sql"

_DUP_SQL = """
SELECT origen_tipo, origen_id, COUNT(*)::int AS n, array_agg(id ORDER BY id) AS ids
FROM public.asientos_contables
WHERE origen_id > 0
  AND origen_tipo IN (
      'AP_DOCUMENTO','AP_PAGO','NOTA_VENTA','NOTA_VENTA_ANULACION','PAGO_CLIENTE',
      'LEASING_FIN_ACTIVACION','LOP_ACTIVACION','LOP_FACTURACION',
      'FONDO_RENDIR_ENT','FONDO_RENDIR_LIQ','REMUNERACION_PROVISION','REMUNERACION_PAGO',
      'REV_MANUAL','INVENTARIO_MOV','LOP_DEPRECIACION'
  )
GROUP BY origen_tipo, origen_id
HAVING COUNT(*) > 1
LIMIT 20
"""


def upgrade() -> None:
    bind = op.get_bind()
    # Preflight: no consolidar datos automáticamente.
    try:
        rows = bind.execute(text(_DUP_SQL)).mappings().all()
    except Exception:
        rows = []
    if rows:
        sample = "; ".join(
            f"{r['origen_tipo']}/{r['origen_id']} ids={list(r['ids'])}" for r in rows
        )
        raise RuntimeError(
            "No se puede crear ux_asientos_origen_idempotente: hay asientos duplicados "
            f"por origen. Revise y resuelva manualmente antes de migrar. Muestra: {sample}"
        )

    raw = _SQL.read_text(encoding="utf-8")
    bind.execute(text(raw))
    from db.schema_revision import ERP_SCHEMA_REVISION, stamp_schema_revision

    stamp_schema_revision(bind, ERP_SCHEMA_REVISION)


def downgrade() -> None:
    op.execute(text("DROP INDEX IF EXISTS public.ux_asientos_origen_idempotente"))
    op.execute(text("DROP INDEX IF EXISTS public.ix_asientos_contables_fecha_origen"))
