# routes/ui/auth.py
# -*- coding: utf-8 -*-
from __future__ import annotations

import logging
import secrets
from typing import Optional

from fastapi import APIRouter, Depends, Form, Query, Request, status
from fastapi.encoders import jsonable_encoder
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from core.ui_templates import EvaluaTemplates as Jinja2Templates
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from core.client_ip import client_ip
from core.config import settings
from core.csrf_middleware import tokens_match
from core.login_throttle import (
    GENERIC_FAILURE,
    is_login_blocked,
    register_login_failure,
    register_login_success,
)
from core.paths import TEMPLATES_DIR
from core.security_log import security_event
from crud.auth import usuarios as crud_auth
from db.session import get_account_db, get_login_db
from schemas.auth.password_reset import ForgotPasswordIn, ResetPasswordIn, VerifyResetCodeIn
from services.auth import password_reset as svc_reset

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


def _start_authenticated_session(request: Request, auth_payload: dict) -> None:
    """Descarta la cookie previa y emite un CSRF nuevo junto con la sesión autenticada."""
    request.session.clear()
    request.session["csrf_global"] = secrets.token_urlsafe(32)
    request.session["auth"] = auth_payload


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


def _rate_limited_login(request: Request, next_url: str) -> RedirectResponse:
    request.session["csrf_login"] = secrets.token_urlsafe(32)
    request.session["login_error"] = GENERIC_FAILURE
    security_event("login_failed", uid="-", reason="rate_limited")
    q = ""
    if (next_url or "").strip():
        from urllib.parse import urlencode

        q = "?" + urlencode({"next": next_url.strip()})
    return RedirectResponse(url=f"/login{q}", status_code=status.HTTP_303_SEE_OTHER)


def _login_identity(request: Request, *, email: str, password: str, next_url: str):
    from db.identity_session import get_identity_sessionmaker
    from services.platform.audit import write_audit
    from services.platform.login_flow import authenticate_identity, begin_session
    from services.platform.messages import MSG_NO_COMPANY

    identity = get_identity_sessionmaker()()
    try:
        if is_login_blocked(email=email, ip=_client_ip(request), db=identity):
            return _rate_limited_login(request, next_url)
        user = authenticate_identity(identity, email, password)
        if user is None:
            register_login_failure(email=email, ip=_client_ip(request), db=identity)
            write_audit(identity, actor_id=None, action="LOGIN_FAILED", result="failed", module="auth")
            identity.commit()
            request.session["csrf_login"] = secrets.token_urlsafe(32)
            request.session["login_error"] = GENERIC_FAILURE
            return RedirectResponse(url="/login", status_code=status.HTTP_303_SEE_OTHER)
        started = begin_session(identity, user)
        register_login_success(email=email, ip=_client_ip(request), db=identity)
        destination = started["destination"]
        if destination == "no_company":
            request.session.clear()
            request.session["csrf_login"] = secrets.token_urlsafe(32)
            request.session["login_error"] = MSG_NO_COMPANY
            return RedirectResponse(url="/login", status_code=status.HTTP_303_SEE_OTHER)
        _start_authenticated_session(request, started["auth"])
        if destination == "selector":
            return RedirectResponse(url="/empresa/seleccionar", status_code=status.HTTP_303_SEE_OTHER)
        if destination == "platform":
            return RedirectResponse(url="/plataforma/empresas", status_code=status.HTTP_303_SEE_OTHER)
        return RedirectResponse(url=_safe_next_url(request, next_url), status_code=status.HTTP_303_SEE_OTHER)
    except Exception:
        logger.exception("Login de plataforma")
        identity.rollback()
        request.session["login_error"] = "No se pudo iniciar sesión. Intente nuevamente."
        return RedirectResponse(url="/login", status_code=status.HTTP_303_SEE_OTHER)
    finally:
        identity.close()


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
    db: Session | None = Depends(get_login_db),
    email: str = Form(""),
    password: str = Form(""),
    csrf_token: str = Form(""),
    next: str = Form(""),
):
    expect = request.session.get("csrf_login")
    if not tokens_match(expect, csrf_token):
        request.session["login_error"] = (
            "Sesión de seguridad expirada. Intente nuevamente. "
            "Si el problema continúa, recargue la página de login antes de enviar el formulario."
        )
        return RedirectResponse(
            url="/login",
            status_code=status.HTTP_303_SEE_OTHER,
        )

    if settings.database_per_company:
        return _login_identity(request, email=email, password=password, next_url=next)

    if is_login_blocked(email=email, ip=_client_ip(request), db=db):
        return _rate_limited_login(request, next)

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
            "No se pudo conectar con la base de datos. Intente más tarde."
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
        register_login_failure(email=email, ip=_client_ip(request), db=db)
        request.session["csrf_login"] = secrets.token_urlsafe(32)
        if crud_auth.contar_usuarios(db) == 0:
            request.session["login_error"] = (
                "No hay usuarios en esta instalación. "
                "Pida al administrador de la plataforma que cree el primer acceso."
            )
        else:
            request.session["login_error"] = GENERIC_FAILURE
        q = ""
        if (next or "").strip():
            from urllib.parse import urlencode

            q = "?" + urlencode({"next": next.strip()})
        return RedirectResponse(url=f"/login{q}", status_code=status.HTTP_303_SEE_OTHER)

    try:
        from crud.auth import modulos_visibles as crud_modulos

        visible = crud_modulos.user_visible_modules_list(u, db)
        auth_payload = jsonable_encoder(crud_auth.serializar_sesion_usuario(u, visible_modules=visible))
        _start_authenticated_session(request, auth_payload)
        crud_auth.actualizar_ultimo_acceso(db, int(u.id))
        register_login_success(email=email, ip=_client_ip(request), db=db)
        security_event("login_success", uid=int(u.id))
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
    auth = getattr(request.state, "auth_user", None) or request.session.get("auth")
    security_event("logout", auth=auth if isinstance(auth, dict) else None)
    request.session.clear()
    return RedirectResponse(url="/login", status_code=status.HTTP_303_SEE_OTHER)


