# crud/comercial/leasing_fin.py
# -*- coding: utf-8 -*-
from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Any, List, Optional

from sqlalchemy import delete, select, update
from sqlalchemy.orm import Session, selectinload

from crud.finanzas.plan_cuentas import asegurar_cuentas_leasing_financiero, obtener_plan_cuenta_por_codigo
from models.comercial.leasing_financiero_cotizacion import (
    LeasingFinancieroCotizacion,
    LeasingFinancieroDocumentoProceso,
    LeasingFinancieroHistorial,
)
from schemas.comercial.leasing_cotizacion import ESTADOS_LF, LeasingCotizacionCreate, LeasingCotizacionUpdate, LeasingSimulacionInput
from services.leasing_financiero import aplicar_parametros_financieros, normalizar_periodicidad, simular_cotizacion
from services.leasing_financiero_contabilidad import (
    activar_contabilidad_leasing_financiero,
    regenerar_proyeccion_contable,
)
from crud.comercial.leasing_fin_operacion import (
    get_cotizacion_completa,
    inicializar_checklist,
    persistir_amortizacion_oficial,
    registrar_factura_compra,
    registrar_orden_compra,
    sincronizar_checklist_automatico,
    solicitar_pago_proveedor,
    upsert_activo,
)
from services.leasing_financiero_workflow import (
    checklist_bloqueantes_pendientes,
    merge_workflow,
    puede_transicionar,
    siguiente_etapa as _siguiente_etapa_svc,
    workflow_por_defecto,
)

_WORKFLOW_ETAPAS = [
    "ANALISIS_CREDITO",
    "ORDEN_COMPRA",
    "CONTRATO_FIRMADO",
    "ACTA_RECEPCION",
    "ACTIVACION_CONTABLE",
]
_ESTADOS_EDITABLES = ESTADOS_LF - {"ACTIVADA", "VIGENTE"}
_ESTADOS_NO_ELIMINABLES = {"ACTIVADA", "VIGENTE"}
_ESTADOS_APROBACION_CREDITO = {"APROBADO", "APROBADA_CONDICIONES"}
_CUENTAS_CONTABLES_REQUERIDAS = ("113701", "210701", "210702", "410701", "110201")


def _aplicar_metricas_persistidas(cotizacion: LeasingFinancieroCotizacion) -> None:
    """Calcula TIR/CAE y desglose tributario para persistir en la cotización."""
    try:
        periodicidad = normalizar_periodicidad(getattr(cotizacion, "periodicidad", "MENSUAL"))
    except ValueError:
        periodicidad = "MENSUAL"
    payload = LeasingSimulacionInput(
        moneda=str(cotizacion.moneda or "CLP"),
        tasa=cotizacion.tasa,
        plazo=cotizacion.plazo,
        opcion_compra=cotizacion.opcion_compra,
        periodos_gracia=cotizacion.periodos_gracia or 0,
        periodicidad=periodicidad,
        fecha_inicio=cotizacion.fecha_inicio,
        fecha_primera_cuota=getattr(cotizacion, "fecha_primera_cuota", None),
        valor_neto=cotizacion.valor_neto,
        pago_inicial_tipo=cotizacion.pago_inicial_tipo,
        pago_inicial_valor=cotizacion.pago_inicial_valor,
        financia_seguro=bool(cotizacion.financia_seguro),
        seguro_monto_uf=cotizacion.seguro_monto_uf,
        otros_montos_pesos=cotizacion.otros_montos_pesos,
        comision_apertura=getattr(cotizacion, "comision_apertura", None),
        comision_apertura_tipo=getattr(cotizacion, "comision_apertura_tipo", None),
        financia_comision=bool(getattr(cotizacion, "financia_comision", False)),
        gastos_operacionales=getattr(cotizacion, "gastos_operacionales", None),
        iva_aplica=bool(getattr(cotizacion, "iva_aplica", False)),
        iva_tasa=getattr(cotizacion, "iva_tasa", None),
        iva_recuperable=bool(getattr(cotizacion, "iva_recuperable", True)),
        uf_valor=cotizacion.uf_valor,
        monto_financiado=cotizacion.monto_financiado,
        dolar_valor=cotizacion.dolar_valor,
    )
    resumen = simular_cotizacion(payload)
    if resumen.tir_anual_pct is not None:
        cotizacion.tir_anual_pct = resumen.tir_anual_pct
    if resumen.cae_anual_pct is not None:
        cotizacion.cae_anual_pct = resumen.cae_anual_pct
    if resumen.desglose_tributario:
        cotizacion.metadata_tributaria = resumen.desglose_tributario


