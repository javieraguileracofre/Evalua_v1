# routes/ui/admin_correo.py
# -*- coding: utf-8 -*-
"""Administración de cuentas de correo saliente (solo ADMIN)."""
from __future__ import annotations

import logging
from urllib.parse import urlencode

from fastapi import APIRouter, Depends, Request, status
from fastapi.responses import HTMLResponse, RedirectResponse
from core.ui_templates import EvaluaTemplates as Jinja2Templates
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from core.paths import TEMPLATES_DIR
from core.public_errors import public_error_message
from core.rbac import usuario_puede_gestionar_correo
from db.session import get_db
from services.comunicaciones import mail_account_service as mail_svc
from services.comunicaciones.mail_account_service import MailConfigError
from services.comunicaciones.smtp_transport import PROVIDER_PRESETS

router = APIRouter(prefix="/seguridad/correo", tags=["Correo"])
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))
logger = logging.getLogger("evalua.correo")


def _guard(request: Request) -> RedirectResponse | None:
    if usuario_puede_gestionar_correo(getattr(request.state, "auth_user", None)):
        return None
    q = urlencode(
        {
            "msg": "No tiene permiso para administrar cuentas de correo (se requiere rol Administrador).",
            "sev": "danger",
        }
    )
    return RedirectResponse(url=f"/?{q}", status_code=status.HTTP_303_SEE_OTHER)


def _redirect(request: Request, *, name: str = "seguridad_correo", msg: str | None = None, sev: str = "info", **params) -> RedirectResponse:
    url = str(request.url_for(name, **params))
    if msg:
        url = f"{url}?{urlencode({'msg': msg, 'sev': sev})}"
    return RedirectResponse(url=url, status_code=status.HTTP_303_SEE_OTHER)


def _actor_id(request: Request) -> int | None:
    auth = getattr(request.state, "auth_user", None) or {}
    raw = auth.get("uid")
    try:
        return int(raw)
    except (TypeError, ValueError):
        return None


@router.get("", response_class=HTMLResponse, name="seguridad_correo")
def correo_hub(request: Request, db: Session = Depends(get_db)):
    if (redir := _guard(request)) is not None:
        return redir
    cuentas = mail_svc.list_accounts(db)
    canales = mail_svc.list_channels(db)
    return templates.TemplateResponse(
        "seguridad/correo_hub.html",
        {
            "request": request,
            "active_menu": "seguridad_correo",
            "cuentas": cuentas,
            "canales": canales,
        },
    )


def _form_ctx(request: Request, *, modo: str, cuenta=None, error: str | None = None, values: dict | None = None) -> dict:
    return {
        "request": request,
        "active_menu": "seguridad_correo",
        "modo": modo,
        "cuenta": cuenta,
        "form_error": error,
        "form_values": values or {},
        "providers": (
            ("SMTP", "SMTP genérico"),
            ("GMAIL", "Gmail / Google Workspace"),
            ("MICROSOFT365", "Microsoft 365 / Outlook"),
            ("OTRO", "Otro proveedor"),
        ),
        "securities": (
            ("SSL", "SSL (habitualmente puerto 465)"),
            ("STARTTLS", "TLS / STARTTLS (habitualmente puerto 587)"),
            ("NONE", "Sin cifrado (solo desarrollo)"),
        ),
        "presets": PROVIDER_PRESETS,
    }


@router.get("/nuevo", response_class=HTMLResponse, name="seguridad_correo_nuevo")
def correo_nuevo_get(request: Request):
    if (redir := _guard(request)) is not None:
        return redir
    return templates.TemplateResponse("seguridad/correo_form.html", _form_ctx(request, modo="nuevo"))


@router.post("/nuevo", name="seguridad_correo_crear")
async def correo_nuevo_post(request: Request, db: Session = Depends(get_db)):
    if (redir := _guard(request)) is not None:
        return redir
    fd = await request.form()
    values = {k: str(fd.get(k) or "") for k in ("nombre", "from_email", "from_name", "provider", "host", "port", "security", "username")}
    try:
        mail_svc.crear_cuenta(
            db,
            nombre=values["nombre"],
            from_email=values["from_email"],
            from_name=values["from_name"],
            provider=values["provider"],
            host=values["host"],
            port=values["port"] or "465",
            security=values["security"],
            username=values["username"],
            password=str(fd.get("password") or ""),
            created_by_id=_actor_id(request),
        )
        db.commit()
    except (MailConfigError, ValueError) as exc:
        db.rollback()
        return templates.TemplateResponse(
            "seguridad/correo_form.html",
            _form_ctx(request, modo="nuevo", error=public_error_message(exc), values=values),
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        )
    except SQLAlchemyError:
        logger.exception("Crear cuenta de correo")
        db.rollback()
        return _redirect(request, msg="No se pudo guardar la cuenta.", sev="danger")
    return _redirect(request, msg="Cuenta creada. Valide la conexión antes de activarla.", sev="success")


@router.get("/{account_id}/editar", response_class=HTMLResponse, name="seguridad_correo_editar")
def correo_editar_get(request: Request, account_id: int, db: Session = Depends(get_db)):
    if (redir := _guard(request)) is not None:
        return redir
    cuenta = mail_svc.get_account(db, account_id)
    if not cuenta:
        return _redirect(request, msg="Cuenta no encontrada.", sev="warning")
    return templates.TemplateResponse(
        "seguridad/correo_form.html",
        _form_ctx(request, modo="editar", cuenta=cuenta),
    )


