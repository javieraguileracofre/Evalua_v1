# services/tesoreria/actualizacion.py
# -*- coding: utf-8 -*-
"""Orquesta la descarga SII y la importación idempotente en la base de la empresa."""
from __future__ import annotations

import hashlib
import logging
import threading
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from core.paths import PROJECT_ROOT
from crud.tesoreria import sii as crud_sii
from integrations.sii.client import ResultadoDescarga, SiiRuntime, descargar_libros
from integrations.sii.errors import EstructuraInvalida, SiiEtapaError, mensaje_publico, scrub
from integrations.sii.normalizer import normalizar_tabla
from integrations.sii.parser import leer_tabla
from services.tesoreria.crypto import SiiCryptoError, decrypt_secret
from services.tesoreria.precondiciones import validar_precondiciones

logger = logging.getLogger("evalua.sii")

_LOCK = threading.Lock()
_RUNNING: set[int] = set()
_SLOTS: dict[tuple[int, int], threading.Event] = {}

_ESTADO_PASO = {
    "conexion": "EN_PROCESO",
    "auth": "EN_PROCESO",
    "periodo": "EN_PROCESO",
    "compras": "DESCARGANDO_COMPRAS",
    "ventas": "DESCARGANDO_VENTAS",
    "importacion": "IMPORTANDO",
}

Descargador = Callable[..., ResultadoDescarga]


class TesoreriaError(Exception):
    def __init__(self, mensaje: str):
        self.mensaje = mensaje
        super().__init__(mensaje)


@dataclass(frozen=True)
class Solicitud:
    company_id: int
    company_name: str
    rut: str
    ejecucion_id: int
    anio: int
    mes: int
    actor_id: int | None
    actor_email: str


def ejecucion_en_curso(company_id: int) -> bool:
    with _LOCK:
        return int(company_id) in _RUNNING


def puede_continuar(company_id: int, ejecucion_id: int) -> bool:
    with _LOCK:
        return (int(company_id), int(ejecucion_id)) in _SLOTS


def continuar_ejecucion(company_id: int, ejecucion_id: int) -> bool:
    with _LOCK:
        evento = _SLOTS.get((int(company_id), int(ejecucion_id)))
    if evento is None:
        return False
    evento.set()
    return True


def iniciar_actualizacion(
    db: Session,
    *,
    session_factory,
    company_id: int,
    company_name: str,
    rut: str,
    actor_id: int | None,
    actor_email: str,
    anio: int,
    mes: int,
    autenticado: bool,
    puede_actualizar: bool,
    descargar: Descargador | None = None,
) -> int:
    if ejecucion_en_curso(company_id):
        raise TesoreriaError("Ya hay una actualización con el SII en curso para esta empresa.")
    credencial = crud_sii.obtener_credencial_publica(db) or {}
    pre = validar_precondiciones(
        autenticado=autenticado,
        puede_actualizar=puede_actualizar,
        company_id=company_id,
        rut_empresa=rut,
        anio=anio,
        mes=mes,
        tiene_credencial=bool(credencial.get("tiene_secreto")),
        rut_credencial=str(credencial.get("rut") or ""),
        hay_ejecucion_activa=False,
        esquema_listo=crud_sii.esquema_listo(db),
    )
    if not pre.ok:
        raise TesoreriaError(pre.mensaje)
    from core.paths import operational_storage

    destino = operational_storage("sii", str(int(company_id)), f"{int(anio):04d}-{int(mes):02d}")
    destino.mkdir(parents=True, exist_ok=True)
    crud_sii.cerrar_ejecuciones_stale(db, company_id, minutos=0)
    db.commit()
    if crud_sii.hay_ejecucion_activa(db, company_id):
        raise TesoreriaError("Ya hay una actualización con el SII en curso para esta empresa.")
    try:
        ejecucion_id = crud_sii.crear_ejecucion(
            db,
            company_id=company_id,
            actor_id=actor_id,
            actor_email=actor_email,
            anio=anio,
            mes=mes,
        )
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        detalle = str(exc).lower()
        if getattr(getattr(exc, "orig", None), "sqlstate", None) == "23505" or any(
            token in detalle for token in ("unique", "unicidad", "duplicad")
        ):
            raise TesoreriaError("Ya hay una actualización con el SII en curso para esta empresa.") from exc
        logger.exception("SII | empresa=%s | no se pudo abrir la ejecución", company_id)
        raise TesoreriaError(
            "No se pudo iniciar la actualización con el SII. "
            "La base de la empresa no aceptó el registro de la ejecución."
        ) from exc
    solicitud = Solicitud(
        company_id=int(company_id),
        company_name=company_name,
        rut=rut,
        ejecucion_id=ejecucion_id,
        anio=int(anio),
        mes=int(mes),
        actor_id=actor_id,
        actor_email=actor_email,
    )
    threading.Thread(
        target=_hilo,
        name=f"sii-rcv-{company_id}-{ejecucion_id}",
        kwargs={
            "session_factory": session_factory,
            "solicitud": solicitud,
            "destino": destino,
            "descargar": descargar,
        },
        daemon=True,
    ).start()
    return ejecucion_id


