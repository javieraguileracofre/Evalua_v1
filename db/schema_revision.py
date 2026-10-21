# db/schema_revision.py
# -*- coding: utf-8 -*-
"""Revisión de esquema operacional.

Fuente de verdad: la revisión Alembic head (`alembic/versions`).
`ERP_SCHEMA_REVISION` debe coincidir con ese id. Los SQL en `db/psql/`
se aplican vía migraciones Alembic o `db.schema_bootstrap.apply_company_schema`.
"""
from __future__ import annotations

from pathlib import Path

from sqlalchemy import text
from sqlalchemy.engine import Connection, Engine

# Debe coincidir con alembic head (ver tests/test_schema_revision_alembic.py).
ERP_SCHEMA_REVISION = "0013_tesoreria_sii"

_ALEMBIC_VERSIONS = Path(__file__).resolve().parent.parent / "alembic" / "versions"


def schema_is_current(version: str | None) -> bool:
    return (version or "").strip() == ERP_SCHEMA_REVISION


def registry_schema_matches(company_version: str | None, database_version: str | None) -> bool:
    """Identity y el registro de la base deben coincidir con la revisión actual."""
    current = (company_version or "").strip()
    recorded = (database_version or "").strip()
    return schema_is_current(current) and recorded == current


def runtime_schema_version(engine: Engine) -> str:
    """Versión escrita en la base operacional. En PostgreSQL sale de app_metadata."""
    if engine.dialect.name != "postgresql":
        return ERP_SCHEMA_REVISION
    with engine.connect() as conn:
        row = conn.execute(
            text("SELECT app_version FROM public.app_metadata ORDER BY id LIMIT 1")
        ).first()
    if row is None:
        return ""
    return str(row[0] or "").strip()


def stamp_schema_revision(bind: Engine | Connection, version: str | None = None) -> str:
    """Escribe `app_metadata.app_version` (PostgreSQL). Idempotente."""
    rev = (version or ERP_SCHEMA_REVISION).strip()
    if isinstance(bind, Connection):
        conn = bind
        if conn.engine.dialect.name != "postgresql":
            return rev
        _stamp_on_connection(conn, rev)
        return rev
    engine = bind
    if engine.dialect.name != "postgresql":
        return rev
    with engine.begin() as conn:
        _stamp_on_connection(conn, rev)
    return rev


def _stamp_on_connection(conn: Connection, rev: str) -> None:
    conn.execute(
        text(
            """
            INSERT INTO public.app_metadata (tenant_code, tenant_name, app_version)
            SELECT 'company', 'company', :version
            WHERE NOT EXISTS (SELECT 1 FROM public.app_metadata)
            """
        ),
        {"version": rev},
    )
    conn.execute(
        text("UPDATE public.app_metadata SET app_version = :version"),
        {"version": rev},
    )


def alembic_head_revision() -> str:
    """Lee el head de Alembic sin conectar a la BD (grafo down_revision)."""
    revisions: dict[str, str | None] = {}
    for path in sorted(_ALEMBIC_VERSIONS.glob("*.py")):
        if path.name.startswith("__"):
            continue
        text_src = path.read_text(encoding="utf-8")
        rev: str | None = None
        down: str | None = None
        for line in text_src.splitlines():
            stripped = line.strip()
            if stripped.startswith("revision") and "=" in stripped and "down_revision" not in stripped:
                rev = stripped.split("=", 1)[1].strip().strip("\"'")
            elif stripped.startswith("down_revision") and "=" in stripped:
                raw = stripped.split("=", 1)[1].strip()
                down = None if raw in {"None", "none"} else raw.strip("\"'")
        if rev:
            revisions[rev] = down
    if not revisions:
        raise RuntimeError("No hay revisiones Alembic en alembic/versions.")
    pointed = {d for d in revisions.values() if d}
    heads = [r for r in revisions if r not in pointed]
    if len(heads) != 1:
        raise RuntimeError(f"Alembic head ambiguo: {heads!r}")
    return heads[0]
