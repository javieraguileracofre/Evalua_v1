# routes/ui/admin_seguridad.py
# -*- coding: utf-8 -*-
"""Administración de usuarios del portal y asignación de roles (solo ADMIN)."""
from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, Request, status
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from core.paths import TEMPLATES_DIR
from core.public_errors import public_error_message
from core.rbac import usuario_es_admin
from crud.auth import usuarios as crud_auth
from db.session import get_db

router = APIRouter(prefix="/seguridad", tags=["Seguridad"])
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))
logger = logging.getLogger("evalua.seguridad")


def _redirect_list(request: Request, *, msg: str | None = None, sev: str = "info") -> RedirectResponse:
    from urllib.parse import urlencode

    url = str(request.url_for("seguridad_usuarios"))
    if msg:
        url = f"{url}?{urlencode({'msg': msg, 'sev': sev})}"
    return RedirectResponse(url=url, status_code=status.HTTP_303_SEE_OTHER)


def _guard_admin(request: Request) -> RedirectResponse | None:
    if not usuario_es_admin(getattr(request.state, "auth_user", None)):
        from urllib.parse import urlencode

        q = urlencode(
            {
                "msg": "No tiene permiso para administrar usuarios (se requiere rol Administrador).",
                "sev": "danger",
            }
        )
        return RedirectResponse(url=f"/?{q}", status_code=status.HTTP_303_SEE_OTHER)
    return None


@router.get("/usuarios", response_class=HTMLResponse, name="seguridad_usuarios")
def usuarios_lista(request: Request, db: Session = Depends(get_db)):
    if (redir := _guard_admin(request)) is not None:
        return redir
    usuarios = crud_auth.listar_usuarios(db)
    roles_catalogo = crud_auth.listar_roles(db)
    return templates.TemplateResponse(
        "seguridad/usuarios_lista.html",
        {
            "request": request,
            "active_menu": "seguridad",
            "usuarios": usuarios,
            "roles_catalogo": roles_catalogo,
        },
    )


@router.get("/usuarios/nuevo", response_class=HTMLResponse, name="seguridad_usuario_nuevo")
def usuario_nuevo_get(request: Request, db: Session = Depends(get_db)):
    if (redir := _guard_admin(request)) is not None:
        return redir
    roles = crud_auth.listar_roles(db)
    return templates.TemplateResponse(
        "seguridad/usuario_form.html",
        {
            "request": request,
            "active_menu": "seguridad",
            "modo": "nuevo",
            "usuario": None,
            "roles_todos": roles,
            "roles_asignados": [],
        },
    )


@router.post("/usuarios/nuevo", name="seguridad_usuario_crear")
async def usuario_crear_post(request: Request, db: Session = Depends(get_db)):
    if (redir := _guard_admin(request)) is not None:
        return redir
    fd = await request.form()

    email = str(fd.get("email") or "")
    nombre = str(fd.get("nombre_completo") or "")
    pw = str(fd.get("password") or "")
    pw2 = str(fd.get("password_confirm") or "")
    activo = fd.get("activo") == "on"
    try:
        roles_sel = list(fd.getlist("roles"))
    except Exception:
        roles_sel = []
    if not roles_sel and fd.get("roles"):
        roles_sel = [str(fd.get("roles"))]

    if pw != pw2:
        return templates.TemplateResponse(
            "seguridad/usuario_form.html",
            {
                "request": request,
                "active_menu": "seguridad",
                "modo": "nuevo",
                "usuario": None,
                "roles_todos": crud_auth.listar_roles(db),
                "roles_asignados": roles_sel,
                "form_error": "Las contraseñas no coinciden.",
                "form_values": {"email": email, "nombre_completo": nombre, "activo": activo, "roles": roles_sel},
            },
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        )

    try:
        crud_auth.crear_usuario(
            db,
            email=email,
            password=pw,
            nombre_completo=nombre,
            rol_codigos=roles_sel,
            activo=activo,
        )
        db.commit()
    except ValueError as e:
        db.rollback()
        return templates.TemplateResponse(
            "seguridad/usuario_form.html",
            {
                "request": request,
                "active_menu": "seguridad",
                "modo": "nuevo",
                "usuario": None,
                "roles_todos": crud_auth.listar_roles(db),
                "roles_asignados": roles_sel,
                "form_error": public_error_message(e),
                "form_values": {"email": email, "nombre_completo": nombre, "activo": activo, "roles": roles_sel},
            },
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        )
    except SQLAlchemyError:
        logger.exception("Crear usuario: error de base de datos")
        db.rollback()
        return _redirect_list(request, msg="No se pudo guardar el usuario en la base de datos.", sev="danger")

    return _redirect_list(request, msg="Usuario creado correctamente.", sev="success")


