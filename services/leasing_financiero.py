# services/leasing_financiero.py
# -*- coding: utf-8 -*-
from __future__ import annotations

from datetime import date
from decimal import Decimal, ROUND_HALF_UP, InvalidOperation
from typing import TYPE_CHECKING, List, Optional

from schemas.comercial.leasing_amortizacion import AmortizacionCuota
from schemas.comercial.leasing_cotizacion import LeasingSimulacionInput, LeasingSimulacionResumen

if TYPE_CHECKING:
    from models.comercial.leasing_financiero_cotizacion import LeasingFinancieroCotizacion

# Límite contractual razonable (evita overflow en fechas: año máximo 9999 en datetime.date).
MAX_PLAZO_MESES = 1200

PERIODICIDADES_LF = frozenset({"MENSUAL", "TRIMESTRAL", "SEMESTRAL", "ANUAL"})
PERIODICIDAD_MESES = {
    "MENSUAL": 1,
    "TRIMESTRAL": 3,
    "SEMESTRAL": 6,
    "ANUAL": 12,
}
PERIODICIDAD_PERIODOS_ANUAL = {
    "MENSUAL": 12,
    "TRIMESTRAL": 4,
    "SEMESTRAL": 2,
    "ANUAL": 1,
}


def normalizar_periodicidad(valor: str | None) -> str:
    p = (valor or "MENSUAL").strip().upper()
    if p not in PERIODICIDADES_LF:
        raise ValueError("Periodicidad inválida. Use MENSUAL, TRIMESTRAL, SEMESTRAL o ANUAL.")
    return p


def _meses_por_periodo(periodicidad: str) -> int:
    return PERIODICIDAD_MESES[normalizar_periodicidad(periodicidad)]


def _periodos_anuales(periodicidad: str) -> int:
    return PERIODICIDAD_PERIODOS_ANUAL[normalizar_periodicidad(periodicidad)]


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


def normalizar_tasa_anual(tasa: Decimal | float | int | None) -> Decimal | None:
    """Acepta tasa decimal (0,12) o porcentaje (12)."""
    if tasa is None:
        return None
    t = Decimal(str(tasa))
    if t > Decimal("1"):
        t = t / Decimal("100")
    if t < Decimal("-0.99"):
        raise ValueError("La tasa nominal anual no puede ser inferior a -99%.")
    return _q4(t)


def calcular_comision_apertura(
    base: Decimal | None,
    tipo: str | None,
    valor: Decimal | None,
) -> Decimal:
    """Comisión de apertura sobre base (valor neto o monto financiado base)."""
    if not base or base <= 0 or not tipo or not valor or valor <= 0:
        return Decimal("0.00")
    tipo_norm = str(tipo).strip().upper()
    if tipo_norm == "PORCENTAJE":
        pct = valor / Decimal("100") if valor > Decimal("1") else valor
        if pct > Decimal("1"):
            raise ValueError("El porcentaje de comisión no puede superar 100%.")
        return _q(base * pct)
    if tipo_norm == "MONTO":
        return _q(valor)
    return Decimal("0.00")


def calcular_pago_inicial(
    valor_neto: Decimal | None,
    tipo: str | None,
    valor: Decimal | None,
) -> Decimal:
    if not valor_neto or valor_neto <= 0 or not tipo or not valor or valor <= 0:
        return Decimal("0.00")
    tipo_norm = str(tipo).strip().upper()
    if tipo_norm == "PORCENTAJE":
        pct = valor / Decimal("100") if valor > Decimal("1") else valor
        if pct > Decimal("1"):
            raise ValueError("El porcentaje de pago inicial no puede superar 100%.")
        return _q(valor_neto * pct)
    if tipo_norm == "MONTO":
        if valor > valor_neto:
            raise ValueError("El pago inicial no puede superar el valor neto de la operación.")
        return _q(valor)
    return Decimal("0.00")


def _convertir_uf_a_moneda(
    moneda: str,
    monto_uf: Decimal | None,
    *,
    uf_valor: Decimal | None,
    dolar_valor: Decimal | None,
) -> Decimal:
    if not monto_uf or monto_uf <= 0:
        return Decimal("0.00")
    m = (moneda or "CLP").strip().upper()
    if m == "UF":
        return _q4(monto_uf)
    if not uf_valor or uf_valor <= 0:
        return Decimal("0.00")
    clp = _q(monto_uf * uf_valor)
    if m == "CLP":
        return clp
    if m == "USD":
        if not dolar_valor or dolar_valor <= 0:
            return Decimal("0.00")
        return _q(clp / dolar_valor)
    return Decimal("0.00")


