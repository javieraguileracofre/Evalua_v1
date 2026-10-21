# integrations/sii/normalizer.py
# -*- coding: utf-8 -*-
"""Convierte filas del SII al documento interno. No inserta en la base."""
from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal, InvalidOperation

from integrations.sii.errors import EstructuraInvalida
from integrations.sii.parser import TablaSii
from integrations.sii.rut import normalizar_rut
from services.finanzas.documento_tributario import montos_cuadran

_TOL = Decimal("1.00")
_CODIGOS = {
    "30": "FACTURA",
    "32": "FACTURA_EXENTA",
    "33": "FACTURA",
    "34": "FACTURA_EXENTA",
    "35": "BOLETA",
    "38": "BOLETA",
    "39": "BOLETA",
    "41": "BOLETA",
    "43": "OTRO",
    "45": "FACTURA",
    "46": "FACTURA",
    "50": "GUIA",
    "52": "GUIA",
    "55": "NOTA_DEBITO",
    "56": "NOTA_DEBITO",
    "60": "NOTA_CREDITO",
    "61": "NOTA_CREDITO",
    "110": "FACTURA",
    "111": "NOTA_DEBITO",
    "112": "NOTA_CREDITO",
}


@dataclass(frozen=True)
class DocumentoSii:
    direccion: str
    tipo: str
    folio: str
    rut_emisor: str
    rut_receptor: str
    razon_social: str
    fecha_emision: date
    fecha_recepcion: date | None
    neto: Decimal
    iva: Decimal
    exento: Decimal
    otros: Decimal
    total: Decimal
    estado: str
    periodo_anio: int
    periodo_mes: int
    fila: int

    def clave(self) -> tuple[str, str, str, str]:
        return (self.direccion, self.tipo, self.folio, self.rut_emisor)


@dataclass(frozen=True)
class FilaNormalizada:
    fila: int
    documento: DocumentoSii | None
    error: str


def _monto(value: str) -> Decimal:
    raw = (value or "").strip().replace("$", "").replace(" ", "")
    if not raw or raw in {"-", "—"}:
        return Decimal("0.00")
    if "," in raw and "." in raw:
        if raw.rfind(",") > raw.rfind("."):
            raw = raw.replace(".", "").replace(",", ".")
        else:
            raw = raw.replace(",", "")
    elif "," in raw:
        raw = raw.replace(".", "").replace(",", ".")
    elif raw.count(".") > 1:
        raw = raw.replace(".", "")
    elif raw.count(".") == 1:
        izquierda, derecha = raw.split(".")
        if len(derecha) == 3 and izquierda.replace("-", "").isdigit():
            raw = izquierda + derecha
    try:
        return Decimal(raw).quantize(Decimal("0.01"))
    except InvalidOperation as exc:
        raise ValueError(f"Monto no numérico: {value}") from exc


def _fecha(value: str, *, obligatoria: bool) -> date | None:
    raw = (value or "").strip()
    if not raw:
        if obligatoria:
            raise ValueError("Falta la fecha de emisión.")
        return None
    if " " in raw:
        raw = raw.split(" ", 1)[0]
    for formato in ("%d/%m/%Y", "%d-%m-%Y", "%Y-%m-%d", "%d/%m/%y"):
        try:
            return datetime.strptime(raw, formato).date()
        except ValueError:
            continue
    raise ValueError(f"Fecha no reconocida: {value}")


def _tipo(value: str) -> str:
    raw = (value or "").strip()
    if not raw:
        raise ValueError("Falta el tipo de documento.")
    coincidencia = re.match(r"(\d+)", raw)
    if coincidencia:
        codigo = coincidencia.group(1)
        if codigo not in _CODIGOS:
            raise ValueError(f"Tipo de documento SII {codigo} no está mapeado al libro interno.")
        return _CODIGOS[codigo]
    bajo = raw.lower()
    if "credito" in bajo or "crédito" in bajo:
        return "NOTA_CREDITO"
    if "debito" in bajo or "débito" in bajo:
        return "NOTA_DEBITO"
    if "boleta" in bajo:
        return "BOLETA"
    if "guia" in bajo or "guía" in bajo:
        return "GUIA"
    if "exent" in bajo:
        return "FACTURA_EXENTA"
    if "factura" in bajo:
        return "FACTURA"
    raise ValueError(f"Tipo de documento SII «{raw}» no está mapeado al libro interno.")


