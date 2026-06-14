# tests/test_cliente_validators.py
# -*- coding: utf-8 -*-
"""Validaciones de clientes: RUT chileno, teléfono y esquemas Pydantic."""
from __future__ import annotations

import pytest
from pydantic import ValidationError

from core.validators import (
    calcular_dv_rut,
    formatear_rut,
    normalizar_telefono_chileno,
    validar_rut_chileno,
)
from schemas.maestros.cliente import ClienteCreate, ClienteUpdate


def test_calcular_dv_rut() -> None:
    assert calcular_dv_rut("11111111") == "1"
    assert calcular_dv_rut("12345678") == "5"


def test_validar_rut_formatos_aceptados() -> None:
    assert validar_rut_chileno("11.111.111-1")
    assert validar_rut_chileno("11111111-1")
    assert validar_rut_chileno("12345678-5")
    assert not validar_rut_chileno("12345678-9")
    assert not validar_rut_chileno("abc")
    assert not validar_rut_chileno("")


def test_formatear_rut_canonico() -> None:
    assert formatear_rut("12.345.678-5") == "12345678-5"
    assert formatear_rut("123456785") == "12345678-5"


def test_formatear_rut_invalido_lanza_error() -> None:
    with pytest.raises(ValueError, match="no es válido"):
        formatear_rut("12345678-9")


def test_normalizar_telefono_chileno() -> None:
    assert normalizar_telefono_chileno("912345678") == "+56912345678"
    assert normalizar_telefono_chileno("+56 9 1234 5678") == "+56912345678"
    assert normalizar_telefono_chileno("22334455") == "+5622334455"
    assert normalizar_telefono_chileno("") is None
    assert normalizar_telefono_chileno(None) is None


def test_normalizar_telefono_invalido() -> None:
    with pytest.raises(ValueError, match="Teléfono inválido"):
        normalizar_telefono_chileno("123")


def test_cliente_create_valido() -> None:
    c = ClienteCreate(
        rut="11.111.111-1",
        razon_social="Empresa Demo SpA",
        telefono="912345678",
        email="contacto@empresa.cl",
    )
    assert c.rut == "11111111-1"
    assert c.telefono == "+56912345678"
    assert c.email == "contacto@empresa.cl"


def test_cliente_create_rut_invalido() -> None:
    with pytest.raises(ValidationError):
        ClienteCreate(rut="12345678-9", razon_social="Empresa Demo SpA")


def test_cliente_create_razon_social_corta() -> None:
    with pytest.raises(ValidationError):
        ClienteCreate(rut="11111111-1", razon_social="A")


def test_cliente_create_email_invalido() -> None:
    with pytest.raises(ValidationError):
        ClienteCreate(
            rut="11111111-1",
            razon_social="Empresa Demo SpA",
            email="no-es-email",
        )


def test_cliente_update_telefono_opcional() -> None:
    u = ClienteUpdate(telefono="")
    assert u.telefono is None


def test_cliente_update_normaliza_email() -> None:
    u = ClienteUpdate(email="Contacto@Empresa.CL")
    assert u.email == "contacto@empresa.cl"
