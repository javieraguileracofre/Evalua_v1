# tools/generar_mapa_bd.py
# -*- coding: utf-8 -*-
from __future__ import annotations

import os
import re
from collections import defaultdict
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.engine import Engine


# ============================================================
# CONFIG
# ============================================================

BASE_DIR = Path(__file__).resolve().parent.parent
OUTPUT_DIR = BASE_DIR / "docs" / "db_inspect"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

load_dotenv(BASE_DIR / ".env")

import sys

if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    raise RuntimeError("No se encontró DATABASE_URL en .env")


# ============================================================
# HELPERS
# ============================================================

def snake_to_pascal(value: str) -> str:
    parts = re.split(r"[_\s]+", value.strip())
    return "".join(p.capitalize() for p in parts if p)


def safe_class_name(schema: str, table: str) -> str:
    if schema == "public":
        return snake_to_pascal(table)
    return f"{snake_to_pascal(schema)}{snake_to_pascal(table)}"


def sqlalchemy_type_from_pg(
    data_type: str | None,
    udt_name: str | None,
    char_length: Any,
    numeric_precision: Any,
    numeric_scale: Any,
) -> str:
    dt = (data_type or "").lower()
    udt = (udt_name or "").lower()

    if dt in ("integer",):
        return "Integer"
    if dt in ("bigint",):
        return "BigInteger"
    if dt in ("smallint",):
        return "SmallInteger"
    if dt in ("boolean",):
        return "Boolean"
    if dt in ("text",):
        return "Text"
    if dt in ("character varying", "varchar"):
        return f"String({char_length})" if char_length else "String"
    if dt in ("character", "char"):
        return f"String({char_length})" if char_length else "String"
    if dt in ("date",):
        return "Date"
    if "timestamp" in dt:
        return "DateTime"
    if dt.startswith("time"):
        return "Time"
    if dt in ("numeric", "decimal"):
        if numeric_precision is not None and numeric_scale is not None:
            return f"Numeric({numeric_precision}, {numeric_scale})"
        if numeric_precision is not None:
            return f"Numeric({numeric_precision})"
        return "Numeric"
    if dt in ("double precision",):
        return "Float"
    if dt in ("real",):
        return "Float"
    if dt in ("uuid",):
        return "UUID(as_uuid=True)"
    if dt in ("json", "jsonb"):
        return "JSON"
    if dt == "array":
        return "ARRAY(String)"
    if dt == "user-defined":
        return "String  # USER-DEFINED::" + (udt_name or "unknown")

    if udt in ("int4",):
        return "Integer"
    if udt in ("int8",):
        return "BigInteger"
    if udt in ("varchar",):
        return f"String({char_length})" if char_length else "String"
    if udt in ("text",):
        return "Text"
    if udt in ("bool",):
        return "Boolean"
    if udt in ("date",):
        return "Date"
    if udt.startswith("timestamp"):
        return "DateTime"

    return "String"


def render_nullable(nullable: bool) -> str:
    return "True" if nullable else "False"


def clean_default(value: Any) -> str | None:
    if value is None:
        return None
    return str(value).strip()


# ============================================================
# SQL
# ============================================================

SQL_COLUMNS = text(
    """
    SELECT
        c.table_schema,
        c.table_name,
        c.column_name,
        c.ordinal_position,
        c.is_nullable,
        c.data_type,
        c.udt_name,
        c.character_maximum_length,
        c.numeric_precision,
        c.numeric_scale,
        c.column_default
    FROM information_schema.columns c
    WHERE c.table_schema NOT IN ('pg_catalog', 'information_schema')
    ORDER BY c.table_schema, c.table_name, c.ordinal_position
    """
)

