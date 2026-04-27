# -*- coding: utf-8 -*-
from __future__ import annotations

import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PLAN_SQL = ROOT / "db" / "psql" / "089_fin_plan_cuentas.sql"
CONFIG_SQL_FILES = [
    ROOT / "db" / "psql" / "090_fin_config_contable.sql",
    ROOT / "db" / "psql" / "091_fin_inventario_recepcion_premium.sql",
    ROOT / "db" / "psql" / "092_fin_ventas_costo_venta_premium.sql",
    ROOT / "db" / "psql" / "093_fin_ap_documento_contabilidad.sql",
    ROOT / "db" / "psql" / "097_fin_ap_post_create_all.sql",
    ROOT / "db" / "psql" / "100_comercial_leasing_financiero.sql",
    ROOT / "db" / "psql" / "107_leasing_operativo_contabilidad_base.sql",
]
SUPABASE_SEEDS = [
    ROOT / "db" / "supabase" / "seed_plan_cuentas_supabase.sql",
    ROOT / "db" / "supabase" / "bootstrap_public_schema.sql",
]


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _extract_six_digit_codes(sql: str) -> set[str]:
    return set(re.findall(r"'(\d{6})'", sql))


def _extract_config_account_codes(sql: str) -> set[str]:
    return set(re.findall(r"'(\d{6})'", sql))


def _extract_bootstrap_089_section(sql: str) -> str:
    start_match = re.search(r"-- --- 089_fin_plan_cuentas\.sql.*?---", sql)
    if not start_match:
        return sql
    tail = sql[start_match.start() :]
    next_section = re.search(r"^-- --- \d{3}_", tail, flags=re.MULTILINE)
    if not next_section:
        return tail
    return tail[: next_section.start()]


def test_seed_089_contiene_cuentas_minimas_requeridas() -> None:
    sql = _read(PLAN_SQL)
    required = {
        "100000",
        "200000",
        "300000",
        "400000",
        "500000",
        "600000",
        "110000",
        "120000",
        "210000",
        "220000",
        "310000",
        "410000",
        "420000",
        "510000",
        "610000",
        "620000",
        "630000",
        "110101",
        "110201",
        "110301",
        "110401",
        "110501",
        "110601",
        "113701",
        "113801",
        "120801",
        "120899",
        "210101",
        "210110",
        "210201",
        "210701",
        "310101",
        "310201",
        "310301",
        "410101",
        "410701",
        "510101",
        "610102",
        "610103",
        "610104",
        "610105",
        "620101",
        "610201",
        "630101",
    }
    found = _extract_six_digit_codes(sql)
    missing = required - found
    assert not missing, f"Faltan cuentas requeridas en 089: {sorted(missing)}"


def test_seeds_no_reintroducen_codigos_con_puntos() -> None:
    pattern = re.compile(r"'\d+\.\d+(\.\d+)?'")
    offenders: list[str] = []

    if pattern.search(_read(PLAN_SQL)):
        offenders.append(PLAN_SQL.name)

    supabase_seed = _read(SUPABASE_SEEDS[0])
    if pattern.search(supabase_seed):
        offenders.append(SUPABASE_SEEDS[0].name)

    bootstrap_section = _extract_bootstrap_089_section(_read(SUPABASE_SEEDS[1]))
    if pattern.search(bootstrap_section):
        offenders.append(SUPABASE_SEEDS[1].name)

    assert not offenders, f"Hay codigos con puntos en seeds: {offenders}"


def test_config_contable_referencia_cuentas_existentes_en_seed() -> None:
    plan_codes = _extract_six_digit_codes(_read(PLAN_SQL))
    referenced: set[str] = set()
    for path in CONFIG_SQL_FILES:
        referenced.update(_extract_config_account_codes(_read(path)))
    missing = referenced - plan_codes
    assert not missing, f"Config contable referencia cuentas no definidas en 089: {sorted(missing)}"


def test_eventos_tienen_debe_y_haber_en_config_base() -> None:
    sql = _read(ROOT / "db" / "psql" / "090_fin_config_contable.sql")
    rows = re.findall(r"\('([A-Z0-9_]+)'\s*,\s*'[^']*'\s*,\s*'(DEBE|HABER)'", sql)
    by_event: dict[str, set[str]] = {}
    for event, side in rows:
        by_event.setdefault(event, set()).add(side)
    invalid = [event for event, sides in by_event.items() if not {"DEBE", "HABER"}.issubset(sides)]
    assert not invalid, f"Eventos sin DEBE/HABER en 090: {sorted(invalid)}"