def _convertir_clp_a_moneda(
    moneda: str,
    monto_clp: Decimal | None,
    *,
    uf_valor: Decimal | None,
    dolar_valor: Decimal | None,
) -> Decimal:
    if not monto_clp or monto_clp <= 0:
        return Decimal("0.00")
    m = (moneda or "CLP").strip().upper()
    if m == "CLP":
        return _q(monto_clp)
    if m == "UF":
        if not uf_valor or uf_valor <= 0:
            return Decimal("0.00")
        return _q(monto_clp / uf_valor)
    if m == "USD":
        if not dolar_valor or dolar_valor <= 0:
            return Decimal("0.00")
        return _q(monto_clp / dolar_valor)
    return Decimal("0.00")


def calcular_monto_financiado(
    *,
    moneda: str,
    valor_neto: Decimal | None,
    pago_inicial_tipo: str | None,
    pago_inicial_valor: Decimal | None,
    financia_seguro: bool,
    seguro_monto_uf: Decimal | None,
    otros_montos_pesos: Decimal | None,
    uf_valor: Decimal | None,
    dolar_valor: Decimal | None,
    comision_apertura_tipo: str | None = None,
    comision_apertura: Decimal | None = None,
    financia_comision: bool = False,
    gastos_operacionales: Decimal | None = None,
) -> tuple[Decimal, Decimal, Decimal, Decimal]:
    """
    Deriva monto financiado desde valor neto, pie, seguro y otros cargos.
    Retorna (monto_financiado, pago_inicial, seguro_financiado, otros_montos).
    """
    pago_inicial = calcular_pago_inicial(valor_neto, pago_inicial_tipo, pago_inicial_valor)
    base = _q((valor_neto or Decimal("0")) - pago_inicial)
    if base < 0:
        raise ValueError("El pago inicial supera el valor neto de la operación.")

    seguro = Decimal("0.00")
    if financia_seguro:
        seguro = _convertir_uf_a_moneda(
            moneda,
            seguro_monto_uf,
            uf_valor=uf_valor,
            dolar_valor=dolar_valor,
        )
    otros = _convertir_clp_a_moneda(
        moneda,
        otros_montos_pesos,
        uf_valor=uf_valor,
        dolar_valor=dolar_valor,
    )
    gastos = _convertir_clp_a_moneda(
        moneda,
        gastos_operacionales,
        uf_valor=uf_valor,
        dolar_valor=dolar_valor,
    )
    comision = Decimal("0.00")
    if financia_comision:
        comision = calcular_comision_apertura(valor_neto, comision_apertura_tipo, comision_apertura)
    return _q(base + seguro + otros + gastos + comision), pago_inicial, seguro, _q(otros + gastos + comision)


def _cotizacion_desde_simulacion(data: LeasingSimulacionInput) -> "LeasingFinancieroCotizacion":
    from types import SimpleNamespace

    tasa = normalizar_tasa_anual(data.tasa)
    monto_fin = data.monto_financiado
    calculado = False
    if monto_fin is None or monto_fin <= 0:
        monto_fin, _, _, _ = calcular_monto_financiado(
            moneda=data.moneda,
            valor_neto=data.valor_neto,
            pago_inicial_tipo=data.pago_inicial_tipo,
            pago_inicial_valor=data.pago_inicial_valor,
            financia_seguro=data.financia_seguro,
            seguro_monto_uf=data.seguro_monto_uf,
            otros_montos_pesos=data.otros_montos_pesos,
            uf_valor=data.uf_valor,
            dolar_valor=data.dolar_valor,
            comision_apertura_tipo=getattr(data, "comision_apertura_tipo", None),
            comision_apertura=getattr(data, "comision_apertura", None),
            financia_comision=getattr(data, "financia_comision", False),
            gastos_operacionales=getattr(data, "gastos_operacionales", None),
        )
        calculado = True
    return SimpleNamespace(
        plazo=data.plazo,
        monto_financiado=monto_fin,
        valor_neto=data.valor_neto,
        monto=None,
        tasa=tasa,
        periodos_gracia=data.periodos_gracia or 0,
        opcion_compra=data.opcion_compra,
        fecha_inicio=data.fecha_inicio,
        fecha_primera_cuota=getattr(data, "fecha_primera_cuota", None),
        periodicidad=getattr(data, "periodicidad", "MENSUAL"),
        moneda=data.moneda,
        _monto_financiado_calculado=calculado,
    )


