# crud/comercial/taller.py
# -*- coding: utf-8 -*-
from __future__ import annotations

import json
import uuid
from collections import defaultdict
from datetime import datetime
from decimal import Decimal, ROUND_HALF_UP
from typing import Any, Optional

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session, joinedload, selectinload

from models.comercial.orden_servicio import OrdenServicio
from models.comercial.orden_servicio_linea import OrdenServicioCotizacionLinea
from models.comercial.vehiculo import Vehiculo
from models.maestros.cliente import Cliente

IVA_TASA = Decimal("0.19")
Q2 = Decimal("0.01")
Q4 = Decimal("0.0001")

ESTADOS_ORDEN = (
    "RECIBIDA",
    "EN_DIAGNOSTICO",
    "EN_REPARACION",
    "LISTO_ENTREGA",
    "ENTREGADA",
    "ANULADA",
)

ESTADO_LABEL_CORTO: dict[str, str] = {
    "RECIBIDA": "Recibida",
    "EN_DIAGNOSTICO": "Diagnóstico",
    "EN_REPARACION": "Reparación",
    "LISTO_ENTREGA": "Listo retiro",
    "ENTREGADA": "Entregada",
    "ANULADA": "Anulada",
}

_MESES_CORTO = (
    "ene",
    "feb",
    "mar",
    "abr",
    "may",
    "jun",
    "jul",
    "ago",
    "sep",
    "oct",
    "nov",
    "dic",
)


def _months_span(n: int) -> list[tuple[int, int]]:
    """Últimos n meses calendario (año, mes), orden cronológico."""
    now = datetime.utcnow()
    y, m = now.year, now.month
    for _ in range(n - 1):
        m -= 1
        if m == 0:
            m = 12
            y -= 1
    keys: list[tuple[int, int]] = []
    for _ in range(n):
        keys.append((y, m))
        m += 1
        if m == 13:
            m = 1
            y += 1
    return keys

NIVELES_COMBUSTIBLE = ("E", "1/4", "1/2", "3/4", "F")


def _d(v: Any) -> Decimal:
    try:
        return Decimal(str(v if v is not None else "0")).quantize(Q2, rounding=ROUND_HALF_UP)
    except Exception:
        return Decimal("0.00")


def _d_qty(v: Any) -> Decimal:
    try:
        d = Decimal(str(v if v is not None else "1"))
        if d <= 0:
            d = Decimal("1")
        return d.quantize(Q4, rounding=ROUND_HALF_UP)
    except Exception:
        return Decimal("1.0000")


def totales_cotizacion(
    subtotal_neto: Decimal, *, afecta_iva: bool
) -> dict[str, Decimal]:
    sn = subtotal_neto.quantize(Q2, rounding=ROUND_HALF_UP)
    iva = (sn * IVA_TASA).quantize(Q2, rounding=ROUND_HALF_UP) if afecta_iva else Decimal("0.00")
    total = (sn + iva).quantize(Q2, rounding=ROUND_HALF_UP)
    return {"subtotal_neto": sn, "iva": iva, "total": total}


def parse_cotizacion_json(raw: str | None) -> list[dict[str, Any]]:
    if not raw or not str(raw).strip():
        return []
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as e:
        raise ValueError("El detalle de cotización no es JSON válido.") from e
    if not isinstance(data, list):
        raise ValueError("La cotización debe ser una lista de líneas.")
    out: list[dict[str, Any]] = []
    for idx, row in enumerate(data, start=1):
        if not isinstance(row, dict):
            continue
        desc = str(row.get("descripcion") or "").strip()
        cant = _d_qty(row.get("cantidad", 1))
        pu = _d(row.get("precio_unitario", 0))
        vn = (cant * pu).quantize(Q2, rounding=ROUND_HALF_UP)
        if not desc and vn == 0 and pu == 0:
            continue
        if not desc:
            desc = f"Ítem {idx}"
        out.append(
            {
                "descripcion": desc,
                "cantidad": cant,
                "precio_unitario": pu,
                "valor_neto": vn,
            }
        )
    return out


def sync_lineas_cotizacion(
    db: Session, orden_id: int, lineas: list[dict[str, Any]]
) -> None:
    db.execute(
        delete(OrdenServicioCotizacionLinea).where(
            OrdenServicioCotizacionLinea.orden_servicio_id == orden_id
        )
    )
    for i, row in enumerate(lineas, start=1):
        ln = OrdenServicioCotizacionLinea(
            orden_servicio_id=orden_id,
            linea=i,
            descripcion=row["descripcion"],
            cantidad=row["cantidad"],
            precio_unitario=row["precio_unitario"],
            valor_neto=row["valor_neto"],
        )
        db.add(ln)
    db.flush()