def cambiar_estado_cotizacion(
    db: Session,
    *,
    cotizacion: LeasingFinancieroCotizacion,
    estado_nuevo: str,
    comentario: str | None = None,
    usuario: str = "sistema",
) -> LeasingFinancieroCotizacion:
    estado_nuevo = str(estado_nuevo or "").strip().upper()
    if estado_nuevo not in ESTADOS_LF:
        raise ValueError("Estado de leasing financiero inválido.")
    estado_actual = str(cotizacion.estado or "").upper()
    if estado_actual in {"ACTIVADA", "VIGENTE"} and estado_nuevo not in {"ANULADA", "VIGENTE", "ACTIVADA"}:
        raise ValueError("No se puede cambiar el estado de una operación activada excepto a ANULADA.")
    if not puede_transicionar(estado_actual, estado_nuevo):
        raise ValueError(f"Transición de estado no permitida: {estado_actual} → {estado_nuevo}.")
    if estado_nuevo == estado_actual:
        return cotizacion
    cotizacion.estado = estado_nuevo
    _registrar_historial(
        db,
        cotizacion=cotizacion,
        tipo_evento="CAMBIO_ESTADO",
        estado_desde=estado_actual,
        estado_hasta=estado_nuevo,
        comentario=comentario or f"Estado actualizado a {estado_nuevo}",
        usuario=usuario,
    )
    db.add(cotizacion)
    db.commit()
    db.refresh(cotizacion)
    return get_cotizacion(db, int(cotizacion.id)) or cotizacion


def get_cotizacion(db: Session, cotizacion_id: int) -> Optional[LeasingFinancieroCotizacion]:
    return get_cotizacion_completa(db, cotizacion_id)


def get_cotizaciones(
    db: Session,
    *,
    cliente_id: Optional[int] = None,
    estado: Optional[str] = None,
    ejecutivo: Optional[str] = None,
    moneda: Optional[str] = None,
    fecha_desde: Optional[date] = None,
    fecha_hasta: Optional[date] = None,
    limit: int = 200,
) -> List[LeasingFinancieroCotizacion]:
    stmt = select(LeasingFinancieroCotizacion).options(
        selectinload(LeasingFinancieroCotizacion.cliente),
        selectinload(LeasingFinancieroCotizacion.analisis_credito),
    )

    if cliente_id is not None:
        stmt = stmt.where(LeasingFinancieroCotizacion.cliente_id == cliente_id)

    if estado:
        stmt = stmt.where(LeasingFinancieroCotizacion.estado == estado)
    if ejecutivo:
        stmt = stmt.where(LeasingFinancieroCotizacion.ejecutivo.ilike(f"%{ejecutivo}%"))
    if moneda:
        stmt = stmt.where(LeasingFinancieroCotizacion.moneda == moneda.upper())

    if fecha_desde:
        stmt = stmt.where(LeasingFinancieroCotizacion.fecha_cotizacion >= fecha_desde)
    if fecha_hasta:
        stmt = stmt.where(LeasingFinancieroCotizacion.fecha_cotizacion <= fecha_hasta)

    stmt = stmt.order_by(
        LeasingFinancieroCotizacion.fecha_cotizacion.desc(),
        LeasingFinancieroCotizacion.id.desc(),
    ).limit(limit)

    return list(db.scalars(stmt))


def listar_cotizaciones(db: Session) -> List[LeasingFinancieroCotizacion]:
    return get_cotizaciones(db)


def listar_cotizaciones_por_cliente(db: Session, cliente_id: int) -> List[LeasingFinancieroCotizacion]:
    return get_cotizaciones(db, cliente_id=cliente_id)


_ACTIVO_CAMPOS = frozenset({"activo_marca", "activo_modelo", "activo_serie", "activo_chasis"})


def _activo_payload_from_data(data: dict) -> dict[str, Any]:
    return {
        "marca": data.pop("activo_marca", None),
        "modelo": data.pop("activo_modelo", None),
        "numero_serie": data.pop("activo_serie", None),
        "numero_chasis": data.pop("activo_chasis", None),
    }


def _dump_cotizacion(obj_in: LeasingCotizacionCreate | LeasingCotizacionUpdate, *, creating: bool) -> dict:
    data = obj_in.model_dump(exclude_unset=not creating)
    for k in _ACTIVO_CAMPOS:
        data.pop(k, None)
    if "moneda" in data and data["moneda"] is not None:
        data["moneda"] = str(data["moneda"]).strip().upper()
    if "estado" in data and data["estado"] is not None:
        data["estado"] = str(data["estado"]).strip().upper()
        if data["estado"] not in ESTADOS_LF:
            raise ValueError("Estado de leasing financiero inválido.")
    return data