def calcular_tea_anual(tasa_nominal_anual: Decimal | None) -> Decimal | None:
    if tasa_nominal_anual is None:
        return None
    t = Decimal(str(tasa_nominal_anual))
    if t <= Decimal("-0.99"):
        return None
    if t == 0:
        return Decimal("0.0000")
    im = t / Decimal("12")
    tea = (Decimal("1") + im) ** 12 - Decimal("1")
    return _q4(tea)


def simular_cotizacion(data: LeasingSimulacionInput) -> LeasingSimulacionResumen:
    advertencias: list[str] = []
    moneda = (data.moneda or "CLP").strip().upper()
    tasa = normalizar_tasa_anual(data.tasa)

    pago_inicial = Decimal("0.00")
    seguro = Decimal("0.00")
    otros = Decimal("0.00")
    monto_fin = data.monto_financiado
    calculado = False

    try:
        if monto_fin is None or monto_fin <= 0:
            monto_fin, pago_inicial, seguro, otros = calcular_monto_financiado(
                moneda=moneda,
                valor_neto=data.valor_neto,
                pago_inicial_tipo=data.pago_inicial_tipo,
                pago_inicial_valor=data.pago_inicial_valor,
                financia_seguro=data.financia_seguro,
                seguro_monto_uf=data.seguro_monto_uf,
                otros_montos_pesos=data.otros_montos_pesos,
                uf_valor=data.uf_valor,
                dolar_valor=data.dolar_valor,
                comision_apertura_tipo=getattr(data, "comision_apertura_tipo", None),
                comision_apertura=getattr(data, "comision_apertura", None),
                financia_comision=getattr(data, "financia_comision", False),
                gastos_operacionales=getattr(data, "gastos_operacionales", None),
            )
            calculado = True
        elif data.valor_neto and data.valor_neto > 0:
            pago_inicial = calcular_pago_inicial(
                data.valor_neto,
                data.pago_inicial_tipo,
                data.pago_inicial_valor,
            )
            if data.financia_seguro:
                seguro = _convertir_uf_a_moneda(
                    moneda,
                    data.seguro_monto_uf,
                    uf_valor=data.uf_valor,
                    dolar_valor=data.dolar_valor,
                )
            otros = _convertir_clp_a_moneda(
                moneda,
                data.otros_montos_pesos,
                uf_valor=data.uf_valor,
                dolar_valor=data.dolar_valor,
            )
    except ValueError as exc:
        advertencias.append(str(exc))
        return LeasingSimulacionResumen(
            moneda=moneda,
            valor_neto=data.valor_neto,
            monto_financiado=Decimal("0.00"),
            advertencias=advertencias,
        )

    if not monto_fin or monto_fin <= 0:
        advertencias.append("Informe valor neto o monto financiado para simular.")
        return LeasingSimulacionResumen(
            moneda=moneda,
            valor_neto=data.valor_neto,
            pago_inicial=pago_inicial,
            seguro_financiado=seguro,
            otros_montos=otros,
            monto_financiado=Decimal("0.00"),
            monto_financiado_calculado=calculado,
            advertencias=advertencias,
        )

    if not data.plazo or data.plazo <= 0:
        advertencias.append("Informe plazo en meses para calcular la renta.")
        return LeasingSimulacionResumen(
            moneda=moneda,
            valor_neto=data.valor_neto,
            pago_inicial=pago_inicial,
            seguro_financiado=seguro,
            otros_montos=otros,
            monto_financiado=monto_fin,
            monto_financiado_calculado=calculado,
            tasa_nominal_anual_pct=_q4((tasa or Decimal("0")) * 100) if tasa is not None else None,
            advertencias=advertencias,
        )

    cot = _cotizacion_desde_simulacion(data)
    cot.monto_financiado = monto_fin
    cot.tasa = tasa

    try:
        tabla = calcular_tabla_amortizacion(cot)
    except ValueError as exc:
        advertencias.append(str(exc))
        return LeasingSimulacionResumen(
            moneda=moneda,
            valor_neto=data.valor_neto,
            pago_inicial=pago_inicial,
            seguro_financiado=seguro,
            otros_montos=otros,
            monto_financiado=monto_fin,
            monto_financiado_calculado=calculado,
            tasa_nominal_anual_pct=_q4((tasa or Decimal("0")) * 100) if tasa is not None else None,
            advertencias=advertencias,
        )

    rentas = [c for c in tabla if not c.es_gracia and not c.es_opcion_compra]
    renta_mensual = rentas[0].cuota if rentas else None
    total_interes = sum((c.interes for c in tabla), Decimal("0.00"))
    total_rentas = sum((c.cuota for c in rentas), Decimal("0.00"))
    total_opcion = sum((c.cuota for c in tabla if c.es_opcion_compra), Decimal("0.00"))
    tea = calcular_tea_anual(tasa)

    periodicidad = normalizar_periodicidad(getattr(data, "periodicidad", "MENSUAL"))
    from services.leasing_financiero_metricas import calcular_cae_tir_operacion
    from services.leasing_financiero_tributario import calcular_desglose_tributario

    tir_pct, cae_pct = calcular_cae_tir_operacion(
        pago_inicial=pago_inicial,
        monto_financiado=monto_fin,
        tabla=tabla,
        periodicidad=periodicidad,
    )
    tributario = calcular_desglose_tributario(
        valor_neto=data.valor_neto,
        iva_aplica=getattr(data, "iva_aplica", False),
        iva_tasa=getattr(data, "iva_tasa", None),
        iva_recuperable=getattr(data, "iva_recuperable", True),
        total_intereses=_q(total_interes),
    )

    return LeasingSimulacionResumen(
        moneda=moneda,
        valor_neto=data.valor_neto,
        pago_inicial=pago_inicial,
        seguro_financiado=seguro,
        otros_montos=otros,
        monto_financiado=monto_fin,
        renta_mensual=renta_mensual,
        total_intereses=_q(total_interes),
        total_rentas=_q(total_rentas),
        total_opcion_compra=_q(total_opcion),
        total_desembolso=_q(pago_inicial + total_rentas + total_opcion),
        tasa_nominal_anual_pct=_q4((tasa or Decimal("0")) * 100) if tasa is not None else None,
        tea_anual_pct=_q4(tea * 100) if tea is not None else None,
        tir_anual_pct=tir_pct,
        cae_anual_pct=cae_pct,
        periodicidad=periodicidad,
        desglose_tributario=tributario.model_dump(),
        cuotas_operativas=len(rentas),
        periodos_gracia=int(data.periodos_gracia or 0),
        monto_financiado_calculado=calculado,
        advertencias=advertencias,
    )


