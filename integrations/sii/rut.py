# integrations/sii/rut.py
# -*- coding: utf-8 -*-
"""Normalización de RUT chileno. No valida contra el SII."""
from __future__ import annotations


def normalizar_rut(value: object) -> str:
    raw = str(value or "").strip().upper().replace(".", "").replace(" ", "")
    if not raw:
        return ""
    raw = raw.replace("–", "-")
    if "-" not in raw and len(raw) >= 2:
        raw = f"{raw[:-1]}-{raw[-1]}"
    cuerpo, _, dv = raw.partition("-")
    cuerpo = cuerpo.lstrip("0") or "0"
    return f"{cuerpo}-{dv}"


def rut_es_valido(value: object) -> bool:
    rut = normalizar_rut(value)
    if "-" not in rut:
        return False
    cuerpo, dv = rut.split("-", 1)
    if not cuerpo.isdigit() or len(dv) != 1:
        return False
    if dv != "K" and not dv.isdigit():
        return False
    suma = 0
    factor = 2
    for digito in reversed(cuerpo):
        suma += int(digito) * factor
        factor = 2 if factor == 7 else factor + 1
    resto = 11 - (suma % 11)
    if resto == 11:
        esperado = "0"
    elif resto == 10:
        esperado = "K"
    else:
        esperado = str(resto)
    return dv == esperado


def rut_para_formulario(value: object) -> str:
    """Formato visual del login SII: 12.345.678-9."""
    rut = normalizar_rut(value)
    if "-" not in rut:
        return rut
    cuerpo, dv = rut.split("-", 1)
    partes: list[str] = []
    while cuerpo:
        partes.append(cuerpo[-3:])
        cuerpo = cuerpo[:-3]
    return f"{'.'.join(reversed(partes))}-{dv}"


def ruts_coinciden(izquierdo: object, derecho: object) -> bool:
    a = normalizar_rut(izquierdo)
    b = normalizar_rut(derecho)
    return bool(a) and a == b