def _ensure_csrf_login(request: Request) -> str:
    if "csrf_login" not in request.session:
        request.session["csrf_login"] = secrets.token_urlsafe(32)
    return str(request.session.get("csrf_login") or "")


def _csrf_ok(request: Request, csrf_token: str) -> bool:
    return tokens_match(request.session.get("csrf_login"), csrf_token)


def _client_ip(request: Request) -> str | None:
    """IP de cliente solo detrás de un proxy explícito. Si no, el cupo es por correo."""
    if not settings.trust_x_forwarded_for:
        return None
    return client_ip(request)


def _clear_reset_session(request: Request) -> None:
    for key in ("pwd_reset_email", "pwd_reset_code", "pwd_reset_verified", "pwd_reset_token"):
        request.session.pop(key, None)


def _flash_reset(request: Request, msg: str, sev: str = "info") -> None:
    request.session["reset_flash_msg"] = msg
    request.session["reset_flash_sev"] = sev


def _pop_flash(request: Request) -> tuple[str | None, str]:
    msg = request.session.pop("reset_flash_msg", None)
    sev = request.session.pop("reset_flash_sev", "info") or "info"
    return msg, str(sev)


def render_recuperar(
    request: Request,
    *,
    step: str,
    msg: str | None = None,
    sev: str = "info",
    error_message: str | None = None,
    email_value: str = "",
) -> HTMLResponse:
    flash_msg, flash_sev = _pop_flash(request)
    return templates.TemplateResponse(
        "auth/recuperar.html",
        {
            "request": request,
            "csrf_token": _ensure_csrf_login(request),
            "step": step,
            "query_msg": msg or flash_msg,
            "query_sev": sev if msg else flash_sev,
            "error_message": error_message,
            "email_value": email_value,
        },
    )


@router.get("/login/recuperar", response_class=HTMLResponse, name="auth_recuperar")
def recuperar_get(request: Request):
    _clear_reset_session(request)
    return render_recuperar(request, step="email")


