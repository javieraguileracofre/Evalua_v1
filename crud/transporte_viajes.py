# crud/transporte_viajes.py
# -*- coding: utf-8 -*-
"""Hojas de ruta (viajes): CRUD, métricas y tablero comparativo."""
from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timedelta
from decimal import Decimal, ROUND_HALF_UP
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from models.fondos_rendir.fondo_rendir import FondoRendir
from models.maestros.cliente import Cliente
from models.transporte.viaje import ESTADOS_VIAJE, TransporteViaje

Q2 = Decimal("0.01")


def _d(v: Any) -> Decimal | None:
    if v is None or str(v).strip() == "":
        return None
    try:
        return Decimal(str(v).strip().replace(",", ".")).quantize(Q2, rounding=ROUND_HALF_UP)
    except Exception:
        return None


def _parse_dt(value: str | None) -> datetime | None:
    if not value or not str(value).strip():
        return None
    raw = str(value).strip().replace("T", " ")
    try:
        return datetime.fromisoformat(raw)
    except ValueError:
        pass
    for fmt in ("%Y-%m-%d %H:%M", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
        try:
            return datetime.strptime(raw[: len(fmt)], fmt)
        except ValueError:
            continue
    return None


def _parse_int(value: str | None) -> int | None:
    if value is None or str(value).strip() == "":
        return None
    try:
        return int(str(value).strip())
    except ValueError:
        return None


def km_recorrido(v: TransporteViaje) -> int | None:
    if v.odometro_inicio is None or v.odometro_fin is None:
        return None
    d = v.odometro_fin - v.odometro_inicio
    return d if d > 0 else None


def horas_viaje(v: TransporteViaje) -> float | None:
    if not v.real_salida or not v.real_llegada:
        return None
    sec = (v.real_llegada - v.real_salida).total_seconds()
    if sec < 0:
        return None
    return round(sec / 3600.0, 2)


def litros_100km(v: TransporteViaje) -> Decimal | None:
    km = km_recorrido(v)
    if km is None or v.litros_combustible is None:
        return None
    if km <= 0:
        return None
    lit = v.litros_combustible
    if lit <= 0:
        return None
    return (lit / Decimal(km)) * Decimal(100)


def rendimiento_km_l_desde_l100(l100: float | None) -> float | None:
    """Convierte L/100 km a km/L usando la razón 100 / L100."""
    if l100 is None or l100 <= 0:
        return None
    return round(100.0 / l100, 2)


def desvio_consumo_pct(v: TransporteViaje) -> float | None:
    """Desvío porcentual de consumo real L/100km vs referencial L/100km."""
    real_l100 = litros_100km(v)
    real = float(real_l100) if real_l100 is not None else None
    ref_l100 = None
    if v.vehiculo and v.vehiculo.consumo_referencial_l100km is not None:
        ref_l100 = float(v.vehiculo.consumo_referencial_l100km)
    if real is None or ref_l100 is None or ref_l100 <= 0:
        return None
    return round((real - ref_l100) / ref_l100 * 100.0, 1)


def metricas_viaje_dict(v: TransporteViaje) -> dict[str, Any]:
    km = km_recorrido(v)
    h = horas_viaje(v)
    l100 = litros_100km(v)
    desv = desvio_consumo_pct(v)
    vel_media = None
    if km is not None and h and h > 0:
        vel_media = round(km / h, 1)
    l100_float = float(l100) if l100 is not None else None
    return {
        "km": km,
        "horas": h,
        "litros_100km": l100_float,
        "rendimiento_km_l": rendimiento_km_l_desde_l100(l100_float),
        "desvio_consumo_pct": desv,
        "referencial_l100km": (
            float(v.vehiculo.consumo_referencial_l100km)
            if v.vehiculo and v.vehiculo.consumo_referencial_l100km is not None
            else None
        ),
        "vel_media_kmh": vel_media,
    }


def siguiente_folio_viaje(db: Session) -> str:
    y = datetime.utcnow().year
    pref = f"HR-{y}-"
    folios = list(
        db.scalars(
            select(TransporteViaje.folio).where(TransporteViaje.folio.startswith(pref))
        ).all()
    )
    n = 0
    for f in folios:
        try:
            part = f.split("-")[-1]
            n = max(n, int(part))
        except (ValueError, IndexError):
            continue
    return f"{pref}{n + 1:05d}"


def listar_viajes(
    db: Session,
    *,
    estado: str | None = None,
    empleado_id: int | None = None,
    limite: int = 300,
) -> list[TransporteViaje]:
    q = (
        select(TransporteViaje)
        .options(
            selectinload(TransporteViaje.empleado),
            selectinload(TransporteViaje.vehiculo),
            selectinload(TransporteViaje.cliente),
            selectinload(TransporteViaje.fondo),
        )
        .order_by(TransporteViaje.updated_at.desc(), TransporteViaje.id.desc())
        .limit(limite)
    )
    if estado:
        q = q.where(TransporteViaje.estado == estado)
    if empleado_id:
        q = q.where(TransporteViaje.empleado_id == empleado_id)
    return list(db.scalars(q).all())


def obtener_viaje(db: Session, viaje_id: int) -> TransporteViaje | None:
    return db.scalars(
        select(TransporteViaje)
        .where(TransporteViaje.id == viaje_id)
        .options(
            selectinload(TransporteViaje.empleado),
            selectinload(TransporteViaje.vehiculo),
            selectinload(TransporteViaje.cliente),
            selectinload(TransporteViaje.fondo),
        )
    ).first()


def listar_fondos_para_viaje(db: Session, *, limite: int = 100) -> list[FondoRendir]:
    """Anticipos abiertos o pendientes para asociar al viaje."""
    return list(
        db.scalars(
            select(FondoRendir)
            .where(FondoRendir.estado.in_(("ABIERTO", "PENDIENTE_APROBACION")))
            .options(selectinload(FondoRendir.empleado), selectinload(FondoRendir.vehiculo))
            .order_by(FondoRendir.fecha_entrega.desc())
            .limit(limite)
        ).all()
    )


def crear_viaje(
    db: Session,
    *,
    empleado_id: int,
    vehiculo_transporte_id: int | None,
    cliente_id: int | None,
    fondo_rendir_id: int | None,
    origen: str,
    destino: str,
    referencia_carga: str | None,
    programado_salida: datetime | None,
    programado_llegada: datetime | None,
    notas: str | None,
) -> TransporteViaje:
    if not empleado_id:
        raise ValueError("Seleccione chofer / trabajador.")
    v = TransporteViaje(
        folio=siguiente_folio_viaje(db),
        empleado_id=empleado_id,
        vehiculo_transporte_id=vehiculo_transporte_id,
        cliente_id=cliente_id,
        fondo_rendir_id=fondo_rendir_id,
        estado="BORRADOR",
        origen=(origen or "").strip()[:240],
        destino=(destino or "").strip()[:240],
        referencia_carga=(referencia_carga or "").strip()[:200] or None,
        programado_salida=programado_salida,
        programado_llegada=programado_llegada,
        notas=notas,
    )
    db.add(v)
    db.flush()
    return v


def actualizar_viaje_borrador(
    db: Session,
    v: TransporteViaje,
    *,
    empleado_id: int,
    vehiculo_transporte_id: int | None,
    cliente_id: int | None,
    fondo_rendir_id: int | None,
    origen: str,
    destino: str,
    referencia_carga: str | None,
    programado_salida: datetime | None,
    programado_llegada: datetime | None,
    notas: str | None,
) -> None:
    if v.estado != "BORRADOR":
        raise ValueError("Solo se editan viajes en borrador.")
    v.empleado_id = empleado_id
    v.vehiculo_transporte_id = vehiculo_transporte_id
    v.cliente_id = cliente_id
    v.fondo_rendir_id = fondo_rendir_id
    v.origen = (origen or "").strip()[:240]
    v.destino = (destino or "").strip()[:240]
    v.referencia_carga = (referencia_carga or "").strip()[:200] or None
    v.programado_salida = programado_salida
    v.programado_llegada = programado_llegada
    v.notas = notas


def actualizar_viaje_corregible(
    db: Session,
    v: TransporteViaje,
    *,
    empleado_id: int,
    vehiculo_transporte_id: int | None,
    cliente_id: int | None,
    fondo_rendir_id: int | None,
    origen: str,
    destino: str,
    referencia_carga: str | None,
    programado_salida: datetime | None,
    programado_llegada: datetime | None,
    notas: str | None,
) -> None:
    """
    Permite corrección operativa en BORRADOR y CERRADO (ej. patente/chofer/ruta).
    En CERRADO solo se corrigen datos maestros/planificación; el estado no cambia.
    """
    if v.estado not in ("BORRADOR", "CERRADO"):
        raise ValueError("Solo se permiten correcciones en viajes BORRADOR o CERRADO.")
    if not empleado_id:
        raise ValueError("Seleccione chofer / trabajador.")
    if not (origen or "").strip() or not (destino or "").strip():
        raise ValueError("Origen y destino son obligatorios.")

    # Cronología mínima para no invalidar métricas históricas.
    if programado_salida and programado_llegada and programado_llegada < programado_salida:
        raise ValueError("La llegada programada no puede ser anterior a la salida programada.")
    if v.real_salida and programado_salida and v.real_salida < programado_salida:
        raise ValueError("La salida real no puede quedar anterior a la salida programada.")
    if v.real_llegada and v.real_salida and v.real_llegada < v.real_salida:
        raise ValueError("La llegada real no puede ser anterior a la salida real.")
    if v.real_llegada and programado_llegada and v.real_llegada < programado_llegada:
        raise ValueError("La llegada real no puede quedar anterior a la llegada programada.")

    v.empleado_id = empleado_id
    v.vehiculo_transporte_id = vehiculo_transporte_id
    v.cliente_id = cliente_id
    v.fondo_rendir_id = fondo_rendir_id
    v.origen = (origen or "").strip()[:240]
    v.destino = (destino or "").strip()[:240]
    v.referencia_carga = (referencia_carga or "").strip()[:200] or None
    v.programado_salida = programado_salida
    v.programado_llegada = programado_llegada
    v.notas = notas


def iniciar_viaje(
    db: Session,
    v: TransporteViaje,
    *,
    real_salida: datetime,
    odometro_inicio: int,
) -> None:
    if v.estado != "BORRADOR":
        raise ValueError("Solo se inicia desde borrador.")
    if v.programado_salida and real_salida < v.programado_salida:
        raise ValueError("La salida real no puede ser anterior a la salida programada.")
    if odometro_inicio < 0:
        raise ValueError("Odómetro inválido.")
    v.estado = "EN_CURSO"
    v.real_salida = real_salida
    v.odometro_inicio = odometro_inicio


def cerrar_viaje(
    db: Session,
    v: TransporteViaje,
    *,
    real_llegada: datetime,
    odometro_fin: int,
    litros_combustible: Decimal | None,
    motivo_desvio: str | None = None,
    observaciones_cierre: str | None = None,
) -> None:
    if v.estado != "EN_CURSO":
        raise ValueError("Solo se cierra un viaje en curso.")
    if v.real_salida and real_llegada < v.real_salida:
        raise ValueError("La llegada real no puede ser anterior a la salida real.")
    if v.programado_llegada and real_llegada < v.programado_llegada:
        raise ValueError("La llegada real no puede ser anterior a la llegada programada.")
    if v.odometro_inicio is not None and odometro_fin < v.odometro_inicio:
        raise ValueError("Odómetro final debe ser mayor o igual al inicial.")
    if v.vehiculo_transporte_id and litros_combustible is None:
        raise ValueError("Debe registrar litros de combustible para cerrar viaje con vehículo.")
    v.estado = "CERRADO"
    v.real_llegada = real_llegada
    v.odometro_fin = odometro_fin
    v.litros_combustible = litros_combustible
    v.motivo_desvio = (motivo_desvio or "").strip() or None
    v.observaciones_cierre = (observaciones_cierre or "").strip() or None
    d = desvio_consumo_pct(v)
    v.alerta_consumo = bool(d is not None and d > 10.0)


def anular_viaje(db: Session, v: TransporteViaje, *, motivo: str) -> None:
    if v.estado == "CERRADO":
        raise ValueError("No se anula un viaje ya cerrado.")
    if v.estado == "ANULADO":
        return
    v.estado = "ANULADO"
    v.motivo_anulacion = (motivo or "").strip()[:2000] or "Sin motivo"


def eliminar_viaje(db: Session, v: TransporteViaje) -> None:
    """Borrado físico: solo permitido en BORRADOR o ANULADO."""
    if v.estado not in ("BORRADOR", "ANULADO"):
        raise ValueError("Solo se puede borrar una hoja en BORRADOR o ANULADA.")
    db.delete(v)


def _viajes_cerrados_ventana(db: Session, dias: int = 120) -> list[TransporteViaje]:
    since = datetime.utcnow() - timedelta(days=dias)
    return list(
        db.scalars(
            select(TransporteViaje)
            .where(
                TransporteViaje.estado == "CERRADO",
                TransporteViaje.real_llegada.isnot(None),
                TransporteViaje.real_llegada >= since,
            )
            .options(
                selectinload(TransporteViaje.empleado),
                selectinload(TransporteViaje.vehiculo),
            )
        ).all()
    )


def dashboard_stats(db: Session, *, dias: int = 120) -> dict[str, Any]:
    """KPIs globales + series para gráficos ApexCharts."""
    cerrados = _viajes_cerrados_ventana(db, dias=dias)
    abiertos = int(
        db.scalar(select(func.count()).select_from(TransporteViaje).where(TransporteViaje.estado == "EN_CURSO"))
        or 0
    )
    borradores = int(
        db.scalar(select(func.count()).select_from(TransporteViaje).where(TransporteViaje.estado == "BORRADOR"))
        or 0
    )

    km_total = 0
    horas_sum = 0.0
    horas_n = 0
    l100_vals: list[float] = []
    desv_vals: list[float] = []

    for v in cerrados:
        km = km_recorrido(v)
        if km:
            km_total += km
        h = horas_viaje(v)
        if h is not None:
            horas_sum += h
            horas_n += 1
        l100 = litros_100km(v)
        if l100 is not None:
            l100_vals.append(float(l100))
        d = desvio_consumo_pct(v)
        if d is not None:
            desv_vals.append(d)

    # Conteo por estado (todos los viajes)
    estados_rows = db.execute(
        select(TransporteViaje.estado, func.count())
        .select_from(TransporteViaje)
        .group_by(TransporteViaje.estado)
    ).all()
    estado_labels: list[str] = []
    estado_counts: list[int] = []
    for st, cnt in sorted(estados_rows, key=lambda x: x[0]):
        estado_labels.append(st.replace("_", " "))
        estado_counts.append(int(cnt))

    # Km por mes (cerrados con km)
    mes_km: dict[tuple[int, int], int] = defaultdict(int)
    for v in cerrados:
        km = km_recorrido(v)
        if not km or not v.real_llegada:
            continue
        key = (v.real_llegada.year, v.real_llegada.month)
        mes_km[key] += km

    now = datetime.utcnow()
    mes_labels: list[str] = []
    mes_kms: list[int] = []
    meses_corto = ("ene", "feb", "mar", "abr", "may", "jun", "jul", "ago", "sep", "oct", "nov", "dic")
    for i in range(5, -1, -1):
        y, m = now.year, now.month - i
        while m <= 0:
            m += 12
            y -= 1
        while m > 12:
            m -= 12
            y += 1
        mes_labels.append(f"{meses_corto[m - 1]} {y % 100}")
        mes_kms.append(mes_km.get((y, m), 0))

    return {
        "dias_ventana": dias,
        "viajes_cerrados_periodo": len(cerrados),
        "viajes_en_curso": abiertos,
        "viajes_borrador": borradores,
        "km_total_periodo": km_total,
        "horas_promedio_viaje": round(horas_sum / horas_n, 2) if horas_n else None,
        "consumo_promedio_l100": round(sum(l100_vals) / len(l100_vals), 2) if l100_vals else None,
        "rendimiento_promedio_km_l": (
            rendimiento_km_l_desde_l100(round(sum(l100_vals) / len(l100_vals), 2))
            if l100_vals
            else None
        ),
        "desvio_promedio_pct": round(sum(desv_vals) / len(desv_vals), 1) if desv_vals else None,
        "chart": {
            "estado_labels": estado_labels,
            "estado_counts": estado_counts,
            "mes_labels": mes_labels,
            "mes_kms": mes_kms,
        },
    }


def comparativo_choferes(db: Session, *, dias: int = 120, top: int = 12) -> list[dict[str, Any]]:
    cerrados = _viajes_cerrados_ventana(db, dias=dias)
    by_e: dict[int, list[TransporteViaje]] = defaultdict(list)
    for v in cerrados:
        by_e[v.empleado_id].append(v)

    rows: list[dict[str, Any]] = []
    for eid, lst in by_e.items():
        nombre = lst[0].empleado.nombre_completo if lst[0].empleado else f"#{eid}"
        kms = [km_recorrido(x) for x in lst]
        kms_ok = [k for k in kms if k is not None]
        hs = [horas_viaje(x) for x in lst]
        hs_ok = [h for h in hs if h is not None]
        l100s = [litros_100km(x) for x in lst]
        l100_ok = [float(x) for x in l100s if x is not None]
        desvs = [desvio_consumo_pct(x) for x in lst]
        desv_ok = [d for d in desvs if d is not None]
        rows.append(
            {
                "empleado_id": eid,
                "nombre": nombre,
                "n_viajes": len(lst),
                "km_total": sum(kms_ok),
                "km_promedio": round(sum(kms_ok) / len(kms_ok), 1) if kms_ok else None,
                "horas_promedio": round(sum(hs_ok) / len(hs_ok), 2) if hs_ok else None,
                "l100_promedio": round(sum(l100_ok) / len(l100_ok), 2) if l100_ok else None,
                "km_l_promedio": (
                    rendimiento_km_l_desde_l100(round(sum(l100_ok) / len(l100_ok), 2))
                    if l100_ok
                    else None
                ),
                "desvio_pct_promedio": round(sum(desv_ok) / len(desv_ok), 1) if desv_ok else None,
            }
        )
    rows.sort(key=lambda r: r["km_total"], reverse=True)
    return rows[:top]


def comparativo_vehiculos(db: Session, *, dias: int = 120, top: int = 12) -> list[dict[str, Any]]:
    cerrados = [v for v in _viajes_cerrados_ventana(db, dias=dias) if v.vehiculo_transporte_id]
    by_v: dict[int, list[TransporteViaje]] = defaultdict(list)
    for v in cerrados:
        by_v[v.vehiculo_transporte_id].append(v)  # type: ignore[arg-type]

    rows: list[dict[str, Any]] = []
    for vid, lst in by_v.items():
        pat = lst[0].vehiculo.patente if lst[0].vehiculo else f"#{vid}"
        ref = lst[0].vehiculo.consumo_referencial_l100km if lst[0].vehiculo else None
        kms_ok = [km_recorrido(x) for x in lst]
        kms_ok = [k for k in kms_ok if k is not None]
        l100s = [litros_100km(x) for x in lst]
        l100_ok = [float(x) for x in l100s if x is not None]
        rows.append(
            {
                "vehiculo_id": vid,
                "patente": pat,
                "referencial_l100": float(ref) if ref is not None else None,
                "referencial_km_l": (
                    rendimiento_km_l_desde_l100(float(ref)) if ref is not None else None
                ),
                "n_viajes": len(lst),
                "km_total": sum(kms_ok),
                "l100_promedio": round(sum(l100_ok) / len(l100_ok), 2) if l100_ok else None,
                "km_l_promedio": (
                    rendimiento_km_l_desde_l100(round(sum(l100_ok) / len(l100_ok), 2))
                    if l100_ok
                    else None
                ),
            }
        )
    rows.sort(key=lambda r: r["km_total"], reverse=True)
    return rows[:top]


def indicadores_combustible(db: Session, *, dias: int = 120) -> dict[str, Any]:
    cerrados = _viajes_cerrados_ventana(db, dias=dias)
    km_total = 0
    litros_total = Decimal("0")
    km_con_dato = 0
    litros_ref_esperados = Decimal("0")
    litros_excedentes = Decimal("0")
    alertas: list[dict[str, Any]] = []
    by_chofer: dict[str, dict[str, float]] = defaultdict(lambda: {"km": 0.0, "litros": 0.0})
    by_patente: dict[str, dict[str, float]] = defaultdict(lambda: {"km": 0.0, "litros": 0.0})
    by_ruta: dict[str, dict[str, float]] = defaultdict(lambda: {"km": 0.0, "litros": 0.0})

    for v in cerrados:
        km = km_recorrido(v)
        if km is None:
            continue
        km_total += km
        if v.litros_combustible is not None and v.litros_combustible > 0:
            litros_total += Decimal(v.litros_combustible)
            km_con_dato += km
            chofer = v.empleado.nombre_completo if v.empleado else f"#{v.empleado_id}"
            by_chofer[chofer]["km"] += km
            by_chofer[chofer]["litros"] += float(v.litros_combustible)
            pat = v.vehiculo.patente if v.vehiculo else "S/PATENTE"
            by_patente[pat]["km"] += km
            by_patente[pat]["litros"] += float(v.litros_combustible)
            ruta = f"{(v.origen or '').strip()} -> {(v.destino or '').strip()}"
            by_ruta[ruta]["km"] += km
            by_ruta[ruta]["litros"] += float(v.litros_combustible)
        if v.vehiculo and v.vehiculo.consumo_referencial_l100km and km > 0:
            ref_lit = (Decimal(km) * Decimal(v.vehiculo.consumo_referencial_l100km)) / Decimal(100)
            litros_ref_esperados += ref_lit
            if v.litros_combustible and v.litros_combustible > ref_lit:
                litros_excedentes += Decimal(v.litros_combustible) - ref_lit
        d = desvio_consumo_pct(v)
        if d is not None and d > 10:
            alertas.append({"viaje_id": v.id, "folio": v.folio, "desvio_pct": d})

    l100_real = (float((litros_total / Decimal(km_con_dato)) * Decimal(100)) if km_con_dato > 0 else None)
    km_l_real = (round(km_con_dato / float(litros_total), 2) if litros_total > 0 else None)
    l100_ref = (float((litros_ref_esperados / Decimal(km_total)) * Decimal(100)) if km_total > 0 and litros_ref_esperados > 0 else None)
    desvio = (round((l100_real - l100_ref) / l100_ref * 100, 1) if l100_real is not None and l100_ref and l100_ref > 0 else None)

    def _ranking(src: dict[str, dict[str, float]]) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        for label, data in src.items():
            if data["km"] <= 0 or data["litros"] <= 0:
                continue
            l100 = (data["litros"] / data["km"]) * 100
            rows.append({"label": label, "km": round(data["km"], 1), "l100": round(l100, 2), "km_l": round(100 / l100, 2)})
        rows.sort(key=lambda x: x["l100"], reverse=True)
        return rows[:10]

    return {
        "km_recorridos": km_total,
        "litros_consumidos": float(litros_total),
        "l100_real": round(l100_real, 2) if l100_real is not None else None,
        "km_l_real": km_l_real,
        "l100_referencial": round(l100_ref, 2) if l100_ref is not None else None,
        "desvio_pct": desvio,
        "litros_esperados": round(float(litros_ref_esperados), 2),
        "litros_excedentes": round(float(litros_excedentes), 2),
        "ranking_chofer": _ranking(by_chofer),
        "ranking_patente": _ranking(by_patente),
        "ranking_ruta": _ranking(by_ruta),
        "alertas_sobreconsumo": alertas,
    }


def ultimos_viajes_resumen(db: Session, *, limite: int = 15) -> list[TransporteViaje]:
    return list(
        db.scalars(
            select(TransporteViaje)
            .options(
                selectinload(TransporteViaje.empleado),
                selectinload(TransporteViaje.vehiculo),
            )
            .order_by(TransporteViaje.updated_at.desc())
            .limit(limite)
        ).all()
    )
