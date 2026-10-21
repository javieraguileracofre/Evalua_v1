# core/domain_errors.py
# -*- coding: utf-8 -*-
"""Errores de negocio que la UI puede mostrar. Siguen siendo ValueError."""
from __future__ import annotations


class DomainError(ValueError):
    """Fallo de regla de negocio, con mensaje apto para el usuario."""

    code = "domain"
    hint = ""


class PeriodoCerradoError(DomainError):
    code = "periodo_cerrado"
    hint = "Revise Cierre mensual y use una fecha de un periodo abierto."


class AsientoDescuadradoError(DomainError):
    code = "asiento_descuadrado"
    hint = "El debe y el haber de la cabecera tienen que coincidir."


class AsientoInmutableError(DomainError):
    code = "asiento_inmutable"
    hint = "Registre una reversión si necesita corregir el movimiento."


class StockInsuficienteError(DomainError):
    code = "stock_insuficiente"
    hint = "Ajuste la cantidad o revise el stock del producto."
