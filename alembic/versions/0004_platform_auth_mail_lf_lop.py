"""Pack canónico: auth reset/sesión, mail, LF fase1 y tipos flota LOP.

Absorbe en Alembic los SQL que antes solo corrían vía AUTO_MIGRATE / startup_schema:
132, 133, 134, 135, 136, 138.
"""
from __future__ import annotations

from pathlib import Path

from alembic import op
from sqlalchemy import text

revision = "0004_platform_auth_mail_lf_lop"
down_revision = "0003_lop_residual_engine"
branch_labels = None
depends_on = None

_PSQL = Path(__file__).resolve().parents[2] / "db" / "psql"
_FILES = (
    "132_auth_password_reset_codes.sql",
    "133_mail_accounts.sql",
    "134_auth_usuario_session_version.sql",
    "135_leasing_financiero_cotizacion_fase1.sql",
    "136_leasing_financiero_estados_fase1.sql",
    "138_leasing_operativo_tipos_flota.sql",
)


def _run_sql_file(bind, name: str) -> None:
    path = _PSQL / name
    if not path.is_file():
        raise FileNotFoundError(f"SQL de migración ausente: {path}")
    raw = path.read_text(encoding="utf-8")
    # psycopg3 acepta multi-statement en execute con text().
    bind.execute(text(raw))


def upgrade() -> None:
    bind = op.get_bind()
    for name in _FILES:
        _run_sql_file(bind, name)
    from db.schema_revision import ERP_SCHEMA_REVISION, stamp_schema_revision

    stamp_schema_revision(bind, ERP_SCHEMA_REVISION)


def downgrade() -> None:
    # DDL parcialmente irreversible (columnas/datos LF). Solo se documenta
    # recuperación vía backup; no se intenta DROP destructivo automático.
    raise NotImplementedError(
        "0004_platform_auth_mail_lf_lop no es reversible de forma segura; "
        "restaurar desde backup de la empresa."
    )
