# integrations/sii/auth_result.py
# -*- coding: utf-8 -*-
"""Clasifica el resultado del login sin leer ni registrar la clave."""
from __future__ import annotations

MARCADORES_INTERVENCION = (
    "captcha",
    "recaptcha",
    "hcaptcha",
    "no es un robot",
    "clave única",
    "clave unica",
    "código de verificación",
    "codigo de verificacion",
    "segundo factor",
    "verificación en dos pasos",
    "verificacion en dos pasos",
    "autenticación adicional",
    "autenticacion adicional",
)

MARCADORES_CREDENCIAL = (
    "no es correcta",
    "es incorrecta",
    "clave incorrecta",
    "datos ingresados no son correctos",
    "rut incorrecto",
    "usuario o clave",
    "bloquead",
)


def frase_login(texto: str) -> str:
    """La frase del SII. Ignora el pie que siempre menciona Clave Tributaria."""
    for linea in (texto or "").splitlines():
        limpia = " ".join(linea.split())
        if not limpia:
            continue
        bajo = limpia.lower()
        if "codigo de este mensaje" in bajo or "código de este mensaje" in bajo:
            continue
        if any(marca in bajo for marca in (*MARCADORES_INTERVENCION, *MARCADORES_CREDENCIAL)):
            return limpia[:400]
    return ""


def clasificar_resultado_login(*, url: str, texto: str, tiene_cookie_rut: bool) -> str:
    """Devuelve ok, credencial, intervencion o desconocido."""
    del url
    if tiene_cookie_rut:
        return "ok"
    bajo = (texto or "").lower()
    if any(marca in bajo for marca in MARCADORES_INTERVENCION):
        return "intervencion"
    if any(marca in bajo for marca in MARCADORES_CREDENCIAL):
        return "credencial"
    return "desconocido"