@router.post("/{account_id}/editar", name="seguridad_correo_actualizar")
async def correo_editar_post(request: Request, account_id: int, db: Session = Depends(get_db)):
    if (redir := _guard(request)) is not None:
        return redir
    fd = await request.form()
    values = {k: str(fd.get(k) or "") for k in ("nombre", "from_email", "from_name", "provider", "host", "port", "security", "username")}
    try:
        mail_svc.actualizar_cuenta(
            db,
            account_id,
            nombre=values["nombre"],
            from_email=values["from_email"],
            from_name=values["from_name"],
            provider=values["provider"],
            host=values["host"],
            port=values["port"] or "465",
            security=values["security"],
            username=values["username"],
            password=str(fd.get("password") or "") or None,
        )
        db.commit()
    except (MailConfigError, ValueError) as exc:
        db.rollback()
        cuenta = mail_svc.get_account(db, account_id)
        return templates.TemplateResponse(
            "seguridad/correo_form.html",
            _form_ctx(request, modo="editar", cuenta=cuenta, error=public_error_message(exc), values=values),
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        )
    except SQLAlchemyError:
        logger.exception("Actualizar cuenta de correo %s", account_id)
        db.rollback()
        return _redirect(request, msg="No se pudo actualizar la cuenta.", sev="danger")
    return _redirect(request, msg="Cuenta actualizada.", sev="success")


@router.post("/{account_id}/validar", name="seguridad_correo_validar")
def correo_validar(request: Request, account_id: int, db: Session = Depends(get_db)):
    if (redir := _guard(request)) is not None:
        return redir
    try:
        row = mail_svc.validar_conexion(db, account_id)
        db.commit()
    except MailConfigError as exc:
        db.rollback()
        return _redirect(request, msg=exc.message, sev="danger")
    except SQLAlchemyError:
        logger.exception("Validar cuenta de correo %s", account_id)
        db.rollback()
        return _redirect(request, msg="No se pudo validar la cuenta.", sev="danger")
    if row.ok:
        return _redirect(
            request,
            msg=f"Conexión correcta ({row.latency_ms or 0} ms). Ya puede activar la cuenta.",
            sev="success",
        )
    return _redirect(request, msg=row.error_message or "La validación falló.", sev="danger")


@router.post("/{account_id}/prueba", name="seguridad_correo_prueba")
async def correo_prueba(request: Request, account_id: int, db: Session = Depends(get_db)):
    if (redir := _guard(request)) is not None:
        return redir
    fd = await request.form()
    dest = str(fd.get("to_email") or "")
    try:
        row = mail_svc.enviar_correo_prueba(db, account_id, dest)
        db.commit()
    except MailConfigError as exc:
        db.rollback()
        return _redirect(request, msg=exc.message, sev="danger")
    except SQLAlchemyError:
        logger.exception("Correo de prueba cuenta %s", account_id)
        db.rollback()
        return _redirect(request, msg="No se pudo enviar el correo de prueba.", sev="danger")
    if row.ok:
        return _redirect(request, msg="Correo de prueba enviado. Revise la bandeja de entrada (y spam).", sev="success")
    return _redirect(request, msg=row.error_message or "El envío de prueba falló.", sev="danger")


@router.post("/{account_id}/estado", name="seguridad_correo_estado")
async def correo_estado(request: Request, account_id: int, db: Session = Depends(get_db)):
    if (redir := _guard(request)) is not None:
        return redir
    fd = await request.form()
    try:
        mail_svc.cambiar_estado(db, account_id, str(fd.get("status") or ""))
        db.commit()
    except MailConfigError as exc:
        db.rollback()
        return _redirect(request, msg=exc.message, sev="danger")
    except SQLAlchemyError:
        logger.exception("Cambiar estado cuenta %s", account_id)
        db.rollback()
        return _redirect(request, msg="No se pudo cambiar el estado.", sev="danger")
    return _redirect(request, msg="Estado de la cuenta actualizado.", sev="success")


@router.post("/canales", name="seguridad_correo_canales")
async def correo_canales_post(request: Request, db: Session = Depends(get_db)):
    if (redir := _guard(request)) is not None:
        return redir
    fd = await request.form()
    try:
        for canal in mail_svc.list_channels(db):
            raw_p = str(fd.get(f"principal_{canal.codigo}") or "").strip()
            raw_f = str(fd.get(f"fallback_{canal.codigo}") or "").strip()
            mail_svc.asignar_canal(
                db,
                canal.codigo,
                cuenta_principal_id=int(raw_p) if raw_p.isdigit() else None,
                cuenta_fallback_id=int(raw_f) if raw_f.isdigit() else None,
            )
        db.commit()
    except MailConfigError as exc:
        db.rollback()
        return _redirect(request, msg=exc.message, sev="danger")
    except SQLAlchemyError:
        logger.exception("Asignar canales de correo")
        db.rollback()
        return _redirect(request, msg="No se pudieron guardar las asignaciones.", sev="danger")
    return _redirect(request, msg="Asignación de tipos de gestión actualizada.", sev="success")
