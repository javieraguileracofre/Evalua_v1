# services/remuneraciones/banco_transfer_csv.py
# -*- coding: utf-8 -*-
"""
Exportación CSV de transferencias / nómina para distintos bancos (mix).

Cada preset es una *aproximación* a lo que suelen pedir los portales de pago masivo;
**debe validarse** con la plantilla oficial del banco del cliente (cambian con el tiempo).

Formatos soportados (parámetro ``formato`` en la URL):
- ``generico``: columnas amplias, monto con decimales (coma).
- ``pesos_cl``: igual estructura que genérico, monto en pesos enteros.
- ``banco_estado``: columnas orientadas a abono masivo / Cuenta RUT (cuenta = RUT sin DV si no hay número de cuenta).
- ``bci``, ``banco_chile``: RUT + datos de cuenta del trabajador + monto (pesos enteros).
- ``santander``, ``scotiabank``, ``security``: mismo cuerpo que ``bci`` (cabecera distinta para identificar el archivo).
"""
from __future__ import annotations

import csv
from decimal import ROUND_HALF_UP, Decimal
from io import StringIO
from typing import TYPE_CHECKING, Callable

if TYPE_CHECKING:
    from models.remuneraciones.models import PeriodoRemuneracion

FORMATOS_NOMINA: tuple[str, ...] = (
    "generico",
    "pesos_cl",
    "banco_estado",
    "bci",
    "banco_chile",
    "santander",
    "scotiabank",
    "security",
)


def normalizar_formato_masivo(formato: str) -> str:
    f = (formato or "generico").strip().lower()
    return f if f in FORMATOS_NOMINA else "generico"


def _rut_limpio(rut: str | None) -> str:
    return (rut or "").replace(".", "").strip()


def _rut_cuerpo_dv(rut: str | None) -> tuple[str, str]:
    s = _rut_limpio(rut).upper()
    if "-" in s:
        body, dv = s.rsplit("-", 1)
        return body, dv
    return s, ""


def _monto_decimal_coma(liq: Decimal) -> str:
    return str(liq).replace(".", ",")


def _monto_pesos_enteros(liq: Decimal) -> str:
    return str(int(liq.quantize(Decimal("1"), rounding=ROUND_HALF_UP)))


def _referencia(pr: PeriodoRemuneracion) -> str:
    return f"Nomina {pr.mes:02d}/{pr.anio}"


def _fecha_abono(pr: PeriodoRemuneracion) -> str:
    return str(pr.fecha_fin)


def _iter_filas_nomina(pr: PeriodoRemuneracion):
    for d in sorted(pr.detalles, key=lambda x: (x.empleado.nombre_completo if x.empleado else "")):
        emp = d.empleado
        if not emp:
            continue
        liq = Decimal(str(d.liquido_a_pagar or 0)).quantize(Decimal("0.01"))
        if liq <= 0:
            continue
        yield emp, liq


def _cuenta_abono_banco_estado(emp) -> str:
    """Cuenta destino: número cargado en ficha, o cuerpo del RUT (sin DV) si paga a Cuenta RUT."""
    n = (getattr(emp, "transferencia_numero_cuenta", None) or "").strip()
    if n:
        return n
    body, _ = _rut_cuerpo_dv(emp.rut)
    return body


def _csv_generico_ampliado(pr: PeriodoRemuneracion, *, decimales: bool) -> str:
    sio = StringIO()
    w = csv.writer(sio, delimiter=";")
    w.writerow(
        [
            "RUT",
            "NombreBeneficiario",
            "Monto",
            "BancoCodigo",
            "TipoCuenta",
            "NumeroCuenta",
            "Email",
            "Referencia",
        ]
    )
    ref = _referencia(pr)
    monto_fn = _monto_decimal_coma if decimales else _monto_pesos_enteros
    for emp, liq in _iter_filas_nomina(pr):
        rut = _rut_limpio(emp.rut)
        w.writerow(
            [
                rut,
                (emp.nombre_completo or "").strip(),
                monto_fn(liq),
                (getattr(emp, "transferencia_banco_codigo", None) or "").strip(),
                (getattr(emp, "transferencia_tipo_cuenta", None) or "").strip(),
                (getattr(emp, "transferencia_numero_cuenta", None) or "").strip(),
                (emp.email or "").strip(),
                ref,
            ]
        )
    return "\ufeff" + sio.getvalue()


