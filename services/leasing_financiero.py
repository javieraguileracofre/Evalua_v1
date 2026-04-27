# services/leasing_financiero.py
# -*- coding: utf-8 -*-
from __future__ import annotations

from datetime import date
from decimal import Decimal, ROUND_HALF_UP, InvalidOperation
from typing import TYPE_CHECKING, List, Optional

from schemas.comercial.leasing_amortizacion import AmortizacionCuota

if TYPE_CHECKING:
    from models.comercial.leasing_financiero_cotizacion import LeasingFinancieroCotizacion

# Límite contractual razonable (evita overflow en fechas: año máximo 9999 en datetime.date).
MAX_PLAZO_MESES = 1200


def _int_meses(valor: object, etiqueta: str, *, minimo: int, maximo: int) -> int:
    if isinstance(valor, bool):
        raise ValueError(f"{etiqueta} no es válido.")
    if valor is None:
        raise ValueError(f"{etiqueta} es requerido.")
    if isinstance(valor, int):
        n = valor
    else:
        try:
            n = int(Decimal(str(valor)))
        except (InvalidOperation, ValueError, TypeError, ArithmeticError) as exc:
            raise ValueError(f"{etiqueta} debe ser un número entero válido.") from exc
    if n < minimo:
        raise ValueError(f"{etiqueta} debe ser mayor o igual a {minimo}.")
    if n > maximo:
        raise ValueError(f"{etiqueta} excede el máximo permitido ({maximo} meses). Revise el dato guardado.")
    return n


def _sumar_meses(fecha: date, meses: int) -> date:
    if fecha is None:
        raise ValueError("fecha_inicio es requerida para calcular fechas de cuotas.")

    if isinstance(meses, bool):
        raise ValueError("El desplazamiento en meses no es válido.")
    meses = int(meses)
    if meses < 0:
        raise ValueError("El desplazamiento en meses no puede ser negativo.")

    year = fecha.year + (fecha.month - 1 + meses) // 12
    month = (fecha.month - 1 + meses) % 12 + 1
    day = fecha.day

    dias_mes = [
        31,
        29 if (year % 4 == 0 and (year % 100 != 0 or year % 400 == 0)) else 28,
        31,
        30,
        31,
        30,
        31,
        31,
        30,
        31,
        30,
        31,
    ]
    max_day = dias_mes[month - 1]
    if day > max_day:
        day = max_day

    try:
        return date(year, month, day)
    except ValueError as exc:
        raise ValueError(
            "Las fechas de la tabla de amortización salen del rango permitido. "
            "Revise plazo, períodos de gracia y fecha de inicio."
        ) from exc


def _q(v: Decimal | float | int) -> Decimal:
    d = Decimal(str(v))
    return d.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def _q4(v: Decimal | float | int) -> Decimal:
    d = Decimal(str(v))
    return d.quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP)