def _folio(value: str) -> str:
    raw = (value or "").strip()
    if not raw:
        raise ValueError("Falta el folio.")
    if raw.isdigit():
        raw = str(int(raw))
    return raw[:40]


def _celda(fila: dict[str, str], nombre: str) -> str:
    return (fila.get(nombre) or "").strip()


def normalizar_tabla(
    tabla: TablaSii,
    *,
    direccion: str,
    rut_empresa: str,
    anio: int,
    mes: int,
) -> list[FilaNormalizada]:
    lado = (direccion or "").strip().upper()
    if lado not in {"EMITIDO", "RECIBIDO"}:
        raise EstructuraInvalida("La dirección del libro debe ser EMITIDO o RECIBIDO.")
    empresa = normalizar_rut(rut_empresa)
    if not empresa:
        raise EstructuraInvalida("La empresa activa no tiene RUT para asignar los documentos.")
    contraparte = "rut_proveedor" if lado == "RECIBIDO" else "rut_cliente"
    if contraparte not in tabla.columnas:
        etiqueta = "RUT Proveedor" if lado == "RECIBIDO" else "Rut cliente"
        raise EstructuraInvalida(f"El archivo no trae la columna {etiqueta}.", etapa="Validación del archivo")
    salida: list[FilaNormalizada] = []
    for fila in tabla.filas:
        numero = int(fila.get("_fila") or 0)
        try:
            documento = _fila(fila, lado=lado, empresa=empresa, anio=anio, mes=mes, numero=numero)
        except ValueError as exc:
            salida.append(FilaNormalizada(fila=numero, documento=None, error=str(exc)))
            continue
        if documento is None:
            continue
        salida.append(FilaNormalizada(fila=numero, documento=documento, error=""))
    return salida


def _fila(
    fila: dict[str, str],
    *,
    lado: str,
    empresa: str,
    anio: int,
    mes: int,
    numero: int,
) -> DocumentoSii | None:
    tipo_raw = _celda(fila, "tipo_doc")
    folio_raw = _celda(fila, "folio")
    rut_raw = _celda(fila, "rut_proveedor" if lado == "RECIBIDO" else "rut_cliente")
    if not tipo_raw and not folio_raw and not rut_raw:
        return None
    if tipo_raw.lower() in {"total", "totales"}:
        return None
    tipo = _tipo(tipo_raw)
    folio = _folio(folio_raw)
    contraparte = normalizar_rut(rut_raw)
    if not contraparte:
        raise ValueError("Falta el RUT de la contraparte.")
    if lado == "RECIBIDO":
        rut_emisor, rut_receptor = contraparte, empresa
    else:
        rut_emisor, rut_receptor = empresa, contraparte
    neto = _monto(_celda(fila, "neto")) + _monto(_celda(fila, "neto_af"))
    exento = _monto(_celda(fila, "exento"))
    if _celda(fila, "iva"):
        iva = _monto(_celda(fila, "iva"))
    else:
        iva = _monto(_celda(fila, "iva_rec")) + _monto(_celda(fila, "iva_no_rec"))
    iva += _monto(_celda(fila, "iva_af")) + _monto(_celda(fila, "iva_uso"))
    otros = _monto(_celda(fila, "otro"))
    total_raw = _celda(fila, "total")
    total = _monto(total_raw) if total_raw else (neto + exento + iva + otros).quantize(Decimal("0.01"))
    if not montos_cuadran(neto, iva, total, exento=exento, otros=otros, tolerancia=_TOL):
        raise ValueError("Los montos no cuadran: neto + exento + IVA + otros debe igualar el total.")
    return DocumentoSii(
        direccion=lado,
        tipo=tipo,
        folio=folio,
        rut_emisor=rut_emisor,
        rut_receptor=rut_receptor,
        razon_social=_celda(fila, "razon")[:180],
        fecha_emision=_fecha(_celda(fila, "fecha_emision"), obligatoria=True),  # type: ignore[arg-type]
        fecha_recepcion=_fecha(_celda(fila, "fecha_recepcion"), obligatoria=False),
        neto=neto,
        iva=iva,
        exento=exento,
        otros=otros,
        total=total,
        estado=_celda(fila, "estado")[:40],
        periodo_anio=int(anio),
        periodo_mes=int(mes),
        fila=numero,
    )
