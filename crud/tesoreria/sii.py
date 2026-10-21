# crud/tesoreria/sii.py
# -*- coding: utf-8 -*-
"""Persistencia de Tesorería. Recibe la Session de la empresa activa."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import text
from sqlalchemy.orm import Session

_ESTADOS_ACTIVOS = (
    "PENDIENTE",
    "EN_PROCESO",
    "DESCARGANDO_COMPRAS",
    "DESCARGANDO_VENTAS",
    "PROCESANDO_COMPRAS",
    "PROCESANDO_VENTAS",
    "IMPORTANDO",
)
_ACTIVOS_SQL = ", ".join(f"'{estado}'" for estado in _ESTADOS_ACTIVOS)

_PASOS = (
    ("conexion", "Conexión iniciada"),
    ("auth", "Autenticación"),
    ("periodo", "Período seleccionado"),
    ("compras", "Compras descargadas"),
    ("ventas", "Ventas descargadas"),
    ("importacion", "Importación"),
)


def pasos_iniciales() -> str:
    return json.dumps(
        [{"codigo": codigo, "etiqueta": etiqueta, "estado": "pendiente"} for codigo, etiqueta in _PASOS],
        ensure_ascii=False,
    )


def esquema_listo(db: Session) -> bool:
    bind = db.get_bind()
    if bind is None or getattr(bind.dialect, "name", "") != "postgresql":
        return False
    ejecucion = db.execute(text("SELECT to_regclass('fin.sii_ejecucion')")).scalar()
    if ejecucion is None:
        return False
    columna = db.execute(
        text(
            """
            SELECT 1
            FROM information_schema.columns
            WHERE table_schema = 'fin'
              AND table_name = 'documento_tributario'
              AND column_name = 'exento'
            """
        )
    ).scalar()
    return columna is not None


def obtener_credencial_publica(db: Session) -> dict | None:
    if not _tabla(db, "fin.sii_credencial"):
        return None
    row = db.execute(
        text(
            """
            SELECT id, rut, usuario, estado, updated_at,
                   (COALESCE(secreto_cifrado, '') <> '') AS tiene_secreto
            FROM fin.sii_credencial
            WHERE id = 1
            """
        )
    ).mappings().first()
    return dict(row) if row else None


def leer_secreto_cifrado(db: Session) -> str:
    row = db.execute(
        text("SELECT secreto_cifrado FROM fin.sii_credencial WHERE id = 1")
    ).scalar()
    return str(row or "")


def guardar_credencial(
    db: Session,
    *,
    rut: str,
    usuario: str,
    secreto_cifrado: str | None,
    actor_id: int | None,
) -> None:
    actual = leer_secreto_cifrado(db) if _tabla(db, "fin.sii_credencial") else ""
    secreto = actual if secreto_cifrado is None else secreto_cifrado
    estado = "CONFIGURADA" if secreto else "INCOMPLETA"
    db.execute(
        text(
            """
            INSERT INTO fin.sii_credencial (
                id, rut, usuario, secreto_cifrado, estado, updated_at, updated_by
            )
            VALUES (1, :rut, :usuario, :secreto, :estado, now(), :actor)
            ON CONFLICT (id) DO UPDATE SET
                rut = EXCLUDED.rut,
                usuario = EXCLUDED.usuario,
                secreto_cifrado = EXCLUDED.secreto_cifrado,
                estado = EXCLUDED.estado,
                updated_at = now(),
                updated_by = EXCLUDED.updated_by
            """
        ),
        {
            "rut": rut[:20],
            "usuario": usuario[:32],
            "secreto": secreto,
            "estado": estado,
            "actor": actor_id,
        },
    )


def cerrar_ejecuciones_stale(db: Session, company_id: int, *, minutos: int = 20) -> None:
    db.execute(
        text(
            f"""
            UPDATE fin.sii_ejecucion
            SET estado = 'ERROR',
                fin_at = now(),
                error_publico = :mensaje
            WHERE company_id = :company_id
              AND estado IN ({_ACTIVOS_SQL})
              AND (
                    inicio_at IS NULL
                    OR inicio_at < now() - make_interval(mins => :minutos)
              )
            """
        ),
        {
            "company_id": int(company_id),
            "minutos": int(minutos),
            "mensaje": (
                "La actualización anterior se interrumpió antes de terminar. "
                "No se importaron documentos de esa ejecución."
            ),
        },
    )


def hay_ejecucion_activa(db: Session, company_id: int) -> bool:
    row = db.execute(
        text(
            f"""
            SELECT 1
            FROM fin.sii_ejecucion
            WHERE company_id = :company_id
              AND estado IN ({_ACTIVOS_SQL})
            LIMIT 1
            """
        ),
        {"company_id": int(company_id)},
    ).first()
    return row is not None


def crear_ejecucion(
    db: Session,
    *,
    company_id: int,
    actor_id: int | None,
    actor_email: str,
    anio: int,
    mes: int,
) -> int:
    row = db.execute(
        text(
            """
            INSERT INTO fin.sii_ejecucion (
                company_id, actor_id, actor_email, periodo_anio, periodo_mes,
                tipo_integracion, estado, pasos, inicio_at,
                compras_encontrados, compras_importados, compras_omitidos, compras_errores,
                ventas_encontrados, ventas_importados, ventas_omitidos, ventas_errores
            )
            VALUES (
                :company_id, :actor_id, :actor_email, :anio, :mes,
                'SII', 'EN_PROCESO', :pasos, now(),
                0, 0, 0, 0,
                0, 0, 0, 0
            )
            RETURNING id
            """
        ),
        {
            "company_id": int(company_id),
            "actor_id": actor_id,
            "actor_email": (actor_email or "")[:254],
            "anio": int(anio),
            "mes": int(mes),
            "pasos": pasos_iniciales(),
        },
    ).scalar()
    return int(row)


def obtener_ejecucion(db: Session, ejecucion_id: int, company_id: int) -> dict | None:
    row = db.execute(
        text(
            """
            SELECT id, company_id, actor_id, actor_email, periodo_anio, periodo_mes,
                   tipo_integracion, estado, pasos, inicio_at, fin_at,
                   compras_encontrados, compras_importados, compras_omitidos, compras_errores,
                   ventas_encontrados, ventas_importados, ventas_omitidos, ventas_errores,
                   error_publico, error_tecnico
            FROM fin.sii_ejecucion
            WHERE id = :id
              AND company_id = :company_id
            """
        ),
        {"id": int(ejecucion_id), "company_id": int(company_id)},
    ).mappings().first()
    return dict(row) if row else None


def listar_ejecuciones(db: Session, company_id: int, *, limit: int = 8) -> list[dict]:
    rows = db.execute(
        text(
            """
            SELECT id, estado, periodo_anio, periodo_mes, inicio_at, fin_at,
                   compras_importados, ventas_importados
            FROM fin.sii_ejecucion
            WHERE company_id = :company_id
            ORDER BY id DESC
            LIMIT :limit
            """
        ),
        {"company_id": int(company_id), "limit": int(limit)},
    ).mappings()
    return [dict(row) for row in rows]


def marcar_paso(db: Session, ejecucion_id: int, company_id: int, codigo: str, estado_ejecucion: str) -> None:
    row = obtener_ejecucion(db, ejecucion_id, company_id)
    if row is None:
        return
    try:
        pasos = json.loads(row.get("pasos") or "[]")
    except json.JSONDecodeError:
        pasos = []
    visto = False
    for paso in pasos:
        if paso.get("codigo") == codigo:
            paso["estado"] = "actual"
            visto = True
        elif not visto and paso.get("estado") != "error":
            paso["estado"] = "ok"
    db.execute(
        text(
            """
            UPDATE fin.sii_ejecucion
            SET estado = :estado, pasos = :pasos
            WHERE id = :id AND company_id = :company_id
            """
        ),
        {
            "estado": estado_ejecucion,
            "pasos": json.dumps(pasos, ensure_ascii=False),
            "id": int(ejecucion_id),
            "company_id": int(company_id),
        },
    )


def cerrar_ejecucion(
    db: Session,
    *,
    ejecucion_id: int,
    company_id: int,
    estado: str,
    stats: dict,
    error_publico: str | None = None,
    error_tecnico: str | None = None,
) -> None:
    row = obtener_ejecucion(db, ejecucion_id, company_id)
    pasos = []
    if row is not None:
        try:
            pasos = json.loads(row.get("pasos") or "[]")
        except json.JSONDecodeError:
            pasos = []
    marca = "error" if estado == "ERROR" else "ok"
    for paso in pasos:
        if paso.get("estado") != "ok":
            paso["estado"] = marca
    db.execute(
        text(
            """
            UPDATE fin.sii_ejecucion
            SET estado = :estado,
                fin_at = :fin_at,
                pasos = :pasos,
                compras_encontrados = :compras_encontrados,
                compras_importados = :compras_importados,
                compras_omitidos = :compras_omitidos,
                compras_errores = :compras_errores,
                ventas_encontrados = :ventas_encontrados,
                ventas_importados = :ventas_importados,
                ventas_omitidos = :ventas_omitidos,
                ventas_errores = :ventas_errores,
                error_publico = :error_publico,
                error_tecnico = :error_tecnico
            WHERE id = :id AND company_id = :company_id
            """
        ),
        {
            "estado": estado,
            "fin_at": None if estado == "REQUIERE_INTERVENCION_USUARIO" else datetime.now(timezone.utc),
            "pasos": json.dumps(pasos, ensure_ascii=False),
            "id": int(ejecucion_id),
            "company_id": int(company_id),
            "error_publico": error_publico,
            "error_tecnico": (error_tecnico or "")[:2000] or None,
            **stats,
        },
    )


def registrar_archivo(
    db: Session,
    *,
    ejecucion_id: int,
    company_id: int,
    tipo: str,
    nombre: str,
    anio: int,
    mes: int,
    sha256: str,
    tamano: int,
    ruta: str,
) -> None:
    db.execute(
        text(
            """
            INSERT INTO fin.sii_archivo (
                ejecucion_id, tipo, nombre_archivo, periodo_anio, periodo_mes,
                company_id, descargado_at, sha256, tamano_bytes, ruta
            )
            VALUES (
                :ejecucion_id, :tipo, :nombre, :anio, :mes,
                :company_id, now(), :sha256, :tamano, :ruta
            )
            """
        ),
        {
            "ejecucion_id": int(ejecucion_id),
            "tipo": tipo,
            "nombre": nombre[:255],
            "anio": int(anio),
            "mes": int(mes),
            "company_id": int(company_id),
            "sha256": sha256,
            "tamano": int(tamano),
            "ruta": ruta[:500],
        },
    )


def _rut_compacto(rut: str) -> str:
    return str(rut or "").replace(".", "").replace("-", "").replace(" ", "").upper()


def contraparte_de_documento(doc) -> tuple[str, str, str] | None:
    """Compra: proveedor emisor. Venta: cliente receptor. No duplica a la propia empresa."""
    if doc.direccion == "RECIBIDO":
        tabla, rut, propio = "proveedor", doc.rut_emisor, doc.rut_receptor
    elif doc.direccion == "EMITIDO":
        tabla, rut, propio = "cliente", doc.rut_receptor, doc.rut_emisor
    else:
        return None
    if not _rut_compacto(rut) or _rut_compacto(rut) == _rut_compacto(propio):
        return None
    razon = (doc.razon_social or "").strip() or rut
    return tabla, rut, razon[:180]


def _tipo_persona(rut: str) -> str:
    cuerpo = rut.split("-", 1)[0].replace(".", "")
    if cuerpo.isdigit() and int(cuerpo) >= 50_000_000:
        return "JURIDICA"
    return "NATURAL"


def asegurar_contraparte(db: Session, doc) -> None:
    """Crea el proveedor o el cliente si el RUT todavía no existe. No hace commit."""
    bind = db.get_bind()
    if bind is None or getattr(bind.dialect, "name", "") != "postgresql":
        return
    destino = contraparte_de_documento(doc)
    if destino is None:
        return
    tabla, rut, razon = destino
    compacto = _rut_compacto(rut)
    if tabla == "proveedor":
        existe = db.execute(
            text(
                """
                SELECT 1
                FROM public.proveedor
                WHERE replace(replace(upper(rut), '.', ''), '-', '') = :compacto
                   OR COALESCE(rut_normalizado, '') = :compacto
                LIMIT 1
                """
            ),
            {"compacto": compacto},
        ).first()
        if existe:
            return
        db.execute(
            text(
                """
                INSERT INTO public.proveedor (rut, razon_social)
                VALUES (:rut, :razon)
                """
            ),
            {"rut": rut[:20], "razon": razon[:180]},
        )
        return
    existe = db.execute(
        text(
            """
            SELECT 1
            FROM public.clientes
            WHERE replace(replace(upper(rut), '.', ''), '-', '') = :compacto
            LIMIT 1
            """
        ),
        {"compacto": compacto},
    ).first()
    if existe:
        return
    db.execute(
        text(
            """
            INSERT INTO public.clientes (
                rut, tipo_persona, razon_social, activo, fecha_creacion, fecha_actualizacion
            )
            VALUES (:rut, :tipo, :razon, true, now(), now())
            """
        ),
        {"rut": rut[:20], "tipo": _tipo_persona(rut), "razon": razon[:200]},
    )


def insertar_si_nuevo(db: Session, doc, *, ejecucion_id: int) -> str:
    """Inserta el documento. Devuelve importado u omitido. No hace commit."""
    row = db.execute(
        text(
            """
            INSERT INTO fin.documento_tributario (
                direccion, tipo, folio, rut_emisor, rut_receptor, razon_social,
                fecha_emision, neto, iva, total, moneda, asiento_id, origen_tipo, origen_id,
                exento, otros, fecha_recepcion, estado_sii, periodo_anio, periodo_mes, ejecucion_sii_id
            )
            VALUES (
                :direccion, :tipo, :folio, :rut_emisor, :rut_receptor, :razon_social,
                :fecha_emision, :neto, :iva, :total, 'CLP', NULL, 'SII_RCV', :origen_id,
                :exento, :otros, :fecha_recepcion, :estado_sii, :periodo_anio, :periodo_mes, :ejecucion_id
            )
            ON CONFLICT (direccion, tipo, folio, rut_emisor) DO NOTHING
            RETURNING id
            """
        ),
        {
            "direccion": doc.direccion,
            "tipo": doc.tipo,
            "folio": doc.folio,
            "rut_emisor": doc.rut_emisor,
            "rut_receptor": doc.rut_receptor,
            "razon_social": doc.razon_social,
            "fecha_emision": doc.fecha_emision,
            "neto": str(doc.neto),
            "iva": str(doc.iva),
            "total": str(doc.total),
            "origen_id": int(ejecucion_id),
            "exento": str(doc.exento),
            "otros": str(doc.otros),
            "fecha_recepcion": doc.fecha_recepcion,
            "estado_sii": doc.estado,
            "periodo_anio": doc.periodo_anio,
            "periodo_mes": doc.periodo_mes,
            "ejecucion_id": int(ejecucion_id),
        },
    ).first()
    return "importado" if row else "omitido"


def contar_documentos(db: Session) -> int:
    total = db.execute(text("SELECT COUNT(*) FROM fin.documento_tributario")).scalar()
    return int(total or 0)


def resumen_periodo(db: Session, *, direccion: str, anio: int, mes: int) -> dict:
    row = db.execute(
        text(
            """
            SELECT COUNT(*) AS documentos,
                   COALESCE(SUM(neto), 0) AS neto,
                   COALESCE(SUM(exento), 0) AS exento,
                   COALESCE(SUM(iva), 0) AS iva,
                   COALESCE(SUM(total), 0) AS total
            FROM fin.documento_tributario
            WHERE direccion = :direccion
              AND (
                    (periodo_anio = :anio AND periodo_mes = :mes)
                    OR (
                        periodo_anio IS NULL
                        AND EXTRACT(YEAR FROM fecha_emision) = :anio
                        AND EXTRACT(MONTH FROM fecha_emision) = :mes
                    )
              )
            """
        ),
        {"direccion": direccion, "anio": int(anio), "mes": int(mes)},
    ).mappings().first()
    data = dict(row or {})
    for clave in ("neto", "exento", "iva", "total"):
        data[clave] = Decimal(str(data.get(clave) or 0))
    data["documentos"] = int(data.get("documentos") or 0)
    return data


def listar_documentos(db: Session, *, direccion: str, anio: int, mes: int, limit: int = 80) -> list[dict]:
    rows = db.execute(
        text(
            """
            SELECT folio, tipo, rut_emisor, rut_receptor, razon_social, fecha_emision,
                   neto, exento, iva, total, estado_sii
            FROM fin.documento_tributario
            WHERE direccion = :direccion
              AND (
                    (periodo_anio = :anio AND periodo_mes = :mes)
                    OR (
                        periodo_anio IS NULL
                        AND EXTRACT(YEAR FROM fecha_emision) = :anio
                        AND EXTRACT(MONTH FROM fecha_emision) = :mes
                    )
              )
            ORDER BY fecha_emision, folio
            LIMIT :limit
            """
        ),
        {"direccion": direccion, "anio": int(anio), "mes": int(mes), "limit": int(limit)},
    ).mappings()
    return [dict(row) for row in rows]


def rut_fiscal_de_la_base(db: Session) -> str:
    """RUT legal guardado en la base que esta sesión tiene abierta."""
    bind = db.get_bind()
    if bind is None or getattr(bind.dialect, "name", "") != "postgresql":
        return ""
    if db.execute(text("SELECT to_regclass('public.empresa')")).scalar() is None:
        return ""
    row = db.execute(
        text(
            """
            SELECT rut
            FROM public.empresa
            WHERE COALESCE(activo, true) IS TRUE
              AND btrim(COALESCE(rut, '')) <> ''
            ORDER BY id
            LIMIT 1
            """
        )
    ).scalar()
    return str(row or "")


def _tabla(db: Session, nombre: str) -> bool:
    bind = db.get_bind()
    if bind is None or getattr(bind.dialect, "name", "") != "postgresql":
        return True
    return db.execute(text("SELECT to_regclass(:nombre)"), {"nombre": nombre}).scalar() is not None
