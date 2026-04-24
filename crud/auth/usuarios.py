# crud/auth/usuarios.py
# -*- coding: utf-8 -*-
from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

import bcrypt
from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from models.auth.usuario import Rol, Usuario

logger = logging.getLogger("evalua.auth")


def contar_usuarios(db: Session) -> int:
    """Total de filas en auth_usuarios (útil para detectar entorno sin bootstrap)."""
    return int(db.scalar(select(func.count()).select_from(Usuario)) or 0)


def hash_password(plain: str) -> str:
    """Hash bcrypt compatible con hashes generados antes con passlib ($2b$...)."""
    pw = (plain or "").encode("utf-8")
    if len(pw) > 72:
        pw = pw[:72]
    return bcrypt.hashpw(pw, bcrypt.gensalt()).decode("ascii")


def verify_password(plain: str, password_hash: str) -> bool:
    """Nunca lanza: hashes desconocidos o corruptos se tratan como inválidos."""
    if not plain or not password_hash:
        return False
    h = str(password_hash).strip()
    if not h:
        return False
    try:
        p = plain.encode("utf-8")
        if len(p) > 72:
            p = p[:72]
        return bcrypt.checkpw(p, h.encode("utf-8"))
    except (ValueError, TypeError):
        return False


def get_usuario_por_email(db: Session, email: str) -> Usuario | None:
    e = (email or "").strip().lower()
    if not e:
        return None
    return db.scalars(
        select(Usuario).options(selectinload(Usuario.roles)).where(Usuario.email == e)
    ).first()


def get_usuario_por_id(db: Session, usuario_id: int) -> Usuario | None:
    return db.scalars(
        select(Usuario).options(selectinload(Usuario.roles)).where(Usuario.id == int(usuario_id))
    ).first()


def listar_usuarios(db: Session, *, limite: int = 300) -> list[Usuario]:
    return list(
        db.scalars(
            select(Usuario)
            .options(selectinload(Usuario.roles))
            .order_by(Usuario.activo.desc(), Usuario.email.asc())
            .limit(max(1, min(int(limite), 500)))
        )
    )


def listar_roles(db: Session) -> list[Rol]:
    return list(db.scalars(select(Rol).order_by(Rol.codigo.asc())))


def contar_admins_activos(db: Session) -> int:
    return int(
        db.scalar(
            select(func.count())
            .select_from(Usuario)
            .where(
                Usuario.activo.is_(True),
                Usuario.roles.any(Rol.codigo == "ADMIN"),
            )
        )
        or 0
    )


def listar_roles_codigos(usuario: Usuario) -> list[str]:
    return sorted({str(r.codigo) for r in (usuario.roles or []) if r.codigo is not None})


def serializar_sesion_usuario(usuario: Usuario) -> dict[str, Any]:
    try:
        roles = listar_roles_codigos(usuario)
    except Exception:
        roles = []
    return {
        "uid": int(usuario.id),
        "email": str(usuario.email or ""),
        "nombre": str(getattr(usuario, "nombre_completo", None) or usuario.email or ""),
        "roles": roles,
    }


def autenticar(db: Session, email: str, password: str) -> Usuario | None:
    e = (email or "").strip().lower()
    u = get_usuario_por_email(db, email)
    if not u:
        logger.info("Login rechazado: no existe usuario con email=%r", e)
        return None
    if not u.activo:
        logger.info("Login rechazado: cuenta inactiva id=%s email=%r", u.id, e)
        return None
    if not verify_password(password, u.password_hash):
        logger.info("Login rechazado: contraseña incorrecta email=%r", e)
        return None
    return u


def actualizar_ultimo_acceso(db: Session, usuario_id: int) -> None:
    u = db.get(Usuario, int(usuario_id))
    if u:
        u.ultimo_acceso = datetime.utcnow()
        db.add(u)
        db.flush()


def _roles_desde_codigos(db: Session, codigos: list[str]) -> list[Rol]:
    codes = sorted({str(c).strip() for c in codigos if str(c).strip()})
    if not codes:
        raise ValueError("Seleccione al menos un rol.")
    roles: list[Rol] = []
    for code in codes:
        r = db.scalars(select(Rol).where(Rol.codigo == code)).first()
        if not r:
            raise ValueError(f"Rol desconocido: {code}")
        roles.append(r)
    return roles


def crear_usuario(
    db: Session,
    *,
    email: str,
    password: str,
    nombre_completo: str,
    rol_codigos: list[str],
    activo: bool = True,
) -> Usuario:
    e = (email or "").strip().lower()
    if not e or "@" not in e:
        raise ValueError("Email inválido.")
    if len((password or "").strip()) < 10:
        raise ValueError("La contraseña debe tener al menos 10 caracteres.")
    if get_usuario_por_email(db, e):
        raise ValueError("Ya existe un usuario con ese email.")
    roles = _roles_desde_codigos(db, rol_codigos)
    u = Usuario(
        email=e,
        password_hash=hash_password(password.strip()),
        nombre_completo=(nombre_completo or "").strip() or e.split("@")[0],
        activo=bool(activo),
    )
    for r in roles:
        u.roles.append(r)
    db.add(u)
    db.flush()
    return u


def actualizar_usuario(
    db: Session,
    usuario_id: int,
    *,
    nombre_completo: str,
    activo: bool,
    rol_codigos: list[str],
    actor_uid: int | None = None,
) -> Usuario:
    u = get_usuario_por_id(db, int(usuario_id))
    if not u:
        raise ValueError("Usuario no encontrado.")

    new_roles = _roles_desde_codigos(db, rol_codigos)
    new_codes = {r.codigo for r in new_roles}
    had_admin = "ADMIN" in listar_roles_codigos(u)
    was_active = bool(u.activo)
    was_effective_admin = had_admin and was_active
    will_have_admin = "ADMIN" in new_codes
    will_be_active = bool(activo)

    if actor_uid is not None and int(u.id) == int(actor_uid):
        if not will_be_active:
            raise ValueError("No puede desactivar su propia cuenta.")
        if had_admin and not will_have_admin:
            raise ValueError("No puede quitarse el rol Administrador a sí mismo.")

    if was_effective_admin and (not will_be_active or not will_have_admin):
        if contar_admins_activos(db) <= 1:
            raise ValueError("Debe existir al menos un administrador activo en el sistema.")

    u.nombre_completo = (nombre_completo or "").strip() or u.email.split("@")[0]
    u.activo = will_be_active
    u.roles.clear()
    for r in new_roles:
        u.roles.append(r)
    db.add(u)
    db.flush()
    return u


def establecer_password(db: Session, usuario_id: int, password: str) -> None:
    if len((password or "").strip()) < 10:
        raise ValueError("La contraseña debe tener al menos 10 caracteres.")
    u = get_usuario_por_id(db, int(usuario_id))
    if not u:
        raise ValueError("Usuario no encontrado.")
    u.password_hash = hash_password(password.strip())
    db.add(u)
    db.flush()


def crear_usuario_admin(
    db: Session,
    *,
    email: str,
    password: str,
    nombre_completo: str,
) -> Usuario:
    """Crea usuario y asigna rol ADMIN (debe existir en auth_roles)."""
    return crear_usuario(
        db,
        email=email,
        password=password,
        nombre_completo=nombre_completo,
        rol_codigos=["ADMIN"],
        activo=True,
    )
