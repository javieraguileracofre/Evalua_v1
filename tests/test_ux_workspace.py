# -*- coding: utf-8 -*-
"""Buscador global y mensajes de dominio con siguiente paso."""
from __future__ import annotations

from core.domain_errors import PeriodoCerradoError
from core.public_errors import public_error_message
from core.request_context import set_request_context
from services.ux.workspace import acciones_visibles


def test_periodo_cerrado_indica_el_siguiente_paso():
    set_request_context(request_id="uxref1")
    msg = public_error_message(PeriodoCerradoError("El período contable 2026-10 está cerrado."))
    assert "Cierre mensual" in msg
    assert "uxref1" in msg


def test_acciones_respetan_modulos_asignados():
    auth = {
        "roles": ["OPERACIONES"],
        "visibleModules": ["PRINCIPAL", "COMERCIAL", "LEASING_OPERATIVO"],
    }
    labels = [accion.label for accion in acciones_visibles(auth)]
    assert "Nueva nota de venta" in labels
    assert "Simular leasing operativo" in labels
    assert "Nueva cotización leasing" not in labels
    assert "Usuarios y roles" not in labels
    assert "Cuentas por pagar" not in labels


def test_acciones_de_admin_incluyen_seguridad():
    labels = [accion.label for accion in acciones_visibles({"roles": ["ADMIN"], "visibleModules": []})]
    assert "Usuarios y roles" in labels
    assert "Nueva nota de venta" in labels


def test_busqueda_de_accion_por_palabras():
    auth = {"roles": ["ADMIN"], "visibleModules": []}
    labels = [accion.label for accion in acciones_visibles(auth, "nueva venta")]
    assert labels == ["Nueva nota de venta"]


def test_resumen_de_notas_conserva_el_total_de_la_consulta():
    from crud.comercial.nota_venta import armar_resumen_notas

    resumen = armar_resumen_notas(10, 2500, 3, 2, 7)
    assert resumen["total"] == 10
    assert resumen["emitidas"] == 5
    assert resumen["pagadas"] == 3
    assert resumen["anuladas"] == 2
    assert resumen["afectas"] == 7
    assert resumen["monto"] == 2500


def test_siguiente_paso_de_nota_de_venta():
    from types import SimpleNamespace

    from routes.ui.ventas_pos import siguiente_paso_nota

    anulada = SimpleNamespace(estado="ANULADA", tipo_pago="CREDITO", cuentas_por_cobrar=[])
    assert siguiente_paso_nota(anulada)["kind"] == "anulada"

    cxc = SimpleNamespace(id=9, estado="PENDIENTE", saldo_pendiente=1500)
    con_saldo = SimpleNamespace(estado="EMITIDA", tipo_pago="CREDITO", cuentas_por_cobrar=[cxc])
    paso = siguiente_paso_nota(con_saldo)
    assert paso["kind"] == "cobrar"
    assert paso["cxc_id"] == 9

    contado = SimpleNamespace(estado="EMITIDA", tipo_pago="CONTADO", cuentas_por_cobrar=[])
    assert siguiente_paso_nota(contado)["kind"] == "ticket"
