# -*- coding: utf-8 -*-
from __future__ import annotations

from decimal import Decimal
from unittest.mock import MagicMock, patch

from crud.cobranza.cobranza import resumen_cobranza_general, resumen_cobranza_por_cliente


def test_resumen_general_usa_saldo_consolidado_plan_cuando_gl_supera_subledger():
    mock_db = MagicMock()
    row = {"total_documentos": 2, "total_monto": Decimal("1000"), "total_saldo": Decimal("400")}

    class _M:
        def first(self):
            return row

    mock_exec = MagicMock()
    mock_exec.mappings.return_value = _M()
    mock_db.execute.return_value = mock_exec

    with patch(
        "crud.cobranza.cobranza.saldo_cxc_consolidado_desde_contabilidad",
        return_value=Decimal("250000"),
    ):
        out = resumen_cobranza_general(mock_db)

    assert out["total_saldo_contable"] == Decimal("250000")
    assert out["total_saldo"] == Decimal("250000")
    assert out["total_monto"] == Decimal("250000")
    assert out["total_documentos"] == 2


def test_resumen_por_cliente_agrega_fila_contable_si_hay_delta_gl():
    mock_db = MagicMock()
    rows = [
        {
            "cliente_id": 1,
            "razon_social": "ACME",
            "monto_total": Decimal("100"),
            "saldo_pendiente": Decimal("100"),
            "documentos": 1,
        }
    ]

    class _M:
        def __iter__(self):
            return iter(rows)

    mock_exec = MagicMock()
    mock_exec.mappings.return_value = _M()
    mock_db.execute.return_value = mock_exec

    with patch(
        "crud.cobranza.cobranza.saldo_cxc_consolidado_desde_contabilidad",
        return_value=Decimal("5000"),
    ):
        rows = resumen_cobranza_por_cliente(mock_db)

    assert len(rows) == 2
    assert rows[-1]["cliente_id"] == 0
    assert rows[-1]["saldo_pendiente"] == Decimal("4900")
