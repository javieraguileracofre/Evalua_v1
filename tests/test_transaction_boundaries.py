# tests/test_transaction_boundaries.py
# -*- coding: utf-8 -*-
"""Verifica que integraciones contables no confirmen TX parciales."""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_ventas_integracion_uses_do_commit_false():
    text = (ROOT / "services" / "finanzas" / "integracion_ventas.py").read_text(encoding="utf-8")
    assert text.count("do_commit=False") >= 2
    assert "origen_tipo=\"NOTA_VENTA\"" in text or "origen_tipo='NOTA_VENTA'" in text


def test_inventario_integracion_uses_do_commit_false():
    text = (ROOT / "services" / "finanzas" / "integracion_inventario.py").read_text(encoding="utf-8")
    assert "do_commit=False" in text


def test_pago_cliente_publishes_outbox_before_commit():
    text = (ROOT / "services" / "cobranza" / "pago_service.py").read_text(encoding="utf-8")
    assert "publish_in_transaction" in text
    assert text.index("publish_in_transaction") < text.index("db.commit()")
    assert "flush_outbox_after_commit" in text


def test_venta_pos_publishes_outbox_before_commit():
    text = (ROOT / "services" / "comercial" / "ventas_service.py").read_text(encoding="utf-8")
    assert "publish_in_transaction" in text
    assert "VENTA_CONFIRMADA" in text
    assert "flush_outbox_after_commit" in text
    # crear + actualizar + anular deben publicar (actualizar usa correlation :upd)
    assert text.count("publish_in_transaction") >= 3
    assert "NOTA_VENTA:" in text and ":upd:" in text
    # En actualizar_venta_pos el publish va antes del commit del flujo.
    upd_idx = text.index("def actualizar_venta_pos")
    next_def = text.find("\ndef ", upd_idx + 1)
    block = text[upd_idx:next_def if next_def > 0 else None]
    assert "publish_in_transaction" in block
    assert block.index("publish_in_transaction") < block.index("db.commit()")


def test_manual_entries_module_used_by_ui():
    ui = (ROOT / "routes" / "ui" / "contabilidad.py").read_text(encoding="utf-8")
    assert "registrar_asiento_manual" in ui
    assert "revertir_asiento_manual" in ui
