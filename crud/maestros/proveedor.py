# crud/maestros/proveedor.py
# -*- coding: utf-8 -*-
from __future__ import annotations

from typing import Any, Optional

from sqlalchemy import text
from sqlalchemy.orm import Session, joinedload

from crud.finanzas.cxp_montos_sql import cxp_sql_suma_saldo_por_proveedor
from models.maestros.proveedor import (
    Proveedor,
    ProveedorBanco,
    ProveedorContacto,
    ProveedorDireccion,
)
from schemas.maestros.proveedor import ProveedorCreate, ProveedorUpdate


def _rut_normalizado(rut: str | None) -> str:
    if not rut:
        return ""
    return (
        str(rut)
        .replace(".", "")
        .replace("-", "")
        .replace(" ", "")
        .strip()
        .upper()
    )


def _clean_str(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


class ProveedorCRUD:
    # ============================================================
    # HELPERS
    # ============================================================

    def _get_fin_estado_labels(self, db: Session) -> set[str]:
        rows = db.execute(
            text(
                """
                SELECT e.enumlabel
                FROM pg_type t
                JOIN pg_namespace n
                  ON n.oid = t.typnamespace
                JOIN pg_enum e
                  ON e.enumtypid = t.oid
                WHERE n.nspname = 'fin'
                  AND t.typname = 'estado_simple'
                ORDER BY e.enumsortorder
                """
            )
        ).scalars().all()
        return set(rows)

    def _fin_estado_from_activo(self, db: Session, activo: bool) -> str:
        labels = self._get_fin_estado_labels(db)

        if not labels:
            return "ACTIVO" if activo else "INACTIVO"

        if activo:
            if "ACTIVO" in labels:
                return "ACTIVO"
            return next(iter(labels))

        if "INACTIVO" in labels:
            return "INACTIVO"
        if "BLOQUEADO" in labels:
            return "BLOQUEADO"
        return "ACTIVO"

    def _sync_fin_proveedor(self, db: Session, proveedor_id: int) -> None:
        row = db.execute(
            text(
                """
                SELECT
                    id,
                    rut,
                    razon_social,
                    nombre_fantasia,
                    giro,
                    email,
                    telefono,
                    sitio_web,
                    condicion_pago_dias,
                    limite_credito,
                    activo,
                    notas
                FROM public.proveedor
                WHERE id = :id
                """
            ),
            {"id": proveedor_id},
        ).mappings().first()

        if not row:
            return

        fin_id = db.execute(
            text(
                """
                SELECT id
                FROM fin.proveedor_fin
                WHERE proveedor_id = :proveedor_id
                """
            ),
            {"proveedor_id": proveedor_id},
        ).scalar_one_or_none()

        estado_fin = self._fin_estado_from_activo(db, bool(row["activo"]))

        payload = {
            "proveedor_id": row["id"],
            "condicion_pago_dias": row["condicion_pago_dias"],
            "limite_credito": row["limite_credito"],
            "estado": estado_fin,
            "notas": row["notas"],
        }

        if fin_id:
            db.execute(
                text(
                    """
                    UPDATE fin.proveedor_fin
                    SET
                        condicion_pago_dias = :condicion_pago_dias,
                        limite_credito = :limite_credito,
                        estado = CAST(:estado AS fin.estado_simple),
                        notas = :notas,
                        updated_at = now()
                    WHERE id = :id
                    """
                ),
                {
                    **payload,
                    "id": fin_id,
                },
            )
        else:
            db.execute(
                text(
                    """
                    INSERT INTO fin.proveedor_fin (
                        proveedor_id,
                        condicion_pago_dias,
                        limite_credito,
                        estado,
                        notas
                    )
                    VALUES (
                        :proveedor_id,
                        :condicion_pago_dias,
                        :limite_credito,
                        CAST(:estado AS fin.estado_simple),
                        :notas
                    )
                    """
                ),
                payload,
            )

    def _replace_bancos(self, db: Session, proveedor: Proveedor, bancos: list[Any]) -> None:
        # Borrado explícito + flush para evitar choque con unique constraint
        db.query(ProveedorBanco).filter(
            ProveedorBanco.proveedor_id == proveedor.id
        ).delete(synchronize_session=False)
        db.flush()

        seen: set[tuple[str, str, str]] = set()

        for item in bancos:
            banco = _clean_str(item.banco)
            tipo_cuenta = _clean_str(item.tipo_cuenta)
            numero_cuenta = _clean_str(item.numero_cuenta)

            if not banco and not numero_cuenta:
                continue

            key = (banco.upper(), tipo_cuenta.upper(), numero_cuenta.upper())
            if key in seen:
                continue
            seen.add(key)

            db.add(
                ProveedorBanco(
                    proveedor_id=proveedor.id,
                    banco=banco,
                    tipo_cuenta=tipo_cuenta,
                    numero_cuenta=numero_cuenta,
                    titular=_clean_str(item.titular) or None,
                    rut_titular=_clean_str(item.rut_titular) or None,
                    email_pago=_clean_str(item.email_pago) or None,
                    es_principal=bool(item.es_principal),
                    activo=bool(item.activo),
                )
            )

        db.flush()

    def _replace_contactos(self, db: Session, proveedor: Proveedor, contactos: list[Any]) -> None:
        db.query(ProveedorContacto).filter(
            ProveedorContacto.proveedor_id == proveedor.id
        ).delete(synchronize_session=False)
        db.flush()

        seen: set[tuple[str, str, str]] = set()

        for item in contactos:
            nombre = _clean_str(item.nombre)
            cargo = _clean_str(item.cargo)
            email = _clean_str(item.email)

            if not nombre:
                continue

            key = (nombre.upper(), cargo.upper(), email.upper())
            if key in seen:
                continue
            seen.add(key)

            db.add(
                ProveedorContacto(
                    proveedor_id=proveedor.id,
                    nombre=nombre,
                    cargo=cargo or None,
                    email=email or None,
                    telefono=_clean_str(item.telefono) or None,
                    es_principal=bool(item.es_principal),
                    activo=bool(item.activo),
                )
            )

        db.flush()

    def _replace_direcciones(self, db: Session, proveedor: Proveedor, direcciones: list[Any]) -> None:
        db.query(ProveedorDireccion).filter(
            ProveedorDireccion.proveedor_id == proveedor.id
        ).delete(synchronize_session=False)
        db.flush()

        seen: set[tuple[str, str, str, str]] = set()

        for item in direcciones:
            linea1 = _clean_str(item.linea1)
            comuna = _clean_str(item.comuna)
            ciudad = _clean_str(item.ciudad)
            region = _clean_str(item.region)

            if not linea1:
                continue

            key = (
                linea1.upper(),
                comuna.upper(),
                ciudad.upper(),
                region.upper(),
            )
            if key in seen:
                continue
            seen.add(key)

            db.add(
                ProveedorDireccion(
                    proveedor_id=proveedor.id,
                    linea1=linea1,
                    linea2=_clean_str(item.linea2) or None,
                    comuna=comuna or None,
                    ciudad=ciudad or None,
                    region=region or None,
                    pais=_clean_str(item.pais) or "Chile",
                    codigo_postal=_clean_str(item.codigo_postal) or None,
                    es_principal=bool(item.es_principal),
                    activo=bool(item.activo),
                )
            )

        db.flush()

    def _log_evento_fin(
        self,
        db: Session,
        entidad_id: int,
        evento: str,
        detalle: str | None = None,
    ) -> None:
        try:
            db.execute(
                text(
                    """
                    INSERT INTO fin.evento (entidad, entidad_id, evento, detalle)
                    VALUES ('proveedor', :entidad_id, :evento, :detalle)
                    """
                ),
                {
                    "entidad_id": entidad_id,
                    "evento": evento,
                    "detalle": detalle,
                },
            )
        except Exception:
            pass

    # ============================================================
    # QUERIES
    # ============================================================

    def list_proveedores(
        self,
        db: Session,
        *,
        q: Optional[str] = None,
        solo_activos: bool = False,
    ) -> list[dict[str, Any]]:
        filtros = ["1=1"]
        params: dict[str, Any] = {}

        if q:
            q_norm = _rut_normalizado(q)
            filtros.append(
                """
                (
                    p.rut ILIKE :q
                    OR COALESCE(p.rut_normalizado, '') ILIKE :q
                    OR COALESCE(p.rut_normalizado, '') ILIKE :q_norm
                    OR p.razon_social ILIKE :q
                    OR COALESCE(p.nombre_fantasia, '') ILIKE :q
                    OR COALESCE(p.email, '') ILIKE :q
                )
                """
            )
            params["q"] = f"%{q}%"
            params["q_norm"] = f"%{q_norm}%"

        if solo_activos:
            filtros.append("COALESCE(p.activo, true) = true")

        rows = db.execute(
            text(
                f"""
                SELECT
                    p.id,
                    p.rut,
                    p.rut_normalizado,
                    p.razon_social,
                    p.nombre_fantasia,
                    p.giro,
                    p.email,
                    p.telefono,
                    p.sitio_web,
                    p.condicion_pago_dias,
                    p.limite_credito,
                    p.activo,
                    p.notas,
                    p.created_at,
                    p.updated_at,
                    COALESCE((
                        SELECT COUNT(*)
                        FROM public.proveedor_contacto c
                        WHERE c.proveedor_id = p.id
                          AND COALESCE(c.activo, true) = true
                    ), 0) AS contactos_activos,
                    COALESCE((
                        SELECT COUNT(*)
                        FROM public.proveedor_banco b
                        WHERE b.proveedor_id = p.id
                          AND COALESCE(b.activo, true) = true
                    ), 0) AS bancos_activos,
                    COALESCE((
                        SELECT COUNT(*)
                        FROM public.proveedor_direccion d
                        WHERE d.proveedor_id = p.id
                          AND COALESCE(d.activo, true) = true
                    ), 0) AS direcciones_activas,
                    {cxp_sql_suma_saldo_por_proveedor("p.id")} AS saldo_cxp
                FROM public.proveedor p
                WHERE {" AND ".join(filtros)}
                ORDER BY p.razon_social ASC, p.id DESC
                """
            ),
            params,
        ).mappings().all()

        return [dict(x) for x in rows]

    def get_resumen(self, db: Session) -> dict[str, Any]:
        row = db.execute(
            text(
                """
                SELECT
                    COUNT(*)::bigint AS total,
                    COALESCE(SUM(CASE WHEN COALESCE(activo, true) THEN 1 ELSE 0 END), 0)::bigint AS activos,
                    COALESCE(SUM(CASE WHEN COALESCE(activo, true) THEN 0 ELSE 1 END), 0)::bigint AS inactivos,
                    COALESCE(SUM(limite_credito), 0) AS limite_credito_total
                FROM public.proveedor
                """
            )
        ).mappings().first()

        return dict(row) if row else {
            "total": 0,
            "activos": 0,
            "inactivos": 0,
            "limite_credito_total": 0,
        }

    def get_proveedor(self, db: Session, proveedor_id: int) -> Optional[Proveedor]:
        return (
            db.query(Proveedor)
            .options(
                joinedload(Proveedor.bancos),
                joinedload(Proveedor.contactos),
                joinedload(Proveedor.direcciones),
            )
            .filter(Proveedor.id == proveedor_id)
            .first()
        )

    # ============================================================
    # COMMANDS
    # ============================================================

    def create_proveedor(self, db: Session, payload: ProveedorCreate) -> Proveedor:
        try:
            rut_norm = _rut_normalizado(payload.rut)

            existe = db.execute(
                text(
                    """
                    SELECT id
                    FROM public.proveedor
                    WHERE COALESCE(rut_normalizado, '') = :rut_normalizado
                    """
                ),
                {"rut_normalizado": rut_norm},
            ).scalar_one_or_none()

            if existe:
                raise ValueError("Ya existe un proveedor con ese RUT.")

            proveedor = Proveedor(
                rut=payload.rut,
                razon_social=payload.razon_social,
                nombre_fantasia=payload.nombre_fantasia,
                giro=payload.giro,
                email=payload.email,
                telefono=payload.telefono,
                sitio_web=payload.sitio_web,
                condicion_pago_dias=payload.condicion_pago_dias,
                limite_credito=payload.limite_credito,
                activo=payload.activo,
                notas=payload.notas,
            )

            db.add(proveedor)
            db.flush()
            db.refresh(proveedor)

            self._replace_bancos(db, proveedor, payload.bancos)
            self._replace_contactos(db, proveedor, payload.contactos)
            self._replace_direcciones(db, proveedor, payload.direcciones)

            self._sync_fin_proveedor(db, proveedor.id)
            self._log_evento_fin(
                db,
                proveedor.id,
                "PROVEEDOR_CREADO",
                f"Proveedor {proveedor.razon_social} creado desde maestros.",
            )

            db.commit()
            db.refresh(proveedor)
            return proveedor

        except Exception:
            db.rollback()
            raise

    def update_proveedor(self, db: Session, proveedor_id: int, payload: ProveedorUpdate) -> Proveedor:
        try:
            proveedor = self.get_proveedor(db, proveedor_id)
            if not proveedor:
                raise ValueError("Proveedor no encontrado.")

            rut_norm = _rut_normalizado(payload.rut)

            existe = db.execute(
                text(
                    """
                    SELECT id
                    FROM public.proveedor
                    WHERE COALESCE(rut_normalizado, '') = :rut_normalizado
                      AND id <> :id
                    """
                ),
                {"rut_normalizado": rut_norm, "id": proveedor_id},
            ).scalar_one_or_none()

            if existe:
                raise ValueError("Ya existe otro proveedor con ese RUT.")

            proveedor.rut = payload.rut
            proveedor.razon_social = payload.razon_social
            proveedor.nombre_fantasia = payload.nombre_fantasia
            proveedor.giro = payload.giro
            proveedor.email = payload.email
            proveedor.telefono = payload.telefono
            proveedor.sitio_web = payload.sitio_web
            proveedor.condicion_pago_dias = payload.condicion_pago_dias
            proveedor.limite_credito = payload.limite_credito
            proveedor.activo = payload.activo
            proveedor.notas = payload.notas

            db.flush()

            self._replace_bancos(db, proveedor, payload.bancos)
            self._replace_contactos(db, proveedor, payload.contactos)
            self._replace_direcciones(db, proveedor, payload.direcciones)

            self._sync_fin_proveedor(db, proveedor.id)
            self._log_evento_fin(
                db,
                proveedor.id,
                "PROVEEDOR_ACTUALIZADO",
                f"Proveedor {proveedor.razon_social} actualizado desde maestros.",
            )

            db.commit()
            db.refresh(proveedor)
            return proveedor

        except Exception:
            db.rollback()
            raise

    def cambiar_estado(self, db: Session, proveedor_id: int, activo: bool) -> None:
        try:
            proveedor = self.get_proveedor(db, proveedor_id)
            if not proveedor:
                raise ValueError("Proveedor no encontrado.")

            proveedor.activo = activo
            db.flush()

            self._sync_fin_proveedor(db, proveedor.id)
            self._log_evento_fin(
                db,
                proveedor.id,
                "PROVEEDOR_ESTADO",
                f"Nuevo estado activo={activo}",
            )

            db.commit()

        except Exception:
            db.rollback()
            raise

    def delete_proveedor(self, db: Session, proveedor_id: int) -> None:
        try:
            proveedor = self.get_proveedor(db, proveedor_id)
            if not proveedor:
                raise ValueError("Proveedor no encontrado.")

            existe_cxp = db.execute(
                text(
                    """
                    SELECT COUNT(*)
                    FROM fin.ap_documento a
                    WHERE a.proveedor_id = :proveedor_id
                    """
                ),
                {"proveedor_id": proveedor.id},
            ).scalar_one()

            if int(existe_cxp or 0) > 0:
                raise ValueError(
                    "No se puede eliminar el proveedor porque tiene documentos en cuentas por pagar. "
                    "Debes inactivarlo."
                )

            db.execute(
                text(
                    """
                    DELETE FROM fin.proveedor_fin
                    WHERE proveedor_id = :proveedor_id
                    """
                ),
                {"proveedor_id": proveedor.id},
            )

            db.query(ProveedorBanco).filter(
                ProveedorBanco.proveedor_id == proveedor.id
            ).delete(synchronize_session=False)

            db.query(ProveedorContacto).filter(
                ProveedorContacto.proveedor_id == proveedor.id
            ).delete(synchronize_session=False)

            db.query(ProveedorDireccion).filter(
                ProveedorDireccion.proveedor_id == proveedor.id
            ).delete(synchronize_session=False)

            db.flush()
            db.delete(proveedor)
            db.flush()

            db.commit()

        except Exception:
            db.rollback()
            raise


proveedor = ProveedorCRUD()