def aplicar_parametros_financieros(data: dict) -> dict:
    """Normaliza tasa y deriva monto financiado antes de persistir."""
    if "tasa_fondeo" in data and data["tasa_fondeo"] is not None:
        data["tasa_fondeo"] = normalizar_tasa_anual(data["tasa_fondeo"])
    if "spread_margen" in data and data["spread_margen"] is not None:
        data["spread_margen"] = normalizar_tasa_anual(data["spread_margen"])
    if data.get("tasa_fondeo") is not None and data.get("spread_margen") is not None:
        if data.get("tasa") is None:
            data["tasa"] = _q4(Decimal(str(data["tasa_fondeo"])) + Decimal(str(data["spread_margen"])))
    if "tasa" in data and data["tasa"] is not None:
        data["tasa"] = normalizar_tasa_anual(data["tasa"])
    moneda = str(data.get("moneda") or "CLP").strip().upper()
    monto_fin = data.get("monto_financiado")
    valor_neto = data.get("valor_neto")
    if valor_neto and valor_neto > 0:
        monto_calc, _, _, _ = calcular_monto_financiado(
            moneda=moneda,
            valor_neto=valor_neto,
            pago_inicial_tipo=data.get("pago_inicial_tipo"),
            pago_inicial_valor=data.get("pago_inicial_valor"),
            financia_seguro=bool(data.get("financia_seguro")),
            seguro_monto_uf=data.get("seguro_monto_uf"),
            otros_montos_pesos=data.get("otros_montos_pesos"),
            uf_valor=data.get("uf_valor"),
            dolar_valor=data.get("dolar_valor"),
            comision_apertura_tipo=data.get("comision_apertura_tipo"),
            comision_apertura=data.get("comision_apertura"),
            financia_comision=bool(data.get("financia_comision")),
            gastos_operacionales=data.get("gastos_operacionales"),
        )
        # Recalcular si no hay monto, es <= 0, o es inconsistente vs neto
        # (p.ej. parseo JS Number("250.000")==250 con neto 25.000.000).
        inconsistente = (
            monto_fin is not None
            and monto_fin > 0
            and monto_calc > 0
            and Decimal(str(monto_fin)) < (Decimal(str(valor_neto)) * Decimal("0.001"))
        )
        if monto_fin is None or monto_fin <= 0 or inconsistente:
            data["monto_financiado"] = monto_calc
    if data.get("monto") is None and data.get("monto_financiado"):
        data["monto"] = data["monto_financiado"]
    return data


