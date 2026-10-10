# modules/credito_cobranzas
"""Contrato público del módulo Crédito y cobranzas.

Agrupa los bounded contexts de crédito/riesgo y cobranza (CxC).
Las rutas UI existentes se mantienen; este paquete es el punto de entrada
progresivo para la UI y servicios cruzados del ciclo crédito → recuperación.
"""
from __future__ import annotations

__all__ = ["credito", "cobranza"]


def __getattr__(name: str):
    if name == "credito":
        from modules import credito as credito_mod

        return credito_mod
    if name == "cobranza":
        from modules import cobranza as cobranza_mod

        return cobranza_mod
    raise AttributeError(name)
