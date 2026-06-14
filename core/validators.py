# core/validators.py
# -*- coding: utf-8 -*-
"""Validadores y normalizadores reutilizables (RUT chileno, teléfono, texto)."""
from __future__ import annotations

import re

from pydantic import ValidationError

_RUT_SEPARADO_RE = re.compile(r"^(\d{1,8})-([\dK])$")
_RUT_COMPACTO_RE = re.compile(r"^(\d{7,8})([\dK])$")


def normalizar_texto(value: str | None) -> str | None:
    if value is None:
        return None
    s = value.strip()
    return s or None


def normalizar_rut(rut: str) -> str:
    """Quita puntos/espacios y deja mayúsculas; asegura guión antes del DV."""
    s = (rut or "").strip().upper()
    s = s.replace(".", "").replace(" ", "")
    if not s:
        return ""

    if "-" in s:
        cuerpo, _, dv = s.partition("-")
        cuerpo = cuerpo.lstrip("0") or "0"
        return f"{cuerpo}-{dv}"

    if _RUT_COMPACTO_RE.match(s):
        cuerpo, dv = _RUT_COMPACTO_RE.match(s).groups()  # type: ignore[union-attr]
        cuerpo = cuerpo.lstrip("0") or "0"
        return f"{cuerpo}-{dv}"

    return s


def calcular_dv_rut(cuerpo: str) -> str:
    """Calcula dígito verificador chileno (módulo 11)."""
    suma = 0
    multiplicador = 2
    for digito in reversed(cuerpo):
        suma += int(digito) * multiplicador
        multiplicador += 1
        if multiplicador > 7:
            multiplicador = 2
    resto = 11 - (suma % 11)
    if resto == 11:
        return "0"
    if resto == 10:
        return "K"
    return str(resto)


def validar_rut_chileno(rut: str) -> bool:
    s = normalizar_rut(rut)
    match = _RUT_SEPARADO_RE.match(s)
    if not match:
        return False
    cuerpo, dv = match.groups()
    if not (1 <= len(cuerpo) <= 8):
        return False
    return calcular_dv_rut(cuerpo) == dv


def formatear_rut(rut: str) -> str:
    """Devuelve RUT canónico ``cuerpo-DV`` o lanza ValueError."""
    s = normalizar_rut(rut)
    if not s:
        raise ValueError("El RUT es obligatorio.")
    if not validar_rut_chileno(s):
        raise ValueError(
            "El RUT no es válido. Verifique el número y el dígito verificador "
            "(formato esperado: 12345678-5)."
        )
    match = _RUT_SEPARADO_RE.match(s)
    assert match is not None
    cuerpo, dv = match.groups()
    return f"{cuerpo}-{dv}"


def rut_para_busqueda(rut: str) -> str:
    """Normaliza RUT para búsquedas y unicidad (canónico si es válido)."""
    s = normalizar_rut(rut)
    if validar_rut_chileno(s):
        return formatear_rut(s)
    return s


def normalizar_telefono_chileno(telefono: str | None) -> str | None:
    """
    Valida y normaliza teléfonos chilenos.

    Acepta móvil (9 dígitos), fijo (8 dígitos) o prefijo +56.
    Devuelve formato ``+56XXXXXXXXX`` o None si está vacío.
    """
    s = normalizar_texto(telefono)
    if not s:
        return None

    digits = re.sub(r"\D", "", s)
    if s.startswith("+"):
        if not digits.startswith("56"):
            raise ValueError(
                "El teléfono debe ser chileno (+56) o un número local de 8–9 dígitos."
            )
        local = digits[2:]
    elif digits.startswith("56") and len(digits) >= 11:
        local = digits[2:]
    else:
        local = digits

    if len(local) == 9 and local.startswith("9"):
        return f"+56{local}"
    if len(local) == 8 and local[0] in "234567":
        return f"+56{local}"
    raise ValueError(
        "Teléfono inválido. Use móvil 9 dígitos (9XXXXXXXX) o fijo 8 dígitos "
        "(2XXXXXXX), con o sin prefijo +56."
    )


def form_validation_message(exc: ValidationError, *, prefix: str = "Revise el formulario") -> str:
    """Convierte ValidationError de Pydantic en mensaje apto para el usuario."""
    parts: list[str] = []
    for err in exc.errors()[:8]:
        loc = " → ".join(str(x) for x in err.get("loc", ()) if x != "body")
        msg = str(err.get("msg", ""))
        if loc:
            parts.append(f"{loc}: {msg}")
        elif msg:
            parts.append(msg)
    if not parts:
        return f"{prefix}: datos no válidos."
    return f"{prefix}: " + "; ".join(parts)