def _hilo(*, session_factory, solicitud: Solicitud, destino: Path, descargar: Descargador | None) -> None:
    with _LOCK:
        _RUNNING.add(solicitud.company_id)
    db = session_factory()
    try:
        correr_actualizacion(db, solicitud, destino=destino, descargar=descargar)
    except Exception:
        logger.exception(
            "SII | empresa=%s | ejecución=%s | error no controlado",
            solicitud.company_id,
            solicitud.ejecucion_id,
        )
    finally:
        db.close()
        with _LOCK:
            _RUNNING.discard(solicitud.company_id)
            _SLOTS.pop((solicitud.company_id, solicitud.ejecucion_id), None)


def correr_actualizacion(
    db: Session,
    solicitud: Solicitud,
    *,
    destino: Path,
    descargar: Descargador | None = None,
) -> None:
    clave = ""
    try:
        def on_step(codigo: str) -> None:
            crud_sii.marcar_paso(
                db,
                solicitud.ejecucion_id,
                solicitud.company_id,
                codigo,
                _ESTADO_PASO.get(codigo, "EN_PROCESO"),
            )
            db.commit()

        def al_intervenir(mensaje: str) -> bool:
            evento = threading.Event()
            with _LOCK:
                _SLOTS[(solicitud.company_id, solicitud.ejecucion_id)] = evento
            crud_sii.cerrar_ejecucion(
                db,
                ejecucion_id=solicitud.ejecucion_id,
                company_id=solicitud.company_id,
                estado="REQUIERE_INTERVENCION_USUARIO",
                stats=_stats_cero(),
                error_publico=mensaje,
            )
            db.commit()
            return evento.wait(timeout=180)

        cifrado = crud_sii.leer_secreto_cifrado(db)
        clave = decrypt_secret(cifrado)
        argumentos = dict(
            rut=solicitud.rut,
            clave=clave,
            anio=solicitud.anio,
            mes=solicitud.mes,
            dest=destino,
            company_id=solicitud.company_id,
            ejecucion_id=solicitud.ejecucion_id,
            on_step=on_step,
            al_intervenir=al_intervenir,
        )
        if descargar is None:
            bajada = descargar_libros(_runtime(), **argumentos)
        else:
            bajada = descargar(None, **argumentos)
        compras = _filas(bajada.compras, "RECIBIDO", solicitud, "Procesando compras")
        ventas = _filas(bajada.ventas, "EMITIDO", solicitud, "Procesando ventas")
        _registrar_si_hay(db, solicitud, "COMPRAS", bajada.compras)
        _registrar_si_hay(db, solicitud, "VENTAS", bajada.ventas)
        db.commit()
        on_step("importacion")
        stats_compras = _importar(db, compras, solicitud.ejecucion_id)
        stats_ventas = _importar(db, ventas, solicitud.ejecucion_id)
        estado = (
            "COMPLETADO"
            if stats_compras["errores"] == 0 and stats_ventas["errores"] == 0
            else "COMPLETADO_CON_OBSERVACIONES"
        )
        crud_sii.cerrar_ejecucion(
            db,
            ejecucion_id=solicitud.ejecucion_id,
            company_id=solicitud.company_id,
            estado=estado,
            stats=_stats(stats_compras, stats_ventas),
        )
        _auditar(db, solicitud, estado, stats_compras, stats_ventas)
        db.commit()
        logger.info(
            "SII | empresa=%s | ejecución=%s | importación completada",
            solicitud.company_id,
            solicitud.ejecucion_id,
        )
    except Exception as exc:
        db.rollback()
        logger.exception(
            "SII | empresa=%s | ejecución=%s | falló la actualización",
            solicitud.company_id,
            solicitud.ejecucion_id,
        )
        _marcar_falla(db, solicitud, exc, clave)
    finally:
        clave = ""


def _filas(path: Path | None, direccion: str, solicitud: Solicitud, etapa: str) -> list:
    if path is None:
        return []
    try:
        tabla = leer_tabla(path)
        return normalizar_tabla(
            tabla,
            direccion=direccion,
            rut_empresa=solicitud.rut,
            anio=solicitud.anio,
            mes=solicitud.mes,
        )
    except EstructuraInvalida as exc:
        raise EstructuraInvalida(exc.detalle, etapa=etapa) from exc


