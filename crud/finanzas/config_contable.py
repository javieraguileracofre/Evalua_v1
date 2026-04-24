# crud/finanzas/config_contable.py
# -*- coding: utf-8 -*-
from __future__ import annotations

from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session


def obtener_configuracion_evento(
    db: Session,
    *,
    codigo_evento: str,
) -> list[dict[str, Any]]:
    query = text(
        """
        SELECT
            codigo_evento,
            nombre_evento,
            lado,
            codigo_cuenta,
            nombre_cuenta,
            tipo,
            clasificacion,
            orden,
            requiere_centro_costo,
            requiere_documento,
            estado,
            descripcion
        FROM fin.vw_config_contable
        WHERE codigo_evento = :codigo_evento
          AND estado = 'ACTIVO'
        ORDER BY
            CASE WHEN lado = 'DEBE' THEN 1 ELSE 2 END,
            orden
        """
    )
    rows = db.execute(query, {"codigo_evento": codigo_evento}).mappings().all()
    return [dict(r) for r in rows]


def obtener_configuracion_evento_modulo(
    db: Session,
    *,
    modulo: str,
    submodulo: str | None = None,
    tipo_documento: str | None = None,
    codigo_evento: str | None = None,
) -> list[dict[str, Any]]:
    conditions = ["modulo = :modulo", "estado = 'ACTIVO'"]
    params: dict[str, Any] = {"modulo": modulo}

    if submodulo is not None:
        conditions.append("submodulo = :submodulo")
        params["submodulo"] = submodulo

    if tipo_documento is not None:
        conditions.append("tipo_documento = :tipo_documento")
        params["tipo_documento"] = tipo_documento

    if codigo_evento is not None:
        conditions.append("codigo_evento = :codigo_evento")
        params["codigo_evento"] = codigo_evento

    query = text(
        f"""
        SELECT
            modulo,
            submodulo,
            tipo_documento,
            codigo_evento,
            nombre_evento,
            lado,
            codigo_cuenta,
            nombre_cuenta,
            tipo,
            clasificacion,
            orden,
            requiere_centro_costo,
            requiere_documento,
            requiere_cliente,
            requiere_proveedor,
            estado,
            descripcion
        FROM fin.vw_config_contable_modulo
        WHERE {" AND ".join(conditions)}
        ORDER BY
            CASE WHEN lado = 'DEBE' THEN 1 ELSE 2 END,
            orden
        """
    )

    rows = db.execute(query, params).mappings().all()
    return [dict(r) for r in rows]