SQL_FOREIGN_KEYS = text(
    """
    SELECT
        tc.table_schema,
        tc.table_name,
        kcu.column_name,
        tc.constraint_name,
        ccu.table_schema AS foreign_table_schema,
        ccu.table_name AS foreign_table_name,
        ccu.column_name AS foreign_column_name
    FROM information_schema.table_constraints AS tc
    JOIN information_schema.key_column_usage AS kcu
      ON tc.constraint_name = kcu.constraint_name
     AND tc.table_schema = kcu.table_schema
    JOIN information_schema.constraint_column_usage AS ccu
      ON ccu.constraint_name = tc.constraint_name
     AND ccu.table_schema = tc.table_schema
    WHERE tc.constraint_type = 'FOREIGN KEY'
      AND tc.table_schema NOT IN ('pg_catalog', 'information_schema')
    ORDER BY tc.table_schema, tc.table_name, kcu.column_name
    """
)

SQL_PRIMARY_KEYS = text(
    """
    SELECT
        tc.table_schema,
        tc.table_name,
        kcu.column_name,
        tc.constraint_name
    FROM information_schema.table_constraints tc
    JOIN information_schema.key_column_usage kcu
      ON tc.constraint_name = kcu.constraint_name
     AND tc.table_schema = kcu.table_schema
     AND tc.table_name = kcu.table_name
    WHERE tc.constraint_type = 'PRIMARY KEY'
      AND tc.table_schema NOT IN ('pg_catalog', 'information_schema')
    ORDER BY tc.table_schema, tc.table_name, kcu.ordinal_position
    """
)

SQL_INDEXES = text(
    """
    SELECT
        schemaname AS table_schema,
        tablename AS table_name,
        indexname,
        indexdef
    FROM pg_indexes
    WHERE schemaname NOT IN ('pg_catalog', 'information_schema')
    ORDER BY schemaname, tablename, indexname
    """
)


# ============================================================
# EXTRACTION
# ============================================================

def get_engine() -> Engine:
    from core.config import postgres_engine_connect_args, settings

    return create_engine(
        DATABASE_URL,
        future=True,
        connect_args=postgres_engine_connect_args(
            DATABASE_URL or "",
            settings.db_connect_timeout_seconds,
        ),
    )


def load_database_structure(engine: Engine) -> dict[str, Any]:
    inspector = inspect(engine)

    with engine.connect() as conn:
        columns_rows = [dict(r._mapping) for r in conn.execute(SQL_COLUMNS)]
        fk_rows = [dict(r._mapping) for r in conn.execute(SQL_FOREIGN_KEYS)]
        pk_rows = [dict(r._mapping) for r in conn.execute(SQL_PRIMARY_KEYS)]
        index_rows = [dict(r._mapping) for r in conn.execute(SQL_INDEXES)]

    pk_map = {(r["table_schema"], r["table_name"], r["column_name"]): r for r in pk_rows}
    fk_map = {(r["table_schema"], r["table_name"], r["column_name"]): r for r in fk_rows}

    structure: dict[str, Any] = defaultdict(lambda: defaultdict(dict))

    schemas = [s for s in inspector.get_schema_names() if s not in ("pg_catalog", "information_schema")]

    for schema in schemas:
        for table_name in inspector.get_table_names(schema=schema):
            structure[schema][table_name] = {
                "kind": "table",
                "columns": [],
                "indexes": [],
                "primary_keys": [],
                "foreign_keys": [],
            }

        for view_name in inspector.get_view_names(schema=schema):
            if view_name not in structure[schema]:
                structure[schema][view_name] = {
                    "kind": "view",
                    "columns": [],
                    "indexes": [],
                    "primary_keys": [],
                    "foreign_keys": [],
                }

    for row in columns_rows:
        schema = row["table_schema"]
        table = row["table_name"]

        if table not in structure[schema]:
            structure[schema][table] = {
                "kind": "table",
                "columns": [],
                "indexes": [],
                "primary_keys": [],
                "foreign_keys": [],
            }

        key = (schema, table, row["column_name"])
        pk = pk_map.get(key)
        fk = fk_map.get(key)

        col = {
            "name": row["column_name"],
            "ordinal_position": row["ordinal_position"],
            "nullable": row["is_nullable"] == "YES",
            "data_type": row["data_type"],
            "udt_name": row["udt_name"],
            "char_length": row["character_maximum_length"],
            "numeric_precision": row["numeric_precision"],
            "numeric_scale": row["numeric_scale"],
            "default": clean_default(row["column_default"]),
            "is_pk": pk is not None,
            "is_fk": fk is not None,
            "fk_schema": fk["foreign_table_schema"] if fk else None,
            "fk_table": fk["foreign_table_name"] if fk else None,
            "fk_column": fk["foreign_column_name"] if fk else None,
        }

        structure[schema][table]["columns"].append(col)

        if pk:
            structure[schema][table]["primary_keys"].append(row["column_name"])

        if fk:
            structure[schema][table]["foreign_keys"].append(
                {
                    "column": row["column_name"],
                    "target_schema": fk["foreign_table_schema"],
                    "target_table": fk["foreign_table_name"],
                    "target_column": fk["foreign_column_name"],
                    "constraint_name": fk["constraint_name"],
                }
            )

    for idx in index_rows:
        schema = idx["table_schema"]
        table = idx["table_name"]
        if table in structure[schema]:
            structure[schema][table]["indexes"].append(
                {
                    "name": idx["indexname"],
                    "definition": idx["indexdef"],
                }
            )

    return structure