@router.post("/login/recuperar", name="auth_recuperar_submit")
def recuperar_post(
    request: Request,
    db: Session = Depends(get_account_db),
    email: str = Form(""),
    csrf_token: str = Form(""),
):
    if not _csrf_ok(request, csrf_token):
        return render_recuperar(
            request,
            step="email",
            error_message="Sesión de seguridad expirada. Recargue la página e intente nuevamente.",
            email_value=email,
        )
    try:
        result = svc_reset.request_password_reset(db, email, ip=_client_ip(request))
        db.commit()
    except SQLAlchemyError:
        logger.exception("Recuperación: error de base de datos al solicitar código")
        try:
            db.rollback()
        except Exception:
            pass
        return render_recuperar(
            request,
            step="email",
            error_message="No se pudo procesar la solicitud. Intente más tarde.",
            email_value=email,
        )
    request.session["pwd_reset_email"] = svc_reset.normalize_email(email)
    request.session.pop("pwd_reset_code", None)
    request.session.pop("pwd_reset_verified", None)
    sev = "warning" if result.rate_limited else "info"
    _flash_reset(request, result.message, sev)
    return RedirectResponse(
        url=str(request.url_for("auth_recuperar_codigo")),
        status_code=status.HTTP_303_SEE_OTHER,
    )


@router.get("/login/recuperar/codigo", response_class=HTMLResponse, name="auth_recuperar_codigo")
def recuperar_codigo_get(request: Request):
    if not request.session.get("pwd_reset_email"):
        return RedirectResponse(
            url=str(request.url_for("auth_recuperar")),
            status_code=status.HTTP_303_SEE_OTHER,
        )
    return render_recuperar(request, step="codigo")


@router.post("/login/recuperar/codigo", name="auth_recuperar_codigo_submit")
def recuperar_codigo_post(
    request: Request,
    db: Session = Depends(get_account_db),
    code: str = Form(""),
    csrf_token: str = Form(""),
):
    if not _csrf_ok(request, csrf_token):
        return render_recuperar(
            request,
            step="codigo",
            error_message="Sesión de seguridad expirada. Recargue la página e intente nuevamente.",
        )
    email = str(request.session.get("pwd_reset_email") or "")
    if not email:
        return render_recuperar(
            request,
            step="email",
            error_message="Indique primero el correo asociado a la cuenta.",
        )
    try:
        result = svc_reset.verify_reset_code(db, email, code)
        db.commit()
    except SQLAlchemyError:
        logger.exception("Recuperación: error de base de datos al verificar código")
        try:
            db.rollback()
        except Exception:
            pass
        return render_recuperar(
            request,
            step="codigo",
            error_message="No se pudo verificar el código. Intente más tarde.",
        )
    if not result.ok:
        return render_recuperar(request, step="codigo", error_message=result.message)
    token = svc_reset.issue_reset_ok_token(db, email)
    request.session.pop("pwd_reset_code", None)
    if not token:
        return render_recuperar(request, step="codigo", error_message=result.message)
    request.session["pwd_reset_token"] = token
    request.session["pwd_reset_verified"] = True
    _flash_reset(request, result.message, "success")
    return RedirectResponse(
        url=str(request.url_for("auth_recuperar_clave")),
        status_code=status.HTTP_303_SEE_OTHER,
    )


@router.get("/login/recuperar/clave", response_class=HTMLResponse, name="auth_recuperar_clave")
def recuperar_clave_get(request: Request):
    if not request.session.get("pwd_reset_verified") or not request.session.get("pwd_reset_token"):
        return RedirectResponse(
            url=str(request.url_for("auth_recuperar")),
            status_code=status.HTTP_303_SEE_OTHER,
        )
    return render_recuperar(request, step="clave")


