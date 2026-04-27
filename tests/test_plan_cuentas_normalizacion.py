# -*- coding: utf-8 -*-
from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from routes.ui import contabilidad as ui_contabilidad
from schemas.finanzas.plan_cuentas import PlanCuentaCreate


ROOT = Path(__file__).resolve().parents[1]
PATCH_114 = ROOT / "db" / "psql" / "114_fin_plan_cuentas_normalizar_codigos.sql"


def test_crear_plan_cuenta_rechaza_codigo_con_puntos() -> None:
    with pytest.raises(ValidationError) as exc:
        PlanCuentaCreate(
            codigo="1.1.01",
            nombre="Caja Legacy",
            nivel=3,
            cuenta_padre_id=None,
            tipo="ACTIVO",
            clasificacion="ACTIVO_CORRIENTE",
            naturaleza="DEUDORA",
            acepta_movimiento=True,
            requiere_centro_costo=False,
            estado="ACTIVO",
            descripcion=None,
        )
    assert "El código de cuenta debe tener 6 dígitos y no debe incluir puntos." in str(exc.value)


def test_crear_plan_cuenta_acepta_codigo_canonico() -> None:
    payload = PlanCuentaCreate(
        codigo="110101",
        nombre="Caja General",
        nivel=3,
        cuenta_padre_id=None,
        tipo="ACTIVO",
        clasificacion="ACTIVO_CORRIENTE",
        naturaleza="DEUDORA",
        acepta_movimiento=True,
        requiere_centro_costo=False,
        estado="ACTIVO",
        descripcion=None,
    )
    assert payload.codigo == "110101"


def test_listado_plan_cuentas_publicado_filtra_activo_por_defecto(monkeypatch) -> None:
    captured: list[dict] = []

    def _fake_listar(_db, **kwargs):
        captured.append(kwargs)
        return []

    def _fake_template(_name, context):
        return context

    monkeypatch.setattr(ui_contabilidad, "guard_finanzas_consulta", lambda _request: None)
    monkeypatch.setattr(ui_contabilidad.crud_plan, "listar_plan_cuentas", _fake_listar)
    monkeypatch.setattr(ui_contabilidad.templates, "TemplateResponse", _fake_template)

    out = ui_contabilidad.contabilidad_plan_cuentas(
        request=SimpleNamespace(),
        q=None,
        tipo=None,
        estado=None,
        solo_movimiento=None,
        msg=None,
        sev="info",
        db=object(),
    )

    assert captured[0]["estado"] == "ACTIVO"
    assert out["estado"] == "ACTIVO"


def test_patch_114_incluye_validacion_cuentas_activas_sin_puntos() -> None:
    sql = PATCH_114.read_text(encoding="utf-8")
    assert "SELECT COUNT(*)" in sql
    assert "FROM fin.plan_cuenta" in sql
    assert "estado = 'ACTIVO'" in sql
    assert "codigo LIKE '%.%'" in sql