def _registrar_historial(
    db: Session,
    *,
    cotizacion: LeasingFinancieroCotizacion,
    tipo_evento: str,
    estado_desde: str | None,
    estado_hasta: str | None,
    comentario: str | None = None,
    usuario: str = "sistema",
    metadata_json: dict[str, Any] | None = None,
) -> None:
    if cotizacion.id is None:
        raise ValueError("No se puede registrar historial sin ID de cotización.")
    db.add(
        LeasingFinancieroHistorial(
            cotizacion_id=int(cotizacion.id),
            tipo_evento=tipo_evento,
            estado_desde=estado_desde,
            estado_hasta=estado_hasta,
            comentario=comentario,
            usuario=(usuario or "sistema").strip() or "sistema",
            metadata_json=metadata_json or {},
        )
    )


def _validar_moneda_y_tipo_cambio(*, moneda: str, uf_valor: object, dolar_valor: object) -> None:
    m = (moneda or "CLP").strip().upper()
    if m not in {"CLP", "USD", "UF"}:
        raise ValueError("Moneda inválida. Use CLP, USD o UF.")
    if m == "USD":
        if dolar_valor is None or Decimal(str(dolar_valor)) <= 0:
            raise ValueError("Para moneda USD debe informar valor dólar mayor a 0.")
    if m == "UF":
        if uf_valor is None or Decimal(str(uf_valor)) <= 0:
            raise ValueError("Para moneda UF debe informar valor UF mayor a 0.")


def _validar_parametros_cotizacion(data: dict, *, estricto: bool = False) -> None:
    plazo = data.get("plazo")
    if plazo is not None and int(plazo) <= 0:
        raise ValueError("El plazo debe ser mayor a 0 meses.")
    periodos_gracia = data.get("periodos_gracia")
    if periodos_gracia is not None and int(periodos_gracia) < 0:
        raise ValueError("Los períodos de gracia no pueden ser negativos.")
    if plazo is not None and periodos_gracia is not None and int(plazo) <= int(periodos_gracia):
        raise ValueError("El plazo debe ser mayor a los períodos de gracia.")
    if not estricto:
        return
    monto_fin = data.get("monto_financiado")
    valor_neto = data.get("valor_neto")
    if (monto_fin is None or monto_fin <= 0) and (valor_neto is None or valor_neto <= 0):
        raise ValueError("Debe informar valor neto o monto financiado mayor a 0.")


def crear_cotizacion(db: Session, *, obj_in: LeasingCotizacionCreate) -> LeasingFinancieroCotizacion:
    raw = obj_in.model_dump()
    activo_extra = _activo_payload_from_data(raw)
    data = _dump_cotizacion(obj_in, creating=True)
    if data.get("fecha_cotizacion") is None:
        data["fecha_cotizacion"] = date.today()
    data = aplicar_parametros_financieros(data)
    _validar_parametros_cotizacion(data, estricto=False)
    _validar_moneda_y_tipo_cambio(
        moneda=str(data.get("moneda") or "CLP"),
        uf_valor=data.get("uf_valor"),
        dolar_valor=data.get("dolar_valor"),
    )

    if not data.get("estado"):
        data["estado"] = "BORRADOR"
    try:
        cot = LeasingFinancieroCotizacion(**data)
        db.add(cot)
        db.flush()

        _registrar_historial(
            db,
            cotizacion=cot,
            tipo_evento="CREACION",
            estado_desde=None,
            estado_hasta=str(data["estado"]),
            comentario="Creación de cotización leasing financiero",
        )

        _aplicar_metricas_persistidas(cot)
        regenerar_proyeccion_contable(db, cot)
        inicializar_checklist(db, cot)
        upsert_activo(
            db,
            cot,
            data={
                "descripcion": data.get("bien_descripcion"),
                "categoria": data.get("bien_tipo"),
                "proveedor_id": data.get("proveedor_id"),
                "valor_neto": data.get("valor_neto"),
                **activo_extra,
            },
        )
        persistir_amortizacion_oficial(db, cot)
        sincronizar_checklist_automatico(db, cot)

        db.commit()
        db.refresh(cot)
        return get_cotizacion(db, int(cot.id)) or cot
    except Exception:
        db.rollback()
        raise