# ============================================================
# OUTPUTS
# ============================================================

def write_markdown_report(structure: dict[str, Any], path: Path) -> None:
    lines: list[str] = []
    lines.append("# Reporte de estructura de base de datos")
    lines.append("")

    for schema in sorted(structure.keys()):
        lines.append(f"## Esquema `{schema}`")
        lines.append("")

        for table in sorted(structure[schema].keys()):
            item = structure[schema][table]
            lines.append(f"### `{schema}.{table}` ({item['kind']})")
            lines.append("")
            lines.append("| # | Columna | Tipo | Nullable | PK | FK | Default |")
            lines.append("|---|---------|------|----------|----|----|---------|")

            for col in sorted(item["columns"], key=lambda x: x["ordinal_position"]):
                tipo = sqlalchemy_type_from_pg(
                    col["data_type"],
                    col["udt_name"],
                    col["char_length"],
                    col["numeric_precision"],
                    col["numeric_scale"],
                )
                fk_txt = ""
                if col["is_fk"]:
                    fk_txt = f"{col['fk_schema']}.{col['fk_table']}.{col['fk_column']}"

                lines.append(
                    f"| {col['ordinal_position']} | {col['name']} | {tipo} | "
                    f"{'YES' if col['nullable'] else 'NO'} | "
                    f"{'YES' if col['is_pk'] else ''} | "
                    f"{fk_txt} | "
                    f"{col['default'] or ''} |"
                )

            if item["indexes"]:
                lines.append("")
                lines.append("**Índices**")
                lines.append("")
                for idx in item["indexes"]:
                    lines.append(f"- `{idx['name']}`")
                    lines.append(f"  - `{idx['definition']}`")

            lines.append("")

    path.write_text("\n".join(lines), encoding="utf-8")


def write_mermaid_diagram(structure: dict[str, Any], path: Path) -> None:
    lines: list[str] = []
    lines.append("erDiagram")

    added_entities: set[str] = set()

    for schema in sorted(structure.keys()):
        for table in sorted(structure[schema].keys()):
            entity = f"{schema}_{table}".replace(".", "_")
            if entity in added_entities:
                continue
            added_entities.add(entity)

            lines.append(f"    {entity} {{")
            for col in sorted(structure[schema][table]["columns"], key=lambda x: x["ordinal_position"]):
                tipo = sqlalchemy_type_from_pg(
                    col["data_type"],
                    col["udt_name"],
                    col["char_length"],
                    col["numeric_precision"],
                    col["numeric_scale"],
                )
                lines.append(f"        {tipo} {col['name']}")
            lines.append("    }")

    lines.append("")

    for schema in sorted(structure.keys()):
        for table in sorted(structure[schema].keys()):
            source = f"{schema}_{table}".replace(".", "_")
            for fk in structure[schema][table]["foreign_keys"]:
                target = f"{fk['target_schema']}_{fk['target_table']}".replace(".", "_")
                lines.append(f"    {source} }}o--|| {target} : {fk['column']}")

    path.write_text("\n".join(lines), encoding="utf-8")


