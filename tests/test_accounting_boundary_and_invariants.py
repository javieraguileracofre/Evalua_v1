# tests/test_accounting_boundary_and_invariants.py
# -*- coding: utf-8 -*-
"""Frontera contable + invariantes de asiento (sin BD real)."""
from __future__ import annotations

import ast
from decimal import Decimal
from pathlib import Path
from unittest.mock import MagicMock

import pytest

ROOT = Path(__file__).resolve().parents[1]

_ALLOWED_CREAR_ASIENTO_IMPORT = {
    Path("modules/contabilidad/accounting_service.py"),
    Path("crud/finanzas/contabilidad_asientos.py"),
}


def _py_files(rel: str) -> list[Path]:
    base = ROOT / rel
    if not base.exists():
        return []
    return [p for p in base.rglob("*.py") if "__pycache__" not in p.parts]


def _imports_crear_asiento(path: Path) -> bool:
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"))
    except SyntaxError:
        return False
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module == "crud.finanzas.contabilidad_asientos":
            if any(a.name == "crear_asiento" for a in node.names):
                return True
        if isinstance(node, ast.Attribute) and getattr(node, "attr", None) == "crear_asiento":
            # crud_asientos.crear_asiento / contabilidad_asientos.crear_asiento
            val = node.value
            if isinstance(val, ast.Name) and val.id in {"crud_asientos", "contabilidad_asientos", "ca"}:
                return True
    return False


def test_no_direct_crear_asiento_outside_accounting_domain():
    violations: list[str] = []
    for folder in ("routes", "services", "crud", "tools", "modules"):
        for path in _py_files(folder):
            rel = path.relative_to(ROOT)
            if rel in _ALLOWED_CREAR_ASIENTO_IMPORT:
                continue
            if rel == Path("crud/finanzas/contabilidad.py"):
                text = path.read_text(encoding="utf-8")
                assert "accounting_service" in text
                continue
            if _imports_crear_asiento(path):
                violations.append(str(rel))
    assert violations == [], "Consumidores deben usar AccountingService:\n" + "\n".join(violations)


def test_accounting_service_exposes_idempotency_and_reverse():
    from modules.contabilidad import accounting_service

    assert hasattr(accounting_service, "post_entry")
    assert hasattr(accounting_service, "find_by_origen")
    assert hasattr(accounting_service, "reverse_manual_entry")


def test_partida_doble_rechaza_desbalance(monkeypatch: pytest.MonkeyPatch):
    from crud.finanzas import contabilidad_asientos as ca

    monkeypatch.setattr(
        ca,
        "_table_columns",
        lambda *a, **k: {
            "id",
            "fecha",
            "origen_tipo",
            "origen_id",
            "glosa",
            "usuario",
            "moneda",
        },
    )
    monkeypatch.setattr(
        ca,
        "obtener_plan_cuenta_por_codigo",
        lambda db, codigo: MagicMock(
            codigo=codigo, nombre="X", estado="ACTIVO", acepta_movimiento=True
        ),
    )
    monkeypatch.setattr(ca, "obtener_asiento_id_por_origen", lambda *a, **k: None)

    db = MagicMock()
    with pytest.raises(ValueError, match="no cuadra"):
        ca.crear_asiento(
            db,
            fecha=None,
            origen_tipo="MANUAL_AJUSTE",
            origen_id=0,
            glosa="test",
            detalles=[
                {"codigo_cuenta": "1101", "debe": Decimal("100"), "haber": Decimal("0")},
                {"codigo_cuenta": "2101", "debe": Decimal("0"), "haber": Decimal("90")},
            ],
            do_commit=False,
            idempotent=False,
        )


def test_idempotencia_retorna_existente(monkeypatch: pytest.MonkeyPatch):
    from crud.finanzas import contabilidad_asientos as ca

    monkeypatch.setattr(ca, "obtener_asiento_id_por_origen", lambda *a, **k: 77)
    db = MagicMock()
    aid = ca.crear_asiento(
        db,
        fecha=None,
        origen_tipo="AP_DOCUMENTO",
        origen_id=12,
        glosa="dup",
        detalles=[{"codigo_cuenta": "1", "debe": 1, "haber": 0}],
        do_commit=False,
    )
    assert aid == 77


def test_cxp_uses_accounting_service():
    text = (ROOT / "crud" / "finanzas" / "cuentas_por_pagar.py").read_text(encoding="utf-8")
    assert "accounting_service" in text
    assert "from crud.finanzas.contabilidad_asientos import crear_asiento" not in text