def actualizar_cotizacion(
    db: Session,
    *,
    cotizacion: LeasingFinancieroCotizacion,
    obj_in: LeasingCotizacionUpdate,
) -> LeasingFinancieroCotizacion:
    if str(cotizacion.estado or "").upper() not in _ESTADOS_EDITABLES:
        raise ValueError("No se puede editar una operación activada o vigente.")
    if bool(getattr(cotizacion, "condiciones_congeladas", False)):
        raise ValueError("Las condiciones financieras están congeladas. Cree una nueva versión de escenario.")
    estado_original = str(cotizacion.estado or "").upper()
    update_data = obj_in.model_dump(exclude_unset=True)
    activo_extra = _activo_payload_from_data(update_data)
    moneda_objetivo = str(update_data.get("moneda") or cotizacion.moneda or "CLP").strip().upper()
    uf_objetivo = update_data.get("uf_valor", cotizacion.uf_valor)
    dolar_objetivo = update_data.get("dolar_valor", cotizacion.dolar_valor)
    _validar_moneda_y_tipo_cambio(
        moneda=moneda_objetivo,
        uf_valor=uf_objetivo,
        dolar_valor=dolar_objetivo,
    )
    if "estado" in update_data and update_data["estado"] is not None:
        update_data["estado"] = str(update_data["estado"]).strip().upper()
    if "moneda" in update_data and update_data["moneda"] is not None:
        update_data["moneda"] = str(update_data["moneda"]).strip().upper()
    if "concesionario" in update_data and update_data["concesionario"] is not None:
        update_data["concesionario"] = update_data["concesionario"].strip() or None
    if "ejecutivo" in update_data and update_data["ejecutivo"] is not None:
        update_data["ejecutivo"] = update_data["ejecutivo"].strip() or None

    merged = {
        "moneda": moneda_objetivo,
        "uf_valor": uf_objetivo,
        "dolar_valor": dolar_objetivo,
        "valor_neto": update_data.get("valor_neto", cotizacion.valor_neto),
        "pago_inicial_tipo": update_data.get("pago_inicial_tipo", cotizacion.pago_inicial_tipo),
        "pago_inicial_valor": update_data.get("pago_inicial_valor", cotizacion.pago_inicial_valor),
        "financia_seguro": update_data.get("financia_seguro", cotizacion.financia_seguro),
        "seguro_monto_uf": update_data.get("seguro_monto_uf", cotizacion.seguro_monto_uf),
        "otros_montos_pesos": update_data.get("otros_montos_pesos", cotizacion.otros_montos_pesos),
        "monto_financiado": update_data.get("monto_financiado", cotizacion.monto_financiado),
        "tasa": update_data.get("tasa", cotizacion.tasa),
        "plazo": update_data.get("plazo", cotizacion.plazo),
        "periodos_gracia": update_data.get("periodos_gracia", cotizacion.periodos_gracia),
        "monto": update_data.get("monto", cotizacion.monto),
    }
    if "monto_financiado" not in update_data or update_data.get("monto_financiado") is None:
        merged["monto_financiado"] = None
    aplicar_parametros_financieros(merged)
    if "tasa" in update_data:
        update_data["tasa"] = merged["tasa"]
    if merged.get("monto_financiado") is not None:
        update_data["monto_financiado"] = merged["monto_financiado"]
    if merged.get("monto") is not None and "monto" not in update_data:
        update_data["monto"] = merged["monto"]
    _validar_parametros_cotizacion({**merged, **update_data}, estricto=False)

    for field, value in update_data.items():
        if hasattr(cotizacion, field) and value is not None:
            setattr(cotizacion, field, value)
    estado_nuevo = str(cotizacion.estado or "").upper()
    if estado_nuevo not in ESTADOS_LF:
        raise ValueError("Estado de leasing financiero inválido.")
    if estado_nuevo != estado_original:
        _registrar_historial(
            db,
            cotizacion=cotizacion,
            tipo_evento="CAMBIO_ESTADO",
            estado_desde=estado_original,
            estado_hasta=estado_nuevo,
            comentario="Cambio manual de estado en edición",
        )

    db.add(cotizacion)
    db.flush()
    _aplicar_metricas_persistidas(cotizacion)
    upsert_activo(
        db,
        cotizacion,
        data={
            "descripcion": update_data.get("bien_descripcion", cotizacion.bien_descripcion),
            "categoria": update_data.get("bien_tipo", cotizacion.bien_tipo),
            "proveedor_id": update_data.get("proveedor_id", cotizacion.proveedor_id),
            "valor_neto": update_data.get("valor_neto", cotizacion.valor_neto),
            **activo_extra,
        },
    )
    persistir_amortizacion_oficial(db, cotizacion)
    sincronizar_checklist_automatico(db, cotizacion)
    db.commit()
    db.refresh(cotizacion)

    cot = get_cotizacion(db, int(cotizacion.id)) or cotizacion
    regenerar_proyeccion_contable(db, cot)
    db.commit()
    db.refresh(cot)
    return cot


def _workflow_por_defecto() -> dict[str, Any]:
    return workflow_por_defecto()


def obtener_workflow(cotizacion: LeasingFinancieroCotizacion) -> dict[str, Any]:
    raw = cotizacion.workflow_json if isinstance(cotizacion.workflow_json, dict) else {}
    return merge_workflow(raw)


def _siguiente_etapa(workflow: dict[str, Any]) -> str:
    return _siguiente_etapa_svc(workflow)