def _csv_banco_estado(pr: PeriodoRemuneracion) -> str:
    """
    Columnas típicas para revisión / portales que piden RUT, cuenta abono y monto en pesos.
    Validar con Portal de Pagos Instituciones BancoEstado.
    """
    sio = StringIO()
    w = csv.writer(sio, delimiter=";")
    w.writerow(
        [
            "RutBeneficiario",
            "MontoPesos",
            "Nombre",
            "CuentaAbono",
            "Email",
            "Glosa",
            "FechaAbono",
        ]
    )
    ref = _referencia(pr)
    f_abono = _fecha_abono(pr)
    for emp, liq in _iter_filas_nomina(pr):
        rut = _rut_limpio(emp.rut)
        w.writerow(
            [
                rut,
                _monto_pesos_enteros(liq),
                (emp.nombre_completo or "").strip(),
                _cuenta_abono_banco_estado(emp),
                (emp.email or "").strip(),
                ref,
                f_abono,
            ]
        )
    return "\ufeff" + sio.getvalue()


def _csv_bci_estilo(pr: PeriodoRemuneracion, *, titulo_banco: str) -> str:
    """Estructura tipo BCI / bancos con RUT, banco, tipo, cuenta, monto entero, glosa."""
    sio = StringIO()
    w = csv.writer(sio, delimiter=";")
    w.writerow(
        [
            "BancoOrigenArchivo",
            "RutBeneficiario",
            "NombreBeneficiario",
            "CodigoBancoDestino",
            "TipoCuentaDestino",
            "NumeroCuentaDestino",
            "MontoPesos",
            "GlosaPago",
        ]
    )
    ref = _referencia(pr)
    for emp, liq in _iter_filas_nomina(pr):
        rut = _rut_limpio(emp.rut)
        w.writerow(
            [
                titulo_banco,
                rut,
                (emp.nombre_completo or "").strip(),
                (getattr(emp, "transferencia_banco_codigo", None) or "").strip(),
                (getattr(emp, "transferencia_tipo_cuenta", None) or "").strip(),
                (getattr(emp, "transferencia_numero_cuenta", None) or "").strip(),
                _monto_pesos_enteros(liq),
                ref,
            ]
        )
    return "\ufeff" + sio.getvalue()


def _csv_banco_chile(pr: PeriodoRemuneracion) -> str:
    sio = StringIO()
    w = csv.writer(sio, delimiter=";")
    w.writerow(
        [
            "Rut",
            "Nombre",
            "BancoDestino",
            "TipoCuenta",
            "CuentaDestino",
            "MontoPesos",
            "ConceptoPago",
        ]
    )
    ref = _referencia(pr)
    for emp, liq in _iter_filas_nomina(pr):
        rut = _rut_limpio(emp.rut)
        w.writerow(
            [
                rut,
                (emp.nombre_completo or "").strip(),
                (getattr(emp, "transferencia_banco_codigo", None) or "").strip(),
                (getattr(emp, "transferencia_tipo_cuenta", None) or "").strip(),
                (getattr(emp, "transferencia_numero_cuenta", None) or "").strip(),
                _monto_pesos_enteros(liq),
                ref,
            ]
        )
    return "\ufeff" + sio.getvalue()


def exportar_nomina_transfer_csv(pr: PeriodoRemuneracion, formato: str) -> str:
    fmt = normalizar_formato_masivo(formato)
    builders: dict[str, Callable[[PeriodoRemuneracion], str]] = {
        "generico": lambda p: _csv_generico_ampliado(p, decimales=True),
        "pesos_cl": lambda p: _csv_generico_ampliado(p, decimales=False),
        "banco_estado": _csv_banco_estado,
        "bci": lambda p: _csv_bci_estilo(p, titulo_banco="BCI"),
        "banco_chile": _csv_banco_chile,
        "santander": lambda p: _csv_bci_estilo(p, titulo_banco="SANTANDER"),
        "scotiabank": lambda p: _csv_bci_estilo(p, titulo_banco="SCOTIABANK"),
        "security": lambda p: _csv_bci_estilo(p, titulo_banco="SECURITY"),
    }
    return builders[fmt](pr)


def monto_csv_generico(liq: Decimal) -> str:
    """Expuesto para tests y utilidades; mismo criterio que columna Monto en ``generico``."""
    return _monto_decimal_coma(liq)


def monto_csv_pesos_cl(liq: Decimal) -> str:
    """Monto en pesos chilenos sin decimales (redondeo half-up)."""
    return _monto_pesos_enteros(liq)