@router.post("/login/recuperar/clave", name="auth_recuperar_clave_submit")
def recuperar_clave_post(
    request: Request,
    db: Session = Depends(get_account_db),
    new_password: str = Form(""),
    confirm_password: str = Form(""),
    csrf_token: str = Form(""),
):
    if not _csrf_ok(request, csrf_token):
        return render_recuperar(
            request,
            step="clave",
            error_message="Sesión de seguridad expirada. Recargue la página e intente nuevamente.",
        )
    email = str(request.session.get("pwd_reset_email") or "")
    token = str(request.session.get("pwd_reset_token") or "")
    if not email or not request.session.get("pwd_reset_verified") or not token:
        return render_recuperar(
            request,
            step="email",
            error_message="Debe solicitar y verificar un código antes de cambiar la contraseña.",
        )
    try:
        result = svc_reset.reset_password_with_ok_token(
            db, email, token, new_password, confirm_password
        )
        db.commit()
    except SQLAlchemyError:
        logger.exception("Recuperación: error de base de datos al cambiar contraseña")
        try:
            db.rollback()
        except Exception:
            pass
        return render_recuperar(
            request,
            step="clave",
            error_message="No se pudo actualizar la contraseña. Intente más tarde.",
        )
    if not result.ok:
        return render_recuperar(request, step="clave", error_message=result.message)
    _clear_reset_session(request)
    _flash_reset(request, result.message, "success")
    return RedirectResponse(
        url=str(request.url_for("auth_recuperar_exito")),
        status_code=status.HTTP_303_SEE_OTHER,
    )


@router.get("/login/recuperar/exito", response_class=HTMLResponse, name="auth_recuperar_exito")
def recuperar_exito_get(request: Request):
    return render_recuperar(request, step="exito")


def _json_reset_payload(ok: bool, message: str, **extra: object) -> JSONResponse:
    body: dict[str, object] = {"ok": ok, "message": message}
    body.update(extra)
    code = status.HTTP_200_OK if ok else status.HTTP_400_BAD_REQUEST
    return JSONResponse(body, status_code=code)


@router.post("/auth/forgot-password", name="auth_forgot_password")
def forgot_password_api(
    payload: ForgotPasswordIn,
    request: Request,
    db: Session = Depends(get_account_db),
):
    try:
        result = svc_reset.request_password_reset(
            db, str(payload.email), ip=_client_ip(request)
        )
        db.commit()
    except SQLAlchemyError:
        logger.exception("API recuperación: error de base de datos al solicitar código")
        try:
            db.rollback()
        except Exception:
            pass
        return JSONResponse(
            {"ok": True, "message": svc_reset.GENERIC_REQUEST_MESSAGE},
            status_code=status.HTTP_200_OK,
        )
    # Respuesta siempre 200 y genérica: no revela si el correo existe.
    return JSONResponse(
        {"ok": True, "message": result.message},
        status_code=status.HTTP_200_OK,
    )


@router.post("/auth/verify-reset-code", name="auth_verify_reset_code")
def verify_reset_code_api(
    payload: VerifyResetCodeIn,
    db: Session = Depends(get_account_db),
):
    try:
        result = svc_reset.verify_reset_code(db, str(payload.email), payload.code)
        db.commit()
    except SQLAlchemyError:
        logger.exception("API recuperación: error de base de datos al verificar código")
        try:
            db.rollback()
        except Exception:
            pass
        return _json_reset_payload(False, svc_reset.GENERIC_CODE_MESSAGE)
    if not result.ok:
        return _json_reset_payload(False, result.message)
    return _json_reset_payload(True, result.message)


@router.post("/auth/reset-password", name="auth_reset_password")
def reset_password_api(
    payload: ResetPasswordIn,
    db: Session = Depends(get_account_db),
):
    try:
        result = svc_reset.reset_password_with_code(
            db,
            str(payload.email),
            payload.code,
            payload.new_password,
            payload.confirm_password,
        )
        db.commit()
    except SQLAlchemyError:
        logger.exception("API recuperación: error de base de datos al cambiar contraseña")
        try:
            db.rollback()
        except Exception:
            pass
        return _json_reset_payload(False, svc_reset.GENERIC_CODE_MESSAGE)
    if not result.ok:
        return _json_reset_payload(False, result.message)
    return _json_reset_payload(True, result.message)