def _asegurar_analisis_aprobado(cotizacion: LeasingFinancieroCotizacion) -> None:
    analisis = getattr(cotizacion, "analisis_credito", None)
    rec = str(getattr(analisis, "recomendacion", "") or "").strip().upper()
    if rec not in _ESTADOS_APROBACION_CREDITO:
        raise ValueError("Debe existir análisis de crédito aprobado para avanzar el flujo.")


def listar_documentos_proceso(db: Session, cotizacion_id: int) -> list[LeasingFinancieroDocumentoProceso]:
    stmt = (
        select(LeasingFinancieroDocumentoProceso)
        .where(LeasingFinancieroDocumentoProceso.cotizacion_id == cotizacion_id)
        .order_by(
            LeasingFinancieroDocumentoProceso.modulo.asc(),
            LeasingFinancieroDocumentoProceso.version_n.desc(),
        )
    )
    return list(db.scalars(stmt))


def guardar_documento_proceso(
    db: Session,
    *,
    cotizacion: LeasingFinancieroCotizacion,
    modulo: str,
    payload: dict[str, Any],
    usuario: str = "sistema",
) -> LeasingFinancieroDocumentoProceso:
    modulo_norm = str(modulo or "").strip().lower()
    if modulo_norm not in {"orden_compra", "contrato", "acta_recepcion", "factura_proveedor", "pagare", "identidad"}:
        raise ValueError("Módulo de documento inválido.")
    if modulo_norm in {"orden_compra", "contrato", "acta_recepcion", "factura_proveedor", "pagare", "identidad"}:
        _asegurar_analisis_aprobado(cotizacion)

    last_stmt = (
        select(LeasingFinancieroDocumentoProceso)
        .where(
            LeasingFinancieroDocumentoProceso.cotizacion_id == int(cotizacion.id),
            LeasingFinancieroDocumentoProceso.modulo == modulo_norm,
        )
        .order_by(LeasingFinancieroDocumentoProceso.version_n.desc())
        .limit(1)
    )
    prev = db.scalars(last_stmt).first()
    version_n = int(prev.version_n) + 1 if prev else 1
    doc = LeasingFinancieroDocumentoProceso(
        cotizacion_id=int(cotizacion.id),
        modulo=modulo_norm,
        version_n=version_n,
        estado=str((payload or {}).get("estado") or "RECIBIDO").upper(),
        payload_json=payload or {},
        usuario=(usuario or "sistema").strip() or "sistema",
    )
    db.add(doc)

    workflow = obtener_workflow(cotizacion)
    if not cotizacion.checklist_items:
        inicializar_checklist(db, cotizacion)
    if modulo_norm == "orden_compra":
        workflow["hitos"]["orden_compra"] = True
        workflow["checklist_documental"]["orden_compra_generada"] = True
        registrar_orden_compra(db, cotizacion, data=payload or {}, usuario=usuario)
    elif modulo_norm == "contrato":
        workflow["hitos"]["contrato_firmado"] = True
        workflow["checklist_documental"]["contrato_generado"] = True
        workflow["checklist_documental"]["contrato_aprobado"] = True
        from services.leasing_financiero_workflow import marcar_checklist_item

        marcar_checklist_item(cotizacion.checklist_items, "contrato_generado", responsable=usuario)
        marcar_checklist_item(
            cotizacion.checklist_items,
            "contrato_aprobado",
            estado="APROBADO",
            aprobado_por=usuario,
            responsable=usuario,
        )
        if payload.get("numero_contrato"):
            cotizacion.numero_contrato = str(payload.get("numero_contrato"))
    elif modulo_norm == "acta_recepcion":
        workflow["hitos"]["acta_recepcion"] = True
    elif modulo_norm == "factura_proveedor":
        workflow["hitos"]["factura_compra"] = True
        workflow["checklist_documental"]["factura_registrada"] = True
        registrar_factura_compra(db, cotizacion, data=payload or {}, usuario=usuario)
    workflow["etapa_actual"] = _siguiente_etapa(workflow)
    cotizacion.workflow_json = workflow
    sincronizar_checklist_automatico(db, cotizacion, usuario=usuario)
    estado_origen = str(cotizacion.estado or "").upper()
    if str(cotizacion.estado or "").upper() in {"COTIZADA", "EN_ANALISIS_CREDITO", "APROBADA", "APROBADA_CONDICIONES"}:
        cotizacion.estado = "EN_FORMALIZACION"
        if (
            workflow["hitos"].get("orden_compra")
            and workflow["hitos"].get("contrato_firmado")
            and workflow["hitos"].get("acta_recepcion")
            and workflow["hitos"].get("factura_compra")
        ):
            cotizacion.estado = "DOCUMENTACION_COMPLETA"
            if cotizacion.fecha_formalizacion is None:
                cotizacion.fecha_formalizacion = date.today()
    _registrar_historial(
        db,
        cotizacion=cotizacion,
        tipo_evento="DOCUMENTO",
        estado_desde=estado_origen,
        estado_hasta=str(cotizacion.estado or "").upper(),
        comentario=f"Registro documento {modulo_norm}",
        usuario=usuario,
        metadata_json=payload or {},
    )

    db.add(cotizacion)
    db.commit()
    db.refresh(doc)
    return doc