def calcular_tabla_amortizacion(cotizacion: "LeasingFinancieroCotizacion") -> List[AmortizacionCuota]:
    """
    Tabla de amortización leasing financiero (tasa nominal anual / 12, cuotas mensuales).
    """
    if cotizacion.plazo is None:
        raise ValueError("La cotización debe tener un plazo > 0.")

    monto_base = cotizacion.monto_financiado or cotizacion.valor_neto or cotizacion.monto
    if not monto_base or monto_base <= 0:
        raise ValueError("La cotización no tiene un monto financiado válido.")

    saldo = _q(monto_base)

    tasa_anual = Decimal(str(cotizacion.tasa)) if cotizacion.tasa is not None else Decimal("0")
    i = _q4(tasa_anual / Decimal("12")) if tasa_anual > 0 else Decimal("0")

    total_periodos = _int_meses(
        cotizacion.plazo,
        "El plazo",
        minimo=1,
        maximo=MAX_PLAZO_MESES,
    )
    periodos_gracia = _int_meses(
        cotizacion.periodos_gracia if cotizacion.periodos_gracia is not None else 0,
        "Los períodos de gracia",
        minimo=0,
        maximo=MAX_PLAZO_MESES,
    )

    residual = _q(cotizacion.opcion_compra or 0)
    if residual < 0:
        raise ValueError("La opción de compra no puede ser negativa.")
    if residual >= saldo:
        raise ValueError("La opción de compra debe ser menor al monto financiado.")

    if total_periodos <= periodos_gracia:
        raise ValueError("El plazo debe ser mayor a los períodos de gracia.")

    tiene_residual = residual > 0

    fecha_inicio: Optional[date] = cotizacion.fecha_inicio
    usar_fechas = fecha_inicio is not None

    tabla: List[AmortizacionCuota] = []
    numero_cuota = 0

    for g in range(1, periodos_gracia + 1):
        numero_cuota += 1
        saldo_inicial = saldo

        if i > 0:
            interes = _q(saldo_inicial * i)
        else:
            interes = Decimal("0.00")

        saldo_final = _q(saldo_inicial + interes)
        fecha_cuota = _sumar_meses(fecha_inicio, g) if usar_fechas else None

        tabla.append(
            AmortizacionCuota(
                numero_cuota=numero_cuota,
                fecha_cuota=fecha_cuota,
                saldo_inicial=_q(saldo_inicial),
                cuota=_q(0),
                interes=_q(interes),
                amortizacion=_q(0),
                saldo_final=_q(saldo_final),
                es_gracia=True,
                es_opcion_compra=False,
            )
        )

        saldo = saldo_final

    n_pagos = total_periodos - periodos_gracia
    if i == 0:
        capital_a_amortizar = saldo - residual if tiene_residual else saldo
        cuota_constante = _q(capital_a_amortizar / Decimal(n_pagos))
    else:
        ip1 = Decimal("1") + i
        ip1_pow_N = ip1**n_pagos

        if tiene_residual:
            numerador = saldo * i - residual * i / ip1_pow_N
            denominador = Decimal("1") - (Decimal("1") / ip1_pow_N)
            cuota_constante = _q(numerador / denominador)
        else:
            cuota_constante = _q(saldo * i / (Decimal("1") - (Decimal("1") / ip1_pow_N)))

    for k in range(1, n_pagos + 1):
        numero_cuota += 1
        saldo_inicial = saldo

        if i > 0:
            interes = _q(saldo_inicial * i)
        else:
            interes = Decimal("0.00")

        es_ultima = k == n_pagos
        saldo_objetivo = residual if (es_ultima and tiene_residual) else Decimal("0.00")
        if es_ultima:
            amortizacion = _q(saldo_inicial - saldo_objetivo)
            cuota = _q(interes + amortizacion)
            saldo_final = _q(saldo_objetivo)
        else:
            amortizacion = _q(cuota_constante - interes)
            saldo_final = _q(saldo_inicial - amortizacion)
            cuota = cuota_constante

        if not es_ultima and saldo_final < residual:
            amortizacion = _q(saldo_inicial - residual)
            cuota = _q(interes + amortizacion)
            saldo_final = _q(residual)

        if not tiene_residual and saldo_final < 0:
            amortizacion = _q(saldo_inicial)
            cuota = _q(interes + amortizacion)
            saldo_final = Decimal("0.00")

        if not tiene_residual and es_ultima and saldo_final != Decimal("0.00"):
            amortizacion = _q(saldo_inicial)
            cuota = _q(interes + amortizacion)
            saldo_final = Decimal("0.00")

        if tiene_residual and es_ultima and saldo_final != residual:
            amortizacion = _q(saldo_inicial - residual)
            cuota = _q(interes + amortizacion)
            saldo_final = _q(residual)

        if amortizacion > 0 and cuota <= 0:
            raise ValueError("La renta calculada debe ser mayor a 0.")

        fecha_cuota = _sumar_meses(fecha_inicio, periodos_gracia + k) if usar_fechas else None

        tabla.append(
            AmortizacionCuota(
                numero_cuota=numero_cuota,
                fecha_cuota=fecha_cuota,
                saldo_inicial=_q(saldo_inicial),
                cuota=_q(cuota),
                interes=_q(interes),
                amortizacion=_q(amortizacion),
                saldo_final=_q(saldo_final),
                es_gracia=False,
                es_opcion_compra=False,
            )
        )

        saldo = saldo_final

    if tiene_residual:
        numero_cuota += 1
        fecha_opcion = _sumar_meses(fecha_inicio, total_periodos + 1) if usar_fechas else None

        tabla.append(
            AmortizacionCuota(
                numero_cuota=numero_cuota,
                fecha_cuota=fecha_opcion,
                saldo_inicial=_q(saldo),
                cuota=_q(residual),
                interes=_q(0),
                amortizacion=_q(residual),
                saldo_final=_q(0),
                es_gracia=False,
                es_opcion_compra=True,
            )
        )

    return tabla