def subtotal_desde_lineas_orm(lineas: list[OrdenServicioCotizacionLinea]) -> Decimal:
    return sum((_d(getattr(x, "valor_neto", 0)) for x in lineas), Decimal("0.00")).quantize(
        Q2, rounding=ROUND_HALF_UP
    )


def _bool(v: Any) -> bool:
    if v is None:
        return False
    s = str(v).strip().lower()
    return s in ("1", "true", "on", "yes", "si", "sí")


def crear_vehiculo(
    db: Session,
    *,
    cliente_id: int,
    patente: str,
    marca: str,
    modelo: str,
    color: str | None = None,
    anio: int | None = None,
    vin: str | None = None,
    km_actual: int | None = None,
) -> Vehiculo:
    p = patente.strip().upper()
    if not p:
        raise ValueError("La patente es obligatoria.")
    m = marca.strip()
    mo = modelo.strip()
    if not m or not mo:
        raise ValueError("Marca y modelo son obligatorios.")
    v = Vehiculo(
        cliente_id=cliente_id,
        patente=p,
        marca=m,
        modelo=mo,
        color=(color or "").strip() or None,
        anio=anio,
        vin=(vin or "").strip() or None,
        km_actual=km_actual,
    )
    db.add(v)
    db.flush()
    return v


def _asignar_folio(db: Session, orden: OrdenServicio) -> None:
    ts = orden.fecha_recepcion or datetime.utcnow()
    year = ts.year
    orden.folio = f"OS-{year}-{orden.id:06d}"


def crear_orden_servicio(
    db: Session,
    *,
    cliente_id: int,
    vehiculo_id: int | None,
    nuevo_vehiculo: dict[str, Any] | None,
    fecha_recepcion: datetime,
    fecha_entrega_estimada: datetime | None,
    contacto_nombre: str | None,
    contacto_telefono: str | None,
    trabajo_solicitado: str | None,
    observaciones: str | None,
    estado: str,
    campos_check: dict[str, bool],
    nivel_combustible: str | None,
    danos: dict[str, str | None],
    pagare_monto: Decimal | None,
    pagare_ciudad: str | None,
    pagare_tasa: Decimal | None,
    ingreso_grua: bool | None = None,
    ote_num: str | None = None,
    email_contacto: str | None = None,
    cotizacion_afecta_iva: bool = True,
) -> OrdenServicio:
    cli = db.get(Cliente, cliente_id)
    if not cli:
        raise ValueError("El cliente no existe.")

    if vehiculo_id:
        veh = db.get(Vehiculo, vehiculo_id)
        if not veh or veh.cliente_id != cliente_id:
            raise ValueError("El vehículo no corresponde al cliente.")
    elif nuevo_vehiculo:
        veh = crear_vehiculo(db, cliente_id=cliente_id, **nuevo_vehiculo)
    else:
        raise ValueError("Seleccione un vehículo o ingrese uno nuevo.")

    if estado not in ESTADOS_ORDEN:
        estado = "RECIBIDA"

    # Folio temporal único: evita INSERT con NULL si en BD folio es NOT NULL.
    folio_tmp = f"TMP-{uuid.uuid4().hex[:24].upper()}"
    orden = OrdenServicio(
        folio=folio_tmp,
        cliente_id=cliente_id,
        vehiculo_id=veh.id,
        estado=estado,
        fecha_recepcion=fecha_recepcion,
        fecha_entrega_estimada=fecha_entrega_estimada,
        contacto_nombre=(contacto_nombre or "").strip() or None,
        contacto_telefono=(contacto_telefono or "").strip() or None,
        trabajo_solicitado=(trabajo_solicitado or "").strip() or None,
        observaciones=(observaciones or "").strip() or None,
        nivel_combustible=nivel_combustible if nivel_combustible in NIVELES_COMBUSTIBLE else None,
        dano_vista_frente=danos.get("frente"),
        dano_vista_atras=danos.get("atras"),
        dano_vista_izquierda=danos.get("izquierda"),
        dano_vista_derecha=danos.get("derecha"),
        pagare_monto=pagare_monto,
        pagare_ciudad=(pagare_ciudad or "").strip() or None,
        pagare_tasa_interes_mensual=pagare_tasa,
        ingreso_grua=ingreso_grua,
        ote_num=(ote_num or "").strip() or None,
        email_contacto=(email_contacto or "").strip() or None,
        cotizacion_afecta_iva=bool(cotizacion_afecta_iva),
    )

    for key, val in campos_check.items():
        if hasattr(orden, key):
            setattr(orden, key, val)

    db.add(orden)
    db.flush()
    _asignar_folio(db, orden)
    # commit() lo hace la ruta (Depends get_db) para no romper la transacción de FastAPI
    return orden