def _importar(db: Session, filas: list, ejecucion_id: int) -> dict[str, int]:
    importados = omitidos = errores = 0
    for fila in filas:
        if fila.documento is None:
            errores += 1
            continue
        crud_sii.asegurar_contraparte(db, fila.documento)
        if crud_sii.insertar_si_nuevo(db, fila.documento, ejecucion_id=ejecucion_id) == "importado":
            importados += 1
        else:
            omitidos += 1
    return {
        "encontrados": len(filas),
        "importados": importados,
        "omitidos": omitidos,
        "errores": errores,
    }


def _marcar_falla(db: Session, solicitud: Solicitud, exc: Exception, clave: str) -> None:
    if isinstance(exc, SiiEtapaError):
        publico = mensaje_publico(exc.etapa, exc.detalle)
        tecnico = scrub(f"{type(exc).__name__}: {exc.detalle}", clave)
        estado = "REQUIERE_INTERVENCION_USUARIO" if exc.__class__.__name__ == "SiiIntervencionRequerida" else "ERROR"
    elif isinstance(exc, SiiCryptoError):
        publico = mensaje_publico("Configuración SII", str(exc))
        tecnico = scrub(exc.__class__.__name__, clave)
        estado = "ERROR"
    else:
        publico = mensaje_publico(
            "Importación",
            "Ocurrió un error interno al procesar los libros. El detalle quedó en el registro de la ejecución.",
        )
        tecnico = scrub(f"{type(exc).__name__}: {exc}", clave)
        estado = "ERROR"
    try:
        crud_sii.cerrar_ejecucion(
            db,
            ejecucion_id=solicitud.ejecucion_id,
            company_id=solicitud.company_id,
            estado=estado,
            stats=_stats_cero(),
            error_publico=publico,
            error_tecnico=tecnico,
        )
        db.commit()
    except Exception:
        db.rollback()
        logger.exception(
            "SII | empresa=%s | ejecución=%s | no se pudo registrar el error",
            solicitud.company_id,
            solicitud.ejecucion_id,
        )


def _registrar_si_hay(db: Session, solicitud: Solicitud, tipo: str, path: Path | None) -> None:
    if path is None or not path.is_file():
        return
    contenido = path.read_bytes()
    try:
        ruta = str(path.resolve().relative_to(PROJECT_ROOT))
    except ValueError:
        ruta = str(path.resolve())
    crud_sii.registrar_archivo(
        db,
        ejecucion_id=solicitud.ejecucion_id,
        company_id=solicitud.company_id,
        tipo=tipo,
        nombre=path.name,
        anio=solicitud.anio,
        mes=solicitud.mes,
        sha256=hashlib.sha256(contenido).hexdigest(),
        tamano=len(contenido),
        ruta=ruta,
    )


def _auditar(db: Session, solicitud: Solicitud, estado: str, compras: dict, ventas: dict) -> None:
    try:
        from services.audit.financial import audit_financial_fact

        audit_financial_fact(
            db,
            action="SII_RCV_IMPORT",
            module="tesoreria",
            entity="sii_ejecucion",
            entity_id=solicitud.ejecucion_id,
            actor_id=solicitud.actor_id,
            company_id=solicitud.company_id,
            result="ok" if estado == "COMPLETADO" else "observado",
            detail={
                "periodo": f"{solicitud.anio:04d}-{solicitud.mes:02d}",
                "compras_importados": compras["importados"],
                "compras_omitidos": compras["omitidos"],
                "ventas_importados": ventas["importados"],
                "ventas_omitidos": ventas["omitidos"],
            },
        )
    except Exception:
        logger.exception(
            "SII | empresa=%s | ejecución=%s | auditoría no registrada",
            solicitud.company_id,
            solicitud.ejecucion_id,
        )


def _runtime() -> SiiRuntime:
    from core.config import settings

    return SiiRuntime(
        login_url=settings.sii_login_url,
        rcv_url=settings.sii_rcv_url,
        headless=settings.sii_headless,
        timeout_ms=settings.sii_timeout_seconds * 1000,
        download_timeout_ms=settings.sii_download_timeout_seconds * 1000,
    )


def _stats(compras: dict[str, int], ventas: dict[str, int]) -> dict[str, int]:
    return {
        "compras_encontrados": compras["encontrados"],
        "compras_importados": compras["importados"],
        "compras_omitidos": compras["omitidos"],
        "compras_errores": compras["errores"],
        "ventas_encontrados": ventas["encontrados"],
        "ventas_importados": ventas["importados"],
        "ventas_omitidos": ventas["omitidos"],
        "ventas_errores": ventas["errores"],
    }


def _stats_cero() -> dict[str, int]:
    return _stats(
        {"encontrados": 0, "importados": 0, "omitidos": 0, "errores": 0},
        {"encontrados": 0, "importados": 0, "omitidos": 0, "errores": 0},
    )
