# integrations/sii/errors.py
# -*- coding: utf-8 -*-
"""Errores de la conexión SII, en lenguaje de usuario y sin secretos."""
from __future__ import annotations


class SiiEtapaError(Exception):
    def __init__(self, etapa: str, detalle: str):
        self.etapa = etapa
        self.detalle = detalle
        super().__init__(detalle)


class SiiCredencialInvalida(SiiEtapaError):
    pass


class SiiIntervencionRequerida(SiiEtapaError):
    pass


class EstructuraInvalida(SiiEtapaError):
    def __init__(self, detalle: str, *, etapa: str = "Validación del archivo"):
        super().__init__(etapa, detalle)


def mensaje_publico(etapa: str, detalle: str) -> str:
    return (
        "No fue posible completar la conexión con el SII.\n\n"
        f"Etapa:\n{etapa}\n\n"
        f"Detalle:\n{detalle}\n\n"
        "No se importaron nuevos documentos."
    )


def scrub(texto: str, secreto: str) -> str:
    limpio = texto or ""
    clave = (secreto or "").strip()
    if clave and clave in limpio:
        limpio = limpio.replace(clave, "***")
    return limpio[:2000]