def actualizar_orden_servicio(
    db: Session,
    orden_id: int,
    *,
    fecha_recepcion: datetime | None,
    estado: str,
    fecha_entrega_estimada: datetime | None,
    contacto_nombre: str | None,
    contacto_telefono: str | None,
    trabajo_solicitado: str | None,
    observaciones: str | None,
    campos_check: dict[str, bool],
    nivel_combustible: str | None,
    danos: dict[str, str | None],
    pagare_monto: Decimal | None,
    pagare_ciudad: str | None,
    pagare_tasa: Decimal | None,
    ingreso_grua: bool | None = None,
    ote_num: str | None = None,
    email_contacto: str | None = None,
    cotizacion_afecta_iva: bool = True,
) -> OrdenServicio:
    orden = db.get(OrdenServicio, orden_id)
    if not orden:
        raise ValueError("La orden no existe.")
    if estado in ESTADOS_ORDEN:
        orden.estado = estado
    if fecha_recepcion is not None:
        orden.fecha_recepcion = fecha_recepcion
    orden.fecha_entrega_estimada = fecha_entrega_estimada
    orden.contacto_nombre = (contacto_nombre or "").strip() or None
    orden.contacto_telefono = (contacto_telefono or "").strip() or None
    orden.trabajo_solicitado = (trabajo_solicitado or "").strip() or None
    orden.observaciones = (observaciones or "").strip() or None
    orden.nivel_combustible = nivel_combustible if nivel_combustible in NIVELES_COMBUSTIBLE else None
    orden.dano_vista_frente = danos.get("frente")
    orden.dano_vista_atras = danos.get("atras")
    orden.dano_vista_izquierda = danos.get("izquierda")
    orden.dano_vista_derecha = danos.get("derecha")
    orden.pagare_monto = pagare_monto
    orden.pagare_ciudad = (pagare_ciudad or "").strip() or None
    orden.pagare_tasa_interes_mensual = pagare_tasa
    orden.ingreso_grua = ingreso_grua
    orden.ote_num = (ote_num or "").strip() or None
    orden.email_contacto = (email_contacto or "").strip() or None
    orden.cotizacion_afecta_iva = bool(cotizacion_afecta_iva)
    for key, val in campos_check.items():
        if hasattr(orden, key):
            setattr(orden, key, val)
    return orden


def listar_ordenes(
    db: Session,
    *,
    estado: Optional[str] = None,
    limit: int = 200,
) -> list[OrdenServicio]:
    q = (
        select(OrdenServicio)
        .options(joinedload(OrdenServicio.cliente), joinedload(OrdenServicio.vehiculo))
        .order_by(OrdenServicio.fecha_recepcion.desc())
    )
    if estado:
        q = q.where(OrdenServicio.estado == estado)
    return list(db.scalars(q.limit(limit)).all())


def obtener_orden(db: Session, orden_id: int) -> OrdenServicio | None:
    return db.scalars(
        select(OrdenServicio)
        .options(
            joinedload(OrdenServicio.cliente),
            joinedload(OrdenServicio.vehiculo),
            selectinload(OrdenServicio.lineas_cotizacion),
        )
        .where(OrdenServicio.id == orden_id)
    ).first()


def listar_vehiculos_cliente(db: Session, cliente_id: int) -> list[Vehiculo]:
    return list(
        db.scalars(
            select(Vehiculo)
            .where(Vehiculo.cliente_id == cliente_id, Vehiculo.activo.is_(True))
            .order_by(Vehiculo.patente)
        ).all()
    )


