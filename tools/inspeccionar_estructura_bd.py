# tools/inspeccionar_estructura_bd.py
# -*- coding: utf-8 -*-
from __future__ import annotations

import csv
import json
import os
from collections import defaultdict
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine


# ============================================================
# CONFIG
# ============================================================

BASE_DIR = Path(__file__).resolve().parent.parent
OUTPUT_DIR = BASE_DIR / "docs" / "db_inspect"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

load_dotenv(BASE_DIR / ".env")

DATABASE_URL = os.getenv("DATABASE_URL")

if not DATABASE_URL:
    raise RuntimeError(
        "No se encontró DATABASE_URL en el archivo .env. "
        "Debes definirla antes de ejecutar este script."
    )


# ============================================================
# QUERIES
# ============================================================

SQL_TABLES = text(
    """
    SELECT
        t.table_schema,
        t.table_name,
        t.table_type
    FROM information_schema.tables t
    WHERE t.table_schema NOT IN ('pg_catalog', 'information_schema')
    ORDER BY t.table_schema, t.table_name;
    """
)

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
        c.datetime_precision,
        c.column_default
    FROM information_schema.columns c
    WHERE c.table_schema NOT IN ('pg_catalog', 'information_schema')
    ORDER BY c.table_schema, c.table_name, c.ordinal_position;
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
    ORDER BY tc.table_schema, tc.table_name, kcu.ordinal_position;
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
    ORDER BY tc.table_schema, tc.table_name, kcu.column_name;
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
    ORDER BY schemaname, tablename, indexname;
    """
)


# ============================================================
# HELPERS
# ============================================================

def get_engine() -> Engine:
    return create_engine(DATABASE_URL, future=True)


def normalize_table_type(table_type: str) -> str:
    mapping = {
        "BASE TABLE": "TABLE",
        "VIEW": "VIEW",
        "FOREIGN": "FOREIGN",
        "LOCAL TEMPORARY": "TEMP",
    }
    return mapping.get(table_type, table_type)


def build_column_type(row: dict[str, Any]) -> str:
    data_type = row.get("data_type")
    udt_name = row.get("udt_name")
    char_len = row.get("character_maximum_length")
    num_precision = row.get("numeric_precision")
    num_scale = row.get("numeric_scale")
    dt_precision = row.get("datetime_precision")

    if data_type in {"character varying", "varchar", "character", "char"}:
        if char_len:
            return f"{data_type}({char_len})"
        return data_type

    if data_type in {"numeric", "decimal"}:
        if num_precision is not None and num_scale is not None:
            return f"{data_type}({num_precision},{num_scale})"
        if num_precision is not None:
            return f"{data_type}({num_precision})"
        return data_type

    if data_type in {"timestamp without time zone", "timestamp with time zone", "time without time zone", "time with time zone"}:
        if dt_precision is not None:
            return f"{data_type}({dt_precision})"
        return data_type

    if data_type == "USER-DEFINED":
        return f"USER-DEFINED::{udt_name}"

    if data_type == "ARRAY":
        return f"ARRAY::{udt_name}"

    return data_type or udt_name or "UNKNOWN"


def export_csv(rows: list[dict[str, Any]], path: Path) -> None:
    if not rows:
        path.write_text("", encoding="utf-8")
        return

    fieldnames = list(rows[0].keys())
    with path.open("w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def export_json(data: Any, path: Path) -> None:
    path.write_text(
        json.dumps(data, indent=2, ensure_ascii=False, default=str),
        encoding="utf-8",
    )


def export_txt_summary(
    structure: dict[str, dict[str, Any]],
    indexes_map: dict[tuple[str, str], list[dict[str, Any]]],
    path: Path,
) -> None:
    lines: list[str] = []
    lines.append("ESTRUCTURA DE BASE DE DATOS")
    lines.append("=" * 80)
    lines.append("")

    for schema_name in sorted(structure.keys()):
        lines.append(f"ESQUEMA: {schema_name}")
        lines.append("-" * 80)

        for table_name in sorted(structure[schema_name].keys()):
            table_info = structure[schema_name][table_name]
            table_type = table_info["table_type"]
            lines.append(f"{schema_name}.{table_name} [{table_type}]")

            for col in table_info["columns"]:
                extras = []
                if col["is_pk"]:
                    extras.append("PK")
                if col["is_fk"]:
                    extras.append(
                        f"FK -> {col['fk_target_schema']}.{col['fk_target_table']}.{col['fk_target_column']}"
                    )
                if col["is_nullable"] == "NO":
                    extras.append("NOT NULL")
                if col["column_default"]:
                    extras.append(f"DEFAULT={col['column_default']}")

                extra_txt = f" | {' | '.join(extras)}" if extras else ""
                lines.append(
                    f"  - {col['ordinal_position']:>2}. {col['column_name']} : {col['full_type']}{extra_txt}"
                )

            idxs = indexes_map.get((schema_name, table_name), [])
            if idxs:
                lines.append("    Índices:")
                for idx in idxs:
                    lines.append(f"      * {idx['indexname']}")
                    lines.append(f"        {idx['indexdef']}")

            lines.append("")

        lines.append("")

    path.write_text("\n".join(lines), encoding="utf-8")


# ============================================================
# MAIN
# ============================================================

def main() -> None:
    engine = get_engine()

    with engine.connect() as conn:
        tables = [dict(row._mapping) for row in conn.execute(SQL_TABLES)]
        columns = [dict(row._mapping) for row in conn.execute(SQL_COLUMNS)]
        primary_keys = [dict(row._mapping) for row in conn.execute(SQL_PRIMARY_KEYS)]
        foreign_keys = [dict(row._mapping) for row in conn.execute(SQL_FOREIGN_KEYS)]
        indexes = [dict(row._mapping) for row in conn.execute(SQL_INDEXES)]

    pk_map: dict[tuple[str, str, str], dict[str, Any]] = {
        (r["table_schema"], r["table_name"], r["column_name"]): r
        for r in primary_keys
    }

    fk_map: dict[tuple[str, str, str], dict[str, Any]] = {
        (r["table_schema"], r["table_name"], r["column_name"]): r
        for r in foreign_keys
    }

    table_type_map: dict[tuple[str, str], str] = {
        (t["table_schema"], t["table_name"]): normalize_table_type(t["table_type"])
        for t in tables
    }

    indexes_map: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for idx in indexes:
        indexes_map[(idx["table_schema"], idx["table_name"])].append(idx)

    detailed_rows: list[dict[str, Any]] = []
    structure: dict[str, dict[str, Any]] = defaultdict(dict)

    for col in columns:
        key = (col["table_schema"], col["table_name"], col["column_name"])
        pk = pk_map.get(key)
        fk = fk_map.get(key)

        row = {
            "schema": col["table_schema"],
            "table_name": col["table_name"],
            "table_type": table_type_map.get((col["table_schema"], col["table_name"]), "UNKNOWN"),
            "column_name": col["column_name"],
            "ordinal_position": col["ordinal_position"],
            "is_nullable": col["is_nullable"],
            "data_type": col["data_type"],
            "udt_name": col["udt_name"],
            "full_type": build_column_type(col),
            "character_maximum_length": col["character_maximum_length"],
            "numeric_precision": col["numeric_precision"],
            "numeric_scale": col["numeric_scale"],
            "datetime_precision": col["datetime_precision"],
            "column_default": col["column_default"],
            "is_primary_key": "YES" if pk else "NO",
            "primary_key_name": pk["constraint_name"] if pk else None,
            "is_foreign_key": "YES" if fk else "NO",
            "foreign_key_name": fk["constraint_name"] if fk else None,
            "foreign_table_schema": fk["foreign_table_schema"] if fk else None,
            "foreign_table_name": fk["foreign_table_name"] if fk else None,
            "foreign_column_name": fk["foreign_column_name"] if fk else None,
        }
        detailed_rows.append(row)

        schema_name = col["table_schema"]
        table_name = col["table_name"]

        if table_name not in structure[schema_name]:
            structure[schema_name][table_name] = {
                "table_type": table_type_map.get((schema_name, table_name), "UNKNOWN"),
                "columns": [],
            }

        structure[schema_name][table_name]["columns"].append(
            {
                "column_name": col["column_name"],
                "ordinal_position": col["ordinal_position"],
                "is_nullable": col["is_nullable"],
                "data_type": col["data_type"],
                "udt_name": col["udt_name"],
                "full_type": build_column_type(col),
                "character_maximum_length": col["character_maximum_length"],
                "numeric_precision": col["numeric_precision"],
                "numeric_scale": col["numeric_scale"],
                "datetime_precision": col["datetime_precision"],
                "column_default": col["column_default"],
                "is_pk": bool(pk),
                "is_fk": bool(fk),
                "fk_target_schema": fk["foreign_table_schema"] if fk else None,
                "fk_target_table": fk["foreign_table_name"] if fk else None,
                "fk_target_column": fk["foreign_column_name"] if fk else None,
            }
        )

    csv_path = OUTPUT_DIR / "db_columns_detail.csv"
    json_path = OUTPUT_DIR / "db_structure.json"
    txt_path = OUTPUT_DIR / "db_structure_summary.txt"

    export_csv(detailed_rows, csv_path)
    export_json(structure, json_path)
    export_txt_summary(structure, indexes_map, txt_path)

    print("=" * 80)
    print("INSPECCIÓN FINALIZADA")
    print("=" * 80)
    print(f"CSV detalle : {csv_path}")
    print(f"JSON        : {json_path}")
    print(f"TXT resumen : {txt_path}")
    print("=" * 80)


if __name__ == "__main__":
    main()