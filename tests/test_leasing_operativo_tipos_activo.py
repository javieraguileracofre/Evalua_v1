# tests/test_leasing_operativo_tipos_activo.py
# -*- coding: utf-8 -*-
from decimal import Decimal

import pytest

from crud.leasing_operativo.crud import _normalizar_codigo_tipo, upsert_tipo_activo


def test_normalizar_codigo_tipo():
    assert _normalizar_codigo_tipo("camioneta liviana") == "CAMIONETA_LIVIANA"
    assert _normalizar_codigo_tipo("  Equipo-IT  ") == "EQUIPO_IT"
    assert _normalizar_codigo_tipo("a" * 50) == ("A" * 40)


def test_upsert_tipo_activo_valida_residual(monkeypatch):
    class _FakeDB:
        def get(self, *_a, **_k):
            return None

        def scalars(self, *_a, **_k):
            class _R:
                def first(self):
                    return None

            return _R()

        def add(self, *_a, **_k):
            return None

        def commit(self):
            return None

        def refresh(self, row):
            row.id = 1

    monkeypatch.setattr(
        "crud.leasing_operativo.crud.asegurar_parametros_tipo_default",
        lambda _db: 0,
    )
    with pytest.raises(ValueError, match="Residual base"):
        upsert_tipo_activo(
            _FakeDB(),
            tipo_id=None,
            codigo="TEST",
            nombre="Test",
            sector="X",
            residual_base_pct=Decimal("50"),
            residual_max_pct=Decimal("40"),
            liquidez_factor=Decimal("1"),
            obsolescencia_factor=Decimal("1"),
            desgaste_km_factor=Decimal("0.0001"),
            desgaste_hora_factor=Decimal("0.0005"),
            haircut_residual_pct=Decimal("5"),
        )
