# services/tesoreria/precondiciones.py
# -*- coding: utf-8 -*-
"""Validaciones previas a conectar con el SII. No abre el navegador."""
from __future__ import annotations

from dataclasses import dataclass

from integrations.sii.rut import normalizar_rut, ruts_coinciden, rut_es_valido

ESTADOS_ACTIVOS = (
    "PENDIENTE",
    "EN_PROCESO",
    "DESCARGANDO_COMPRAS",
    "DESCARGANDO_VENTAS",
    "PROCESANDO_COMPRAS",
    "PROCESANDO_VENTAS",
    "IMPORTANDO",
)

ESTADOS_TERMINALES = (
    "COMPLETADO",
    "COMPLETADO_CON_OBSERVACIONES",
    "ERROR",
)


@dataclass(frozen=True)
class Precheck:
    ok: bool
    mensaje: str = ""


def parse_periodo(value: str) -> tuple[int, int]:
    texto = (value or "").strip()
    partes = texto.split("-")
    if len(partes) != 2:
        raise ValueError("Seleccione un período con año y mes.")
    anio = int(partes[0])
    mes = int(partes[1])
    if anio < 2000 or anio > 2100 or mes < 1 or mes > 12:
        raise ValueError("El período está fuera del rango permitido.")
    return anio, mes


def rut_de_empresa_activa(*, por_base: bool, rut_contexto: str, rut_legado: str) -> str:
    """En multiempresa solo vale el RUT de la compañía autorizada."""
    if por_base:
        return normalizar_rut(rut_contexto)
    return normalizar_rut(rut_legado)


def rut_para_consulta_sii(*, rut_base: str, rut_contexto: str) -> str:
    """El RUT que se envía al SII es el de la base de datos abierta."""
    base = normalizar_rut(rut_base)
    contexto = normalizar_rut(rut_contexto)
    if base and rut_es_valido(base):
        if contexto and rut_es_valido(contexto) and not ruts_coinciden(base, contexto):
            raise ValueError(
                f"La base de datos abierta pertenece al RUT {base}, "
                f"pero la empresa activa figura con el RUT {contexto}. "
                "No se consultará el SII."
            )
        return base
    if contexto and rut_es_valido(contexto):
        return contexto
    raise ValueError("La empresa abierta no tiene un RUT válido para consultar el SII.")


def validar_precondiciones(
    *,
    autenticado: bool,
    puede_actualizar: bool,
    company_id: int | None,
    rut_empresa: str,
    anio: int,
    mes: int,
    tiene_credencial: bool,
    rut_credencial: str,
    hay_ejecucion_activa: bool,
    esquema_listo: bool,
) -> Precheck:
    if not autenticado:
        return Precheck(False, "Debe iniciar sesión para actualizar compras y ventas.")
    if not puede_actualizar:
        return Precheck(
            False,
            "No tiene permiso para actualizar compras y ventas. Se requiere rol Finanzas o Administrador.",
        )
    if company_id is None:
        return Precheck(False, "No hay una empresa activa.")
    if not esquema_listo:
        return Precheck(
            False,
            "Falta aplicar la migración de Tesorería (0013_tesoreria_sii) en la base de la empresa.",
        )
    if anio < 2000 or anio > 2100 or mes < 1 or mes > 12:
        return Precheck(False, "Seleccione un período válido.")
    rut = normalizar_rut(rut_empresa)
    if not rut or not rut_es_valido(rut):
        return Precheck(False, "La empresa activa no tiene un RUT válido para consultar el SII.")
    if not tiene_credencial:
        return Precheck(False, "La empresa activa no tiene credenciales SII configuradas.")
    if not ruts_coinciden(rut, rut_credencial):
        return Precheck(
            False,
            "La credencial SII no corresponde al RUT de la empresa activa. No se consultará otra empresa.",
        )
    if hay_ejecucion_activa:
        return Precheck(False, "Ya hay una actualización con el SII en curso para esta empresa.")
    return Precheck(True)