def conteos_hub(db: Session) -> dict[str, Any]:
    total = db.scalar(select(func.count()).select_from(OrdenServicio)) or 0
    abiertas = db.scalar(
        select(func.count())
        .select_from(OrdenServicio)
        .where(~OrdenServicio.estado.in_(("ENTREGADA", "ANULADA")))
    ) or 0
    vehiculos = db.scalar(select(func.count()).select_from(Vehiculo)) or 0
    n_listo_entrega = (
        db.scalar(
            select(func.count())
            .select_from(OrdenServicio)
            .where(OrdenServicio.estado == "LISTO_ENTREGA")
        )
        or 0
    )

    estado_labels: list[str] = []
    estado_counts: list[int] = []
    for code in ESTADOS_ORDEN:
        estado_labels.append(ESTADO_LABEL_CORTO.get(code, code))
        n_e = (
            db.scalar(
                select(func.count()).select_from(OrdenServicio).where(OrdenServicio.estado == code)
            )
            or 0
        )
        estado_counts.append(int(n_e))

    mes_keys = _months_span(6)
    keys_set = set(mes_keys)
    cutoff = datetime(mes_keys[0][0], mes_keys[0][1], 1)
    rows_mes = db.execute(
        select(OrdenServicio.created_at).where(OrdenServicio.created_at >= cutoff)
    ).all()
    agg_mes: dict[tuple[int, int], int] = defaultdict(int)
    for (created_at,) in rows_mes:
        if not created_at:
            continue
        key = (created_at.year, created_at.month)
        if key not in keys_set:
            continue
        agg_mes[key] += 1

    mes_labels: list[str] = []
    mes_n: list[int] = []
    for y, m in mes_keys:
        mes_labels.append(f"{_MESES_CORTO[m - 1]} {y}")
        mes_n.append(int(agg_mes.get((y, m), 0)))

    listos = list(
        db.scalars(
            select(OrdenServicio)
            .options(joinedload(OrdenServicio.cliente), joinedload(OrdenServicio.vehiculo))
            .where(OrdenServicio.estado == "LISTO_ENTREGA")
            .order_by(OrdenServicio.fecha_recepcion.asc())
            .limit(12)
        ).all()
    )
    alertas_listo: list[dict[str, Any]] = []
    for o in listos:
        alertas_listo.append(
            {
                "orden_id": int(o.id),
                "folio": (o.folio or "").strip() or f"#{o.id}",
                "cliente": o.cliente.razon_social if o.cliente else "",
                "patente": o.vehiculo.patente if o.vehiculo else "",
            }
        )

    return {
        "ordenes_total": int(total),
        "ordenes_abiertas": int(abiertas),
        "vehiculos": int(vehiculos),
        "n_listo_entrega": int(n_listo_entrega),
        "alertas_listo_entrega": alertas_listo,
        "chart": {
            "estado_labels": estado_labels,
            "estado_counts": estado_counts,
            "mes_labels": mes_labels,
            "mes_n": mes_n,
        },
    }


CHECK_KEYS = (
    "testigo_airbag",
    "testigo_check_engine",
    "testigo_abs",
    "testigo_aceite",
    "testigo_bateria",
    "testigo_cinturon",
    "testigo_freno_mano",
    "testigo_luces_altas",
    "testigo_traccion",
    "testigo_temperatura",
    "inv_gato",
    "inv_herramientas",
    "inv_triangulos",
    "inv_tapetes",
    "inv_llanta_repuesto",
    "inv_extintor",
    "inv_antena",
    "inv_emblemas",
    "inv_tapones_rueda",
    "inv_cables",
    "inv_estereo",
    "inv_encendedor",
)


def campos_check_desde_form(form: dict[str, Any]) -> dict[str, bool]:
    out: dict[str, bool] = {}
    for k in CHECK_KEYS:
        out[k] = _bool(form.get(k))
    return out


TESTIGO_LABELS: tuple[tuple[str, str], ...] = (
    ("testigo_airbag", "Airbag"),
    ("testigo_check_engine", "Check engine"),
    ("testigo_abs", "ABS"),
    ("testigo_aceite", "Presión aceite"),
    ("testigo_bateria", "Batería"),
    ("testigo_cinturon", "Cinturón"),
    ("testigo_freno_mano", "Freno mano"),
    ("testigo_luces_altas", "Luces altas"),
    ("testigo_traccion", "Tracción / ESP"),
    ("testigo_temperatura", "Temperatura"),
)

INV_LABELS: tuple[tuple[str, str], ...] = (
    ("inv_gato", "Gato"),
    ("inv_herramientas", "Herramientas"),
    ("inv_triangulos", "Triángulos"),
    ("inv_tapetes", "Tapetes"),
    ("inv_llanta_repuesto", "Llanta repuesto"),
    ("inv_extintor", "Extintor"),
    ("inv_antena", "Antena"),
    ("inv_emblemas", "Emblemas"),
    ("inv_tapones_rueda", "Tapones rueda"),
    ("inv_cables", "Cables"),
    ("inv_estereo", "Estéreo"),
    ("inv_encendedor", "Encendedor"),
)


def checks_desde_orden(orden: Any) -> dict[str, bool]:
    return {k: bool(getattr(orden, k, False)) for k in CHECK_KEYS}