def write_sqlalchemy_models(structure: dict[str, Any], path: Path) -> None:
    lines: list[str] = []
    lines.append("# models_autogen.py")
    lines.append("# -*- coding: utf-8 -*-")
    lines.append("from __future__ import annotations")
    lines.append("")
    lines.append("from sqlalchemy import Boolean, Date, DateTime, Float, ForeignKey, Integer, BigInteger, SmallInteger, Numeric, String, Text, Time")
    lines.append("from sqlalchemy.dialects.postgresql import UUID, JSON, ARRAY")
    lines.append("from sqlalchemy.orm import Mapped, mapped_column")
    lines.append("")
    lines.append("from db.base_class import Base")
    lines.append("")

    for schema in sorted(structure.keys()):
        for table in sorted(structure[schema].keys()):
            item = structure[schema][table]
            if item["kind"] != "table":
                continue

            class_name = safe_class_name(schema, table)

            lines.append("")
            lines.append(f"class {class_name}(Base):")
            lines.append(f'    __tablename__ = "{table}"')
            if schema != "public":
                lines.append(f'    __table_args__ = {{"schema": "{schema}"}}')
            lines.append("")

            if not item["columns"]:
                lines.append("    pass")
                continue

            for col in sorted(item["columns"], key=lambda x: x["ordinal_position"]):
                sa_type = sqlalchemy_type_from_pg(
                    col["data_type"],
                    col["udt_name"],
                    col["char_length"],
                    col["numeric_precision"],
                    col["numeric_scale"],
                )

                fk_expr = ""
                if col["is_fk"]:
                    target_schema = col["fk_schema"]
                    target_table = col["fk_table"]
                    target_col = col["fk_column"]
                    if target_schema == "public":
                        fk_expr = f', ForeignKey("{target_table}.{target_col}")'
                    else:
                        fk_expr = f', ForeignKey("{target_schema}.{target_table}.{target_col}")'

                pk_expr = ", primary_key=True" if col["is_pk"] else ""
                nullable_expr = f", nullable={render_nullable(col['nullable'])}"
                default_expr = ""
                if col["default"]:
                    default_expr = f"  # default={col['default']}"

                lines.append(
                    f'    {col["name"]}: Mapped[{sa_type}] = mapped_column('
                    f'{sa_type}{fk_expr}{pk_expr}{nullable_expr}){default_expr}'
                )

            lines.append("")

    path.write_text("\n".join(lines), encoding="utf-8")


# ============================================================
# MAIN
# ============================================================

def main() -> None:
    engine = get_engine()
    structure = load_database_structure(engine)

    md_path = OUTPUT_DIR / "schema_report.md"
    mermaid_path = OUTPUT_DIR / "schema_diagram.mmd"
    models_path = OUTPUT_DIR / "models_autogen.py"

    write_markdown_report(structure, md_path)
    write_mermaid_diagram(structure, mermaid_path)
    write_sqlalchemy_models(structure, models_path)

    print("=" * 80)
    print("INSPECCIÓN AVANZADA FINALIZADA")
    print("=" * 80)
    print(f"Markdown : {md_path}")
    print(f"Mermaid  : {mermaid_path}")
    print(f"Models   : {models_path}")
    print("=" * 80)


if __name__ == "__main__":
    main()