def sincronizar_hito_credito(db: Session, *, cotizacion: LeasingFinancieroCotizacion) -> LeasingFinancieroCotizacion:
    _asegurar_analisis_aprobado(cotizacion)
    workflow = obtener_workflow(cotizacion)
    workflow["hitos"]["analisis_credito"] = True
    workflow["etapa_actual"] = _siguiente_etapa(workflow)
    cotizacion.workflow_json = workflow
    rec = str(getattr(cotizacion.analisis_credito, "recomendacion", "") or "").upper()
    estado_origen = str(cotizacion.estado or "").upper()
    if rec == "APROBADO":
        cotizacion.estado = "APROBADA"
    else:
        cotizacion.estado = "APROBADA_CONDICIONES"
    cotizacion.fecha_aprobacion = date.today()
    persistir_amortizacion_oficial(db, cotizacion, usuario="sistema", congelar=True)
    sincronizar_checklist_automatico(db, cotizacion)
    _registrar_historial(
        db,
        cotizacion=cotizacion,
        tipo_evento="SCORING",
        estado_desde=estado_origen,
        estado_hasta=str(cotizacion.estado),
        comentario=f"Sincronización de crédito: {rec}",
        metadata_json={"recomendacion": rec},
    )
    db.add(cotizacion)
    db.commit()
    db.refresh(cotizacion)
    return cotizacion


def activar_flujo_contable(
    db: Session,
    *,
    cotizacion: LeasingFinancieroCotizacion,
    usuario: str = "sistema",
) -> int:
    workflow = obtener_workflow(cotizacion)
    _asegurar_analisis_aprobado(cotizacion)
    if not workflow["hitos"].get("orden_compra"):
        raise ValueError("Debe registrar orden de compra antes de activar.")
    if not workflow["hitos"].get("contrato_firmado"):
        raise ValueError("Debe registrar contrato firmado antes de activar.")
    if not workflow["hitos"].get("acta_recepcion"):
        raise ValueError("Debe registrar acta de recepción antes de activar.")
    if not workflow["hitos"].get("factura_compra") and not getattr(cotizacion, "facturas_compra", None):
        raise ValueError("Debe registrar factura de compra antes de activar.")
    if not getattr(cotizacion, "checklist_items", None):
        inicializar_checklist(db, cotizacion)
    sincronizar_checklist_automatico(db, cotizacion, usuario=usuario)
    items = getattr(cotizacion, "checklist_items", None) or []
    if items:
        pendientes = checklist_bloqueantes_pendientes(items)
        criticos = [p for p in pendientes if getattr(p, "codigo", "") not in {"solicitud_pago"}]
        if criticos:
            titulos = ", ".join(getattr(p, "titulo", getattr(p, "codigo", "")) for p in criticos[:5])
            raise ValueError(f"Checklist incompleto. Pendientes bloqueantes: {titulos}")

    if not cotizacion.monto_financiado or cotizacion.monto_financiado <= 0:
        raise ValueError("Debe informar monto financiado válido antes de activar.")
    if cotizacion.tasa is None:
        raise ValueError("Debe informar tasa válida antes de activar.")
    if Decimal(str(cotizacion.tasa)) <= Decimal("-0.99"):
        raise ValueError("La tasa no puede ser -0.99 o menor.")
    if not cotizacion.plazo or cotizacion.plazo <= 0:
        raise ValueError("Debe informar plazo válido antes de activar.")
    if not cotizacion.fecha_inicio:
        raise ValueError("Debe informar fecha de inicio antes de activar.")
    asegurar_cuentas_leasing_financiero(db)
    for codigo in _CUENTAS_CONTABLES_REQUERIDAS:
        cuenta = obtener_plan_cuenta_por_codigo(db, codigo)
        if not cuenta:
            raise ValueError(f"No existe cuenta contable requerida: {codigo}.")
        if str(cuenta.estado or "").upper() != "ACTIVO":
            raise ValueError(f"La cuenta contable requerida {codigo} está inactiva.")

    estado_origen = str(cotizacion.estado or "").upper()
    asiento_id = activar_contabilidad_leasing_financiero(db, cotizacion, usuario=usuario)
    workflow["hitos"]["activacion_contable"] = True
    workflow["etapa_actual"] = "ACTIVACION_CONTABLE"
    cotizacion.workflow_json = workflow
    cotizacion.contrato_activo = True
    cotizacion.estado = "ACTIVADA"
    cotizacion.asiento_id = asiento_id
    cotizacion.fecha_activacion = date.today()
    cotizacion.fecha_vigencia_desde = cotizacion.fecha_inicio
    if cotizacion.numero_operacion is None:
        cotizacion.numero_operacion = f"LF-{int(cotizacion.id):06d}"
    _registrar_historial(
        db,
        cotizacion=cotizacion,
        tipo_evento="ACTIVACION_CONTABLE",
        estado_desde=estado_origen,
        estado_hasta="ACTIVADA",
        comentario=f"Activación contable asiento #{asiento_id}",
        usuario=usuario,
        metadata_json={"asiento_id": asiento_id},
    )
    db.add(cotizacion)
    sincronizar_checklist_automatico(db, cotizacion, usuario=usuario)
    db.commit()
    return asiento_id


