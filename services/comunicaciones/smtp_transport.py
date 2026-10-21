# services/comunicaciones/smtp_transport.py
# -*- coding: utf-8 -*-
"""Transporte SMTP con SSL/STARTTLS, timeout y errores sanitizados."""
from __future__ import annotations

import os
import smtplib
import socket
import ssl
import time
from dataclasses import dataclass
from email.message import EmailMessage
from typing import Any

SMTP_TIMEOUT_SECONDS = 12.0

PROVIDER_PRESETS: dict[str, tuple[str, int, str]] = {
    "GMAIL": ("smtp.gmail.com", 587, "STARTTLS"),
    "MICROSOFT365": ("smtp.office365.com", 587, "STARTTLS"),
}


class MailTransportError(RuntimeError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


@dataclass(frozen=True)
class SmtpConfig:
    host: str
    port: int
    username: str
    password: str
    from_email: str
    from_name: str
    security: str = "SSL"
    timeout: float = SMTP_TIMEOUT_SECONDS
    reply_to: str | None = None


@dataclass(frozen=True)
class ValidationOutcome:
    ok: bool
    code: str
    message: str
    latency_ms: int


def apply_provider_preset(provider: str, host: str, port: int, security: str) -> tuple[str, int, str]:
    key = (provider or "SMTP").strip().upper()
    preset = PROVIDER_PRESETS.get(key)
    h = (host or "").strip()
    sec = (security or "SSL").strip().upper()
    if preset and not h:
        return preset
    if preset and h == preset[0] and int(port or 0) in (0, preset[1]) and sec in {"", "SSL", "STARTTLS"}:
        return preset[0], int(port or preset[1]), (sec or preset[2])
    return h, int(port or 465), sec or "SSL"


def _allow_plain() -> bool:
    try:
        from core.config import settings

        return bool(getattr(settings, "is_dev", False))
    except Exception:
        return os.getenv("APP_ENV", "development").strip().lower() in {"dev", "development", "local"}


def classify_smtp_error(exc: BaseException) -> MailTransportError:
    if isinstance(exc, MailTransportError):
        return exc
    if isinstance(exc, TimeoutError) or isinstance(exc, socket.timeout):
        return MailTransportError(
            "timeout",
            "No se pudo contactar el servidor de correo a tiempo. Revise host, puerto y el firewall.",
        )
    if isinstance(exc, socket.gaierror):
        return MailTransportError("host", "El host SMTP no se pudo resolver. Verifique el nombre del servidor.")
    if isinstance(exc, ConnectionRefusedError):
        return MailTransportError("conexion", "El servidor rechazó la conexión. Verifique host y puerto.")
    if isinstance(exc, ssl.SSLError):
        return MailTransportError(
            "tls",
            "Falló la negociación SSL/TLS. Pruebe el otro modo (SSL en 465 o STARTTLS en 587).",
        )
    if isinstance(exc, smtplib.SMTPAuthenticationError):
        return MailTransportError(
            "autenticacion",
            "Usuario o contraseña rechazados por el proveedor. En Gmail use una contraseña de aplicación.",
        )
    if isinstance(exc, smtplib.SMTPConnectError):
        return MailTransportError("conexion", "No se pudo establecer la conexión SMTP.")
    if isinstance(exc, OSError) and getattr(exc, "winerror", None) == 10060:
        return MailTransportError(
            "timeout",
            "Tiempo de espera agotado al conectar con el proveedor (puerto bloqueado o host inalcanzable).",
        )
    if isinstance(exc, OSError):
        return MailTransportError("conexion", "Error de red al conectar con el servidor de correo.")
    return MailTransportError("proveedor", "El proveedor de correo rechazó la operación.")


def open_smtp(cfg: SmtpConfig) -> smtplib.SMTP:
    security = (cfg.security or "SSL").strip().upper()
    if security == "NONE":
        if not _allow_plain():
            raise MailTransportError(
                "tls",
                "El envío sin cifrado solo está permitido en ambiente de desarrollo controlado.",
            )
        server: smtplib.SMTP = smtplib.SMTP(cfg.host, int(cfg.port), timeout=cfg.timeout)
        server.ehlo()
    elif security == "STARTTLS":
        server = smtplib.SMTP(cfg.host, int(cfg.port), timeout=cfg.timeout)
        server.ehlo()
        context = ssl.create_default_context()
        server.starttls(context=context)
        server.ehlo()
    else:
        context = ssl.create_default_context()
        server = smtplib.SMTP_SSL(cfg.host, int(cfg.port), timeout=cfg.timeout, context=context)
        server.ehlo()
    if not (cfg.password or "").strip():
        server.close()
        raise MailTransportError("autenticacion", "Falta la contraseña de la cuenta de correo.")
    try:
        server.login(cfg.username, cfg.password)
    except Exception:
        try:
            server.close()
        except Exception:
            pass
        raise
    return server


def validate_smtp(cfg: SmtpConfig) -> ValidationOutcome:
    started = time.monotonic()
    server: smtplib.SMTP | None = None
    try:
        server = open_smtp(cfg)
        server.noop()
        latency = int((time.monotonic() - started) * 1000)
        return ValidationOutcome(True, "ok", "Conexión y autenticación correctas.", latency)
    except Exception as exc:
        latency = int((time.monotonic() - started) * 1000)
        err = classify_smtp_error(exc)
        return ValidationOutcome(False, err.code, err.message, latency)
    finally:
        if server is not None:
            try:
                server.quit()
            except Exception:
                try:
                    server.close()
                except Exception:
                    pass


def send_with_config(
    cfg: SmtpConfig,
    *,
    to: list[str],
    subject: str,
    html_body: str,
    text_body: str,
    cc: list[str] | None = None,
    bcc: list[str] | None = None,
    attachments: list[tuple[str, bytes, str]] | None = None,
) -> dict[str, Any]:
    if not to:
        raise MailTransportError("destinatario", "No hay destinatarios válidos para el envío.")
    msg = EmailMessage()
    display_from = (cfg.from_email or cfg.username).strip()
    name = (cfg.from_name or "").strip()
    msg["From"] = f"{name} <{display_from}>" if name else display_from
    msg["To"] = ", ".join(to)
    msg["Subject"] = subject
    if cc:
        msg["Cc"] = ", ".join(cc)
    if cfg.reply_to:
        msg["Reply-To"] = cfg.reply_to
    msg.set_content(text_body)
    msg.add_alternative(html_body, subtype="html")
    for filename, content, mime in attachments or []:
        maintype, _, subtype = (mime or "application/octet-stream").partition("/")
        if not subtype:
            maintype, subtype = "application", "octet-stream"
        msg.add_attachment(
            content,
            maintype=maintype,
            subtype=subtype,
            filename=filename or "adjunto.bin",
        )
    recipients = list(to) + list(cc or []) + list(bcc or [])
    server: smtplib.SMTP | None = None
    try:
        server = open_smtp(cfg)
        server.send_message(msg, from_addr=display_from, to_addrs=recipients)
        return {"ok": True, "to": to, "subject": subject}
    except Exception as exc:
        raise classify_smtp_error(exc) from exc
    finally:
        if server is not None:
            try:
                server.quit()
            except Exception:
                try:
                    server.close()
                except Exception:
                    pass