@router.get("/usuarios/{usuario_id}/editar", response_class=HTMLResponse, name="seguridad_usuario_editar")
def usuario_editar_get(request: Request, usuario_id: int, db: Session = Depends(get_db)):
    if (redir := _guard_admin(request)) is not None:
        return redir
    u = crud_auth.get_usuario_por_id(db, usuario_id)
    if not u:
        return _redirect_list(request, msg="Usuario no encontrado.", sev="warning")
    roles = crud_auth.listar_roles(db)
    return templates.TemplateResponse(
        "seguridad/usuario_form.html",
        {
            "request": request,
            "active_menu": "seguridad",
            "modo": "editar",
            "usuario": u,
            "roles_todos": roles,
            "roles_asignados": crud_auth.listar_roles_codigos(u),
        },
    )


@router.post("/usuarios/{usuario_id}/editar", name="seguridad_usuario_actualizar")
async def usuario_actualizar_post(request: Request, usuario_id: int, db: Session = Depends(get_db)):
    if (redir := _guard_admin(request)) is not None:
        return redir
    fd = await request.form()

    u = crud_auth.get_usuario_por_id(db, usuario_id)
    if not u:
        return _redirect_list(request, msg="Usuario no encontrado.", sev="warning")

    nombre = str(fd.get("nombre_completo") or "")
    activo = fd.get("activo") == "on"
    try:
        roles_sel = list(fd.getlist("roles"))
    except Exception:
        roles_sel = []
    if not roles_sel and fd.get("roles"):
        roles_sel = [str(fd.get("roles"))]

    auth = getattr(request.state, "auth_user", None) or {}
    actor_uid = int(auth["uid"]) if isinstance(auth.get("uid"), int) else None
    if actor_uid is None and isinstance(auth.get("uid"), str) and str(auth["uid"]).isdigit():
        actor_uid = int(auth["uid"])

    try:
        crud_auth.actualizar_usuario(
            db,
            usuario_id,
            nombre_completo=nombre,
            activo=activo,
            rol_codigos=roles_sel,
            actor_uid=actor_uid,
        )
        pw = str(fd.get("password") or "").strip()
        if pw:
            pw2 = str(fd.get("password_confirm") or "").strip()
            if pw != pw2:
                raise ValueError("Las contraseñas nuevas no coinciden.")
            crud_auth.establecer_password(db, usuario_id, pw)
        db.commit()
    except ValueError as e:
        db.rollback()
        u2 = crud_auth.get_usuario_por_id(db, usuario_id)
        u_show = u2 or u
        return templates.TemplateResponse(
            "seguridad/usuario_form.html",
            {
                "request": request,
                "active_menu": "seguridad",
                "modo": "editar",
                "usuario": u_show,
                "roles_todos": crud_auth.listar_roles(db),
                "roles_asignados": crud_auth.listar_roles_codigos(u_show),
                "form_error": public_error_message(e),
            },
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        )
    except SQLAlchemyError:
        logger.exception("Actualizar usuario %s: error de base de datos", usuario_id)
        db.rollback()
        return _redirect_list(request, msg="No se pudo actualizar el usuario.", sev="danger")

    return _redirect_list(request, msg="Usuario actualizado.", sev="success")