def solicitar_pago(
    db: Session,
    *,
    cotizacion: LeasingFinancieroCotizacion,
    factura_id: int | None = None,
    usuario: str = "sistema",
    aprobado_por: str | None = None,
):
    if not cotizacion.checklist_items:
        inicializar_checklist(db, cotizacion)
    sol = solicitar_pago_proveedor(
        db,
        cotizacion,
        factura_id=factura_id,
        usuario=usuario,
        aprobado_por=aprobado_por,
    )
    _registrar_historial(
        db,
        cotizacion=cotizacion,
        tipo_evento="SOLICITUD_PAGO",
        estado_desde=str(cotizacion.estado or "").upper(),
        estado_hasta=str(cotizacion.estado or "").upper(),
        comentario=f"Solicitud de pago #{sol.id} por {sol.monto}",
        usuario=usuario,
        metadata_json={"solicitud_pago_id": int(sol.id), "factura_id": int(sol.factura_compra_id)},
    )
    db.add(cotizacion)
    db.commit()
    db.refresh(sol)
    return sol


def get_hub_resumen(db: Session) -> dict[str, Any]:
    cotizaciones = get_cotizaciones(db, limit=1000)
    kpis = {
        "abiertas": 0,
        "en_credito": 0,
        "aprobadas": 0,
        "formalizacion": 0,
        "vigentes": 0,
        "rechazadas": 0,
        "activadas": 0,
        "total": len(cotizaciones),
    }
    pipeline_montos: dict[str, Decimal] = {"CLP": Decimal("0"), "UF": Decimal("0"), "USD": Decimal("0")}
    cartera_montos: dict[str, Decimal] = {"CLP": Decimal("0"), "UF": Decimal("0"), "USD": Decimal("0")}
    _estados_pipeline = {
        "BORRADOR",
        "COTIZADA",
        "EN_ANALISIS_COMERCIAL",
        "EN_ANALISIS_CREDITO",
        "APROBADA",
        "APROBADA_CONDICIONES",
        "EN_FORMALIZACION",
        "DOCUMENTACION_COMPLETA",
    }
    _estados_cartera = {"VIGENTE", "ACTIVADA"}

    for c in cotizaciones:
        est = str(c.estado or "").upper()
        moneda = str(c.moneda or "CLP").strip().upper()
        if moneda not in pipeline_montos:
            moneda = "CLP"
        monto = c.monto_financiado or c.valor_neto or c.monto or Decimal("0")
        if monto and monto > 0:
            if est in _estados_pipeline:
                pipeline_montos[moneda] += Decimal(str(monto))
            if est in _estados_cartera:
                cartera_montos[moneda] += Decimal(str(monto))

        if est in {"BORRADOR", "COTIZADA", "EN_ANALISIS_COMERCIAL"}:
            kpis["abiertas"] += 1
        if est == "EN_ANALISIS_CREDITO":
            kpis["en_credito"] += 1
        if est in {"APROBADA", "APROBADA_CONDICIONES"}:
            kpis["aprobadas"] += 1
        if est in {"EN_FORMALIZACION", "DOCUMENTACION_COMPLETA", "ACTIVADA"}:
            kpis["formalizacion"] += 1
        if est == "VIGENTE":
            kpis["vigentes"] += 1
        if est in {"RECHAZADA", "PERDIDA_CLIENTE", "ANULADA"}:
            kpis["rechazadas"] += 1
        if est in {"ACTIVADA", "VIGENTE"}:
            kpis["activadas"] += 1

    cerradas = kpis["activadas"] + kpis["rechazadas"]
    tasa_cierre_pct = (
        Decimal(str(kpis["activadas"])) / Decimal(str(cerradas)) * Decimal("100")
        if cerradas > 0
        else None
    )

    funnel = [
        {
            "key": "cotizacion",
            "label": "Cotización",
            "count": kpis["abiertas"],
            "hint": "BORRADOR · COTIZADA · ANÁLISIS COMERCIAL",
        },
        {
            "key": "credito",
            "label": "Crédito",
            "count": kpis["en_credito"],
            "hint": "Scoring y aprobación",
        },
        {
            "key": "aprobacion",
            "label": "Aprobación",
            "count": kpis["aprobadas"],
            "hint": "Condiciones comerciales",
        },
        {
            "key": "formalizacion",
            "label": "Formalización",
            "count": kpis["formalizacion"],
            "hint": "OC · contrato · acta",
        },
        {
            "key": "cartera",
            "label": "Cartera",
            "count": kpis["activadas"],
            "hint": "ACTIVADA · VIGENTE",
        },
    ]

    pendientes_credito = [c for c in cotizaciones if str(c.estado or "").upper() == "EN_ANALISIS_CREDITO"][:10]
    pendientes_docs = [
        c
        for c in cotizaciones
        if str(c.estado or "").upper() in {"APROBADA", "APROBADA_CONDICIONES", "EN_FORMALIZACION"}
    ][:10]
    pendientes_activacion = [c for c in cotizaciones if str(c.estado or "").upper() == "DOCUMENTACION_COMPLETA"][:10]
    recientes = cotizaciones[:8]

    return {
        "kpis": kpis,
        "recientes": recientes,
        "pendientes_credito": pendientes_credito,
        "pendientes_documentacion": pendientes_docs,
        "pendientes_activacion": pendientes_activacion,
        "pipeline_montos": pipeline_montos,
        "cartera_montos": cartera_montos,
        "tasa_cierre_pct": tasa_cierre_pct,
        "funnel": funnel,
    }


