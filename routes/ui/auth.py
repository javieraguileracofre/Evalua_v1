# routes/ui/auth.py
# -*- coding: utf-8 -*-
from __future__ import annotations

import logging
import secrets
from typing import Optional

from fastapi import APIRouter, Depends, Form, Query, Request, status
from fastapi.encoders import jsonable_encoder
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from core.config import settings
from core.paths import TEMPLATES_DIR
from core.tenant import get_current_tenant_code
from crud.auth import usuarios as crud_auth
from db.session import get_db

router = APIRouter(tags=["Autenticación"])
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))
logger = logging.getLogger("evalua.auth")


def render_login_form(
    request: Request,
    *,
    next_url: str | None = None,
    msg: str | None = None,
    sev: str = "danger",
) -> HTMLResponse:
    """HTML del formulario de login (`templates/auth/login.html`)."""
    if "csrf_login" not in request.session:
        request.session["csrf_login"] = secrets.token_urlsafe(32)
    err = request.session.pop("login_error", None)
    return templates.TemplateResponse(
        "auth/login.html",
        {
            "request": request,
            "csrf_token": request.session.get("csrf_login", ""),
            "next_url": (next_url or "").strip(),
            "error_message": err,
            "query_msg": msg,
            "query_sev": sev,
        },
    )


def _safe_next_url(request: Request, raw: str | None) -> str:
    """Evita redirecciones abiertas a dominios externos."""
    if not raw or not str(raw).strip():
        return str(request.url_for("menu_principal"))
    path = str(raw).strip()
    if not path.startswith("/") or path.startswith("//"):
        return str(request.url_for("menu_principal"))
    if "://" in path:
        return str(request.url_for("menu_principal"))
    return path


@router.get("/login", response_class=HTMLResponse, name="auth_login")
def login_get(
    request: Request,
    next: Optional[str] = Query(None),
    msg: Optional[str] = Query(None),
    sev: str = Query("danger"),
):
    raw_auth = request.session.get("auth")
    if isinstance(raw_auth, dict) and raw_auth.get("uid"):
        return RedirectResponse(
            url=_safe_next_url(request, next),
            status_code=status.HTTP_303_SEE_OTHER,
        )
    if raw_auth is not None:
        request.session.pop("auth", None)
    return render_login_form(request, next_url=next or "", msg=msg, sev=sev)


@router.post("/login", name="auth_login_submit")
def login_post(
    request: Request,
    db: Session = Depends(get_db),
    email: str = Form(""),
    password: str = Form(""),
    csrf_token: str = Form(""),
    next: str = Form(""),
):
    expect = request.session.get("csrf_login")
    if not expect or expect != (csrf_token or "").strip():
        request.session["login_error"] = (
            "Sesión de seguridad expirada. Intente nuevamente. "
            "Si el problema continúa, recargue la página de login antes de enviar el formulario."
        )
        return RedirectResponse(
            url="/login",
            status_code=status.HTTP_303_SEE_OTHER,
        )

    try:
        u = crud_auth.autenticar(db, email, password)
    except SQLAlchemyError:
        logger.exception("Login: error de base de datos al validar usuario")
        try:
            db.rollback()
        except Exception:
            pass
        request.session["csrf_login"] = secrets.token_urlsafe(32)
        request.session["login_error"] = (
            "No se pudo conectar con la base de datos o validar el usuario. "
            "Revise que PostgreSQL esté en marcha y las variables DATABASE_URL / tenant."
        )
        return RedirectResponse(url="/login", status_code=status.HTTP_303_SEE_OTHER)
    except Exception:
        logger.exception("Login: error inesperado al validar credenciales")
        try:
            db.rollback()
        except Exception:
            pass
        request.session["csrf_login"] = secrets.token_urlsafe(32)
        request.session["login_error"] = (
            "Error interno al validar la contraseña. Si acaba de migrar usuarios desde otro sistema, "
            "vuelva a generar el hash con la herramienta de administración o contacte soporte."
        )
        return RedirectResponse(url="/login", status_code=status.HTTP_303_SEE_OTHER)

    if not u:
        request.session["csrf_login"] = secrets.token_urlsafe(32)
        request.session["login_error"] = "Credenciales incorrectas o usuario desactivado."
        q = ""
        if (next or "").strip():
            from urllib.parse import urlencode

            q = "?" + urlencode({"next": next.strip()})
        return RedirectResponse(url=f"/login{q}", status_code=status.HTTP_303_SEE_OTHER)

    try:
        auth_payload = jsonable_encoder(crud_auth.serializar_sesion_usuario(u))
        auth_payload["tenant_code"] = (
            (get_current_tenant_code() or settings.default_tenant_code).strip().lower()
        )
        request.session["auth"] = auth_payload
        request.session.pop("csrf_login", None)
        crud_auth.actualizar_ultimo_acceso(db, int(u.id))
        db.commit()
    except SQLAlchemyError:
        logger.exception("Login: error al guardar sesión o último acceso")
        try:
            db.rollback()
        except Exception:
            pass
        request.session.clear()
        request.session["csrf_login"] = secrets.token_urlsafe(32)
        request.session["login_error"] = (
            "Las credenciales son válidas pero no se pudo registrar la sesión. "
            "Revise permisos en tablas auth_* y la consola del servidor."
        )
        return RedirectResponse(url="/login", status_code=status.HTTP_303_SEE_OTHER)
    except Exception:
        logger.exception("Login: error inesperado al serializar sesión")
        try:
            db.rollback()
        except Exception:
            pass
        request.session.clear()
        request.session["csrf_login"] = secrets.token_urlsafe(32)
        request.session["login_error"] = "No se pudo iniciar sesión por un error interno. Intente nuevamente."
        return RedirectResponse(url="/login", status_code=status.HTTP_303_SEE_OTHER)

    try:
        dest = _safe_next_url(request, next)
        return RedirectResponse(url=dest, status_code=status.HTTP_303_SEE_OTHER)
    except Exception:
        logger.exception("Login: error al resolver URL de destino; redirigiendo a inicio")
        return RedirectResponse(url="/", status_code=status.HTTP_303_SEE_OTHER)


@router.post("/logout", name="auth_logout")
def logout_post(request: Request):
    request.session.clear()
    return RedirectResponse(url="/login", status_code=status.HTTP_303_SEE_OTHER)
