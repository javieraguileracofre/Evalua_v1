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


def validar_politica_password(plain: str) -> str:
    """Política mínima del portal: largo, letras y números. Devuelve la clave recortada."""
    pw = (plain or "").strip()
    if len(pw.encode("utf-8")) > 72:
        raise ValueError("La contraseña no puede superar 72 bytes (límite de bcrypt).")
    if len(pw) < 10:
        raise ValueError("La contraseña debe tener al menos 10 caracteres.")
    if not any(c.isalpha() for c in pw):
        raise ValueError("La contraseña debe incluir al menos una letra.")
    if not any(c.isdigit() for c in pw):
        raise ValueError("La contraseña debe incluir al menos un número.")
    return pw


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


def listar_usuarios(
    db: Session,
    *,
    limite: int = 50,
    offset: int = 0,
    q: str | None = None,
    solo_activos: bool | None = None,
) -> list[Usuario]:
    stmt = select(Usuario).options(
        selectinload(Usuario.roles),
        selectinload(Usuario.modulos_visibles),
    )
    term = (q or "").strip()
    if term:
        like = f"%{term.lower()}%"
        stmt = stmt.where(
            (func.lower(Usuario.email).like(like))
            | (func.lower(Usuario.nombre_completo).like(like))
        )
    if solo_activos is True:
        stmt = stmt.where(Usuario.activo.is_(True))
    elif solo_activos is False:
        stmt = stmt.where(Usuario.activo.is_(False))
    stmt = stmt.order_by(Usuario.activo.desc(), Usuario.email.asc())
    lim = max(1, min(int(limite), 200))
    off = max(0, int(offset))
    return list(db.scalars(stmt.offset(off).limit(lim)))


def contar_usuarios_filtrados(
    db: Session,
    *,
    q: str | None = None,
    solo_activos: bool | None = None,
) -> int:
    stmt = select(func.count()).select_from(Usuario)
    term = (q or "").strip()
    if term:
        like = f"%{term.lower()}%"
        stmt = stmt.where(
            (func.lower(Usuario.email).like(like))
            | (func.lower(Usuario.nombre_completo).like(like))
        )
    if solo_activos is True:
        stmt = stmt.where(Usuario.activo.is_(True))
    elif solo_activos is False:
        stmt = stmt.where(Usuario.activo.is_(False))
    return int(db.scalar(stmt) or 0)


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


def serializar_sesion_usuario(usuario: Usuario, *, visible_modules: list[str] | None = None) -> dict[str, Any]:
    try:
        roles = listar_roles_codigos(usuario)
    except Exception:
        roles = []
    payload: dict[str, Any] = {
        "uid": int(usuario.id),
        "email": str(usuario.email or ""),
        "nombre": str(getattr(usuario, "nombre_completo", None) or usuario.email or ""),
        "roles": roles,
        "sv": int(getattr(usuario, "session_version", 1) or 1),
    }
    if visible_modules is not None:
        payload["visibleModules"] = list(visible_modules)
    return payload


def autenticar(db: Session, email: str, password: str) -> Usuario | None:
    e = (email or "").strip().lower()
    u = get_usuario_por_email(db, email)
    if not u:
        from core.security_log import security_event

        security_event("login_failed", uid="-", reason="unknown_user")
        return None
    if not u.activo:
        from core.security_log import security_event

        security_event("login_failed", uid=int(u.id), reason="inactive")
        return None
    if not verify_password(password, u.password_hash):
        from core.security_log import security_event

        security_event("login_failed", uid=int(u.id), reason="bad_password")
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
    modulo_keys: list[str] | None = None,
) -> Usuario:
    e = (email or "").strip().lower()
    if not e or "@" not in e:
        raise ValueError("Email inválido.")
    password = validar_politica_password(password)
    if get_usuario_por_email(db, e):
        raise ValueError("Ya existe un usuario con ese email.")
    roles = _roles_desde_codigos(db, rol_codigos)
    u = Usuario(
        email=e,
        password_hash=hash_password(password),
        nombre_completo=(nombre_completo or "").strip() or e.split("@")[0],
        activo=bool(activo),
    )
    for r in roles:
        u.roles.append(r)
    db.add(u)
    db.flush()
    from crud.auth import modulos_visibles as crud_modulos

    crud_modulos.resolve_visible_modules_for_user(db, u, modulo_keys)
    return u


def increment_session_version(db: Session, usuario_id: int) -> int:
    """Invalida cookies firmadas previas. Devuelve la nueva versión."""
    u = db.get(Usuario, int(usuario_id))
    if not u:
        raise ValueError("Usuario no encontrado.")
    current = int(getattr(u, "session_version", 1) or 1)
    u.session_version = current + 1
    db.add(u)
    db.flush()
    return int(u.session_version)


def actualizar_usuario(
    db: Session,
    usuario_id: int,
    *,
    nombre_completo: str,
    activo: bool,
    rol_codigos: list[str],
    actor_uid: int | None = None,
    modulo_keys: list[str] | None = None,
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

    old_roles = set(listar_roles_codigos(u))
    u.nombre_completo = (nombre_completo or "").strip() or u.email.split("@")[0]
    u.activo = will_be_active
    u.roles.clear()
    for r in new_roles:
        u.roles.append(r)
    roles_changed = old_roles != set(new_codes)
    if roles_changed or was_active != will_be_active:
        increment_session_version(db, int(u.id))
        from core.security_log import security_event

        if was_active and not will_be_active:
            security_event("user_deactivated", uid=int(u.id), actor=actor_uid)
        if roles_changed:
            security_event("roles_changed", uid=int(u.id), actor=actor_uid)
    db.add(u)
    db.flush()
    if modulo_keys is not None:
        from crud.auth import modulos_visibles as crud_modulos

        crud_modulos.set_user_visible_modules(
            db,
            u,
            modulo_keys,
            assigned_by_id=actor_uid,
        )
        increment_session_version(db, int(u.id))
    return u


def establecer_password(db: Session, usuario_id: int, password: str) -> None:
    password = validar_politica_password(password)
    u = get_usuario_por_id(db, int(usuario_id))
    if not u:
        raise ValueError("Usuario no encontrado.")
    u.password_hash = hash_password(password)
    increment_session_version(db, int(u.id))
    db.add(u)
    db.flush()
    from core.security_log import security_event

    security_event("password_changed", uid=int(u.id))


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