def calcular_tabla_amortizacion(cotizacion: "LeasingFinancieroCotizacion") -> List[AmortizacionCuota]:
    """
    Tabla de amortización leasing financiero (método francés, cuota fija por periodo).
    Soporta periodicidad MENSUAL/TRIMESTRAL/SEMESTRAL/ANUAL y fecha primera cuota.
    """
    if cotizacion.plazo is None:
        raise ValueError("La cotización debe tener un plazo > 0.")

    monto_base = cotizacion.monto_financiado or cotizacion.valor_neto or cotizacion.monto
    if not monto_base or monto_base <= 0:
        raise ValueError("La cotización no tiene un monto financiado válido.")

    saldo = _q(monto_base)

    tasa_anual = normalizar_tasa_anual(cotizacion.tasa) if cotizacion.tasa is not None else Decimal("0")
    if tasa_anual is None:
        tasa_anual = Decimal("0")

    periodicidad = normalizar_periodicidad(getattr(cotizacion, "periodicidad", "MENSUAL"))
    meses_por_cuota = _meses_por_periodo(periodicidad)
    periodos_anuales = _periodos_anuales(periodicidad)

    plazo_meses = _int_meses(
        cotizacion.plazo,
        "El plazo",
        minimo=1,
        maximo=MAX_PLAZO_MESES,
    )
    if plazo_meses % meses_por_cuota != 0:
        raise ValueError(
            f"El plazo ({plazo_meses} meses) debe ser múltiplo de la periodicidad {periodicidad} "
            f"({meses_por_cuota} meses por cuota)."
        )

    total_periodos = plazo_meses // meses_por_cuota

    gracia_meses = _int_meses(
        cotizacion.periodos_gracia if cotizacion.periodos_gracia is not None else 0,
        "Los períodos de gracia",
        minimo=0,
        maximo=MAX_PLAZO_MESES,
    )
    if gracia_meses % meses_por_cuota != 0:
        raise ValueError(
            f"Los períodos de gracia ({gracia_meses} meses) deben ser múltiplo de {meses_por_cuota} meses."
        )
    periodos_gracia = gracia_meses // meses_por_cuota

    i = _q4(tasa_anual / Decimal(periodos_anuales)) if tasa_anual > 0 else Decimal("0")

    residual = _q(cotizacion.opcion_compra or 0)
    if residual < 0:
        raise ValueError("La opción de compra no puede ser negativa.")
    if residual >= saldo:
        raise ValueError("La opción de compra debe ser menor al monto financiado.")

    if total_periodos <= periodos_gracia:
        raise ValueError("El plazo debe ser mayor a los períodos de gracia.")

    tiene_residual = residual > 0

    fecha_inicio: Optional[date] = cotizacion.fecha_inicio
    fecha_primera: Optional[date] = getattr(cotizacion, "fecha_primera_cuota", None)
    usar_fechas = fecha_inicio is not None or fecha_primera is not None

    def _fecha_cuota(indice_periodo: int) -> Optional[date]:
        """indice_periodo: 1-based desde inicio contractual."""
        if not usar_fechas:
            return None
        if fecha_primera is not None:
            return _sumar_meses(fecha_primera, (indice_periodo - 1) * meses_por_cuota)
        if fecha_inicio is not None:
            return _sumar_meses(fecha_inicio, indice_periodo * meses_por_cuota)
        return None

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
        fecha_cuota = _fecha_cuota(g)

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

        fecha_cuota = _fecha_cuota(periodos_gracia + k)

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
        fecha_opcion = _fecha_cuota(total_periodos + 1)

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