def puede_eliminar_cotizacion(cotizacion: LeasingFinancieroCotizacion) -> bool:
    est = str(cotizacion.estado or "").upper()
    if est in _ESTADOS_NO_ELIMINABLES:
        return False
    if bool(cotizacion.contrato_activo):
        return False
    if cotizacion.asiento_id is not None:
        return False
    return True


def eliminar_cotizaciones(db: Session, *, ids: list[int]) -> dict[str, Any]:
    if not ids:
        raise ValueError("Seleccione al menos una cotización.")

    ids_unicos = list(dict.fromkeys(int(i) for i in ids if int(i) > 0))
    stmt = select(LeasingFinancieroCotizacion).where(LeasingFinancieroCotizacion.id.in_(ids_unicos))
    cotizaciones = list(db.scalars(stmt))
    encontrados = {int(c.id) for c in cotizaciones}
    no_encontradas = [i for i in ids_unicos if i not in encontrados]

    eliminables: list[LeasingFinancieroCotizacion] = []
    bloqueadas: list[LeasingFinancieroCotizacion] = []
    for cot in cotizaciones:
        if puede_eliminar_cotizacion(cot):
            eliminables.append(cot)
        else:
            bloqueadas.append(cot)

    if not eliminables:
        if bloqueadas:
            raise ValueError(
                "Las cotizaciones seleccionadas no pueden eliminarse (activadas, vigentes o con contabilidad)."
            )
        raise ValueError("No se encontraron cotizaciones válidas para eliminar.")

    elim_ids = [int(c.id) for c in eliminables]
    try:
        from models.comercial.credito_riesgo import CreditoSolicitud

        db.execute(
            update(CreditoSolicitud)
            .where(CreditoSolicitud.comercial_lf_cotizacion_id.in_(elim_ids))
            .values(comercial_lf_cotizacion_id=None)
        )
    except Exception:
        pass

    try:
        db.execute(
            delete(LeasingFinancieroCotizacion).where(LeasingFinancieroCotizacion.id.in_(elim_ids))
        )
        db.commit()
    except Exception:
        db.rollback()
        raise

    return {
        "eliminadas": len(eliminables),
        "bloqueadas": len(bloqueadas),
        "no_encontradas": len(no_encontradas),
        "ids_eliminados": elim_ids,
    }


def obtener_ultimo_documento_payload(db: Session, cotizacion_id: int, modulo: str) -> dict:
    stmt = (
        select(LeasingFinancieroDocumentoProceso)
        .where(
            LeasingFinancieroDocumentoProceso.cotizacion_id == cotizacion_id,
            LeasingFinancieroDocumentoProceso.modulo == str(modulo or "").strip().lower(),
        )
        .order_by(LeasingFinancieroDocumentoProceso.version_n.desc())
        .limit(1)
    )
    row = db.scalars(stmt).first()
    if row and isinstance(row.payload_json, dict):
        return dict(row.payload_json)
    return {}


def listar_historial(db: Session, cotizacion_id: int) -> list[LeasingFinancieroHistorial]:
    stmt = (
        select(LeasingFinancieroHistorial)
        .where(LeasingFinancieroHistorial.cotizacion_id == cotizacion_id)
        .order_by(LeasingFinancieroHistorial.created_at.desc())
    )
    return list(db.scalars(stmt))
