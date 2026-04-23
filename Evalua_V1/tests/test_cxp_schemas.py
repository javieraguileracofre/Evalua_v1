# tests/test_cxp_schemas.py
# -*- coding: utf-8 -*-
"""Validaciones de esquemas Cuentas por Pagar (reglas de negocio en Pydantic)."""
from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest
from pydantic import ValidationError

from schemas.finanzas.cuentas_por_pagar import (
    DocumentoCreate,
    DocumentoDetalleCreate,
    PagoAplicacionCreate,
    PagoCreate,
)


def _detalle() -> DocumentoDetalleCreate:
    return DocumentoDetalleCreate(
        descripcion="Línea 1",
        cantidad=Decimal("2"),
        precio_unitario=Decimal("100"),
        descuento=Decimal("0"),
    )


def test_documento_create_fechas_coherentes() -> None:
    base = {
        "proveedor_id": 1,
        "tipo": "FACTURA",
        "folio": "F-1",
        "fecha_emision": date(2024, 1, 10),
        "fecha_vencimiento": date(2024, 2, 10),
        "moneda": "CLP",
        "tipo_cambio": Decimal("1"),
        "es_exento": "NO",
        "detalles": [_detalle()],
    }
    DocumentoCreate(**base)
    with pytest.raises(ValidationError):
        DocumentoCreate(
            **{**base, "fecha_vencimiento": date(2024, 1, 5)},
        )


def test_documento_create_sin_detalle_falla() -> None:
    with pytest.raises(ValidationError):
        DocumentoCreate(
            proveedor_id=1,
            tipo="FACTURA",
            folio="X",
            fecha_emision=date(2024, 1, 1),
            fecha_vencimiento=date(2024, 1, 2),
            detalles=[],
        )


def test_documento_detalle_cantidad_positiva() -> None:
    with pytest.raises(ValidationError):
        DocumentoDetalleCreate(
            descripcion="x",
            cantidad=Decimal("0"),
            precio_unitario=Decimal("1"),
        )


def test_pago_create_requiere_aplicaciones() -> None:
    with pytest.raises(ValidationError):
        PagoCreate(
            proveedor_id=1,
            fecha_pago=date(2024, 1, 1),
            medio_pago="TRANSFERENCIA",
            aplicaciones=[],
        )


def test_pago_create_total_positivo() -> None:
    p = PagoCreate(
        proveedor_id=1,
        fecha_pago=date(2024, 1, 1),
        medio_pago="TRANSFERENCIA",
        aplicaciones=[
            PagoAplicacionCreate(documento_id=10, monto_aplicado=Decimal("150.50")),
        ],
    )
    assert p.aplicaciones[0].monto_aplicado == Decimal("150.50")


def test_pago_aplicacion_monto_positivo() -> None:
    with pytest.raises(ValidationError):
        PagoAplicacionCreate(documento_id=1, monto_aplicado=Decimal("0"))


def test_documento_es_exento_normalizado() -> None:
    d = DocumentoCreate(
        proveedor_id=1,
        tipo="BOLETA",
        folio="B-1",
        fecha_emision=date(2024, 1, 1),
        fecha_vencimiento=date(2024, 1, 31),
        es_exento="si",
        detalles=[_detalle()],
    )
    assert d.es_exento == "SI"
