# services/comunicaciones/email_service.py
# -*- coding: utf-8 -*-
from __future__ import annotations

import json
import os
import re
import smtplib
import ssl
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from email.message import EmailMessage
from html import escape
from typing import Any, Iterable

from sqlalchemy.orm import Session

from crud.comunicaciones import email_log as crud_email_log


SMTP_HOST: str = os.getenv("EVALUA_SMTP_HOST", "mail.evaluasoluciones.cl")
SMTP_PORT: int = int(os.getenv("EVALUA_SMTP_PORT", "465"))

SMTP_USER: str = os.getenv("EVALUA_SMTP_USER", "cobranzas_athletic@evaluasoluciones.cl")
SMTP_PASSWORD: str = os.getenv("EVALUA_SMTP_PASSWORD", "")

FROM_NAME: str = os.getenv("EVALUA_MAIL_FROM_NAME", "Evalua Soluciones · Cobranza")
REPLY_TO_DEFAULT: str | None = os.getenv("EVALUA_MAIL_REPLY_TO") or None

AddressLike = str | Iterable[str]


def _normalize_recipients(value: AddressLike | None) -> list[str]:
    if value is None:
        return []

    raw_items: list[str] = []

    if isinstance(value, str):
        raw_items = re.split(r"[;,]", value)
    else:
        for item in value:
            if item is None:
                continue
            raw_items.extend(re.split(r"[;,]", str(item)))

    cleaned: list[str] = []
    seen: set[str] = set()

    for item in raw_items:
        email = item.strip()
        if not email:
            continue
        key = email.lower()
        if key in seen:
            continue
        seen.add(key)
        cleaned.append(email)

    return cleaned


def _strip_html_tags(html_body: str) -> str:
    text = (
        html_body.replace("<br>", "\n")
        .replace("<br/>", "\n")
        .replace("<br />", "\n")
        .replace("</p>", "\n\n")
        .replace("</div>", "\n")
        .replace("</li>", "\n")
        .replace("<li>", "- ")
    )
    text = re.sub(r"<[^>]+>", "", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def _to_decimal(value: Any) -> Decimal:
    try:
        return Decimal(str(value or 0))
    except (InvalidOperation, ValueError, TypeError):
        return Decimal("0")


def _clp(value: Any) -> str:
    amount = _to_decimal(value)
    return f"${amount:,.0f}".replace(",", ".")


def _fmt_date(value: Any) -> str:
    if value is None:
        return "—"

    if isinstance(value, datetime):
        return value.strftime("%d-%m-%Y")

    if isinstance(value, date):
        return value.strftime("%d-%m-%Y")

    try:
        return value.strftime("%d-%m-%Y")
    except Exception:
        return str(value)


def _safe_json(data: dict[str, Any] | None) -> str | None:
    if not data:
        return None
    try:
        return json.dumps(data, ensure_ascii=False, default=str)
    except Exception:
        return json.dumps({"error": "meta_json_serialization_failed"}, ensure_ascii=False)


class EmailService:
    def __init__(
        self,
        *,
        host: str,
        port: int,
        username: str,
        password: str,
        from_name: str,
        reply_to_default: str | None = None,
    ) -> None:
        self.host = host
        self.port = port
        self.username = username
        self.password = password
        self.from_name = from_name
        self.reply_to_default = reply_to_default

    def _connect(self) -> smtplib.SMTP_SSL:
        if not self.password:
            raise RuntimeError("EVALUA_SMTP_PASSWORD no está configurado.")
        context = ssl.create_default_context()
        server = smtplib.SMTP_SSL(self.host, self.port, context=context)
        server.login(self.username, self.password)
        return server

    def send_email(
        self,
        *,
        to: AddressLike,
        subject: str,
        html_body: str,
        text_body: str | None = None,
        cc: AddressLike | None = None,
        bcc: AddressLike | None = None,
        reply_to: str | None = None,
    ) -> dict[str, Any]:
        to_list = _normalize_recipients(to)
        cc_list = _normalize_recipients(cc)
        bcc_list = _normalize_recipients(bcc)

        if not to_list:
            raise ValueError("No hay destinatarios válidos para el envío.")

        msg = EmailMessage()
        msg["From"] = f"{self.from_name} <{self.username}>"
        msg["To"] = ", ".join(to_list)
        msg["Subject"] = subject

        if cc_list:
            msg["Cc"] = ", ".join(cc_list)

        reply_to_value = reply_to or self.reply_to_default
        if reply_to_value:
            msg["Reply-To"] = reply_to_value

        text_body_final = text_body or _strip_html_tags(html_body)
        msg.set_content(text_body_final)
        msg.add_alternative(html_body, subtype="html")

        all_recipients = to_list + cc_list + bcc_list

        server: smtplib.SMTP_SSL | None = None
        try:
            server = self._connect()
            server.send_message(msg, from_addr=self.username, to_addrs=all_recipients)
            return {
                "ok": True,
                "to": to_list,
                "cc": cc_list,
                "bcc_count": len(bcc_list),
                "subject": subject,
            }
        finally:
            if server is not None:
                try:
                    server.quit()
                except Exception:
                    pass

    def send_and_log(
        self,
        *,
        db: Session,
        modulo: str,
        evento: str,
        to: AddressLike,
        subject: str,
        html_body: str,
        text_body: str | None = None,
        cc: AddressLike | None = None,
        bcc: AddressLike | None = None,
        reply_to: str | None = None,
        cliente_id: int | None = None,
        cxc_id: int | None = None,
        include_detalle: bool = True,
        meta: dict[str, Any] | None = None,
    ) -> Any:
        to_list = _normalize_recipients(to)
        if not to_list:
            raise ValueError("No hay destinatarios válidos para registrar el envío.")

        primary_to = to_list[0]

        log = crud_email_log.crear_email_log(
            db=db,
            modulo=modulo,
            evento=evento,
            cliente_id=cliente_id,
            cxc_id=cxc_id,
            to_email=primary_to,
            subject=subject,
            include_detalle=include_detalle,
            status="PENDIENTE",
            meta_json=_safe_json(meta),
        )

        try:
            self.send_email(
                to=to_list,
                subject=subject,
                html_body=html_body,
                text_body=text_body,
                cc=cc,
                bcc=bcc,
                reply_to=reply_to,
            )
            crud_email_log.marcar_enviado(db=db, email_log_id=log.id)
            return log
        except Exception as exc:
            crud_email_log.marcar_error(db=db, email_log_id=log.id, error_message=str(exc))
            raise

    def send_cobranza_recordatorio_lote(
        self,
        *,
        db: Session,
        cliente: Any,
        cuentas: list[Any],
        incluir_detalle: bool = True,
        comentarios: str | None = None,
        reply_to: str | None = None,
    ) -> Any:
        to_email = (
            getattr(cliente, "email", None)
            or getattr(cliente, "correo", None)
            or ""
        ).strip()

        if not to_email:
            raise ValueError("El cliente no tiene correo registrado.")

        cliente_id = getattr(cliente, "id", None)
        nombre_cliente = (
            getattr(cliente, "razon_social", None)
            or getattr(cliente, "nombre", None)
            or "Cliente"
        )

        subject = f"Recordatorio de cobranza · {nombre_cliente}"

        total_saldo = sum(
            (_to_decimal(getattr(c, "saldo_pendiente", 0)) for c in (cuentas or [])),
            Decimal("0"),
        )

        detalle_html = ""
        cuentas_meta: list[dict[str, Any]] = []

        if incluir_detalle and cuentas:
            rows: list[str] = []

            for c in cuentas:
                cxc_id = getattr(c, "id", None)
                numero_documento = getattr(c, "numero_documento", None)

                if not numero_documento and getattr(c, "nota_venta", None):
                    numero_documento = getattr(c.nota_venta, "numero", None)

                if not numero_documento:
                    numero_documento = f"CxC {cxc_id or ''}".strip()

                fecha_vencimiento = _fmt_date(getattr(c, "fecha_vencimiento", None))
                saldo = _to_decimal(getattr(c, "saldo_pendiente", 0))
                saldo_fmt = _clp(saldo)

                cuentas_meta.append(
                    {
                        "cxc_id": cxc_id,
                        "numero_documento": numero_documento,
                        "fecha_vencimiento": fecha_vencimiento,
                        "saldo_pendiente": str(saldo),
                    }
                )

                rows.append(
                    "<tr>"
                    f"<td style='padding:8px;border-bottom:1px solid #e5e7eb;'>{escape(str(numero_documento))}</td>"
                    f"<td style='padding:8px;border-bottom:1px solid #e5e7eb;text-align:center;'>{escape(fecha_vencimiento)}</td>"
                    f"<td style='padding:8px;border-bottom:1px solid #e5e7eb;text-align:right;font-weight:600;color:#b91c1c;'>{escape(saldo_fmt)}</td>"
                    "</tr>"
                )

            detalle_html = f"""
            <table style="width:100%;border-collapse:collapse;margin-top:10px">
              <thead>
                <tr>
                  <th style="text-align:left;padding:8px;border-bottom:2px solid #e5e7eb;background:#f8fafc">Documento</th>
                  <th style="text-align:center;padding:8px;border-bottom:2px solid #e5e7eb;background:#f8fafc">Vencimiento</th>
                  <th style="text-align:right;padding:8px;border-bottom:2px solid #e5e7eb;background:#f8fafc">Saldo</th>
                </tr>
              </thead>
              <tbody>
                {''.join(rows)}
              </tbody>
            </table>
            """

        comentarios_html = ""
        if comentarios:
            comentarios_html = f"""
            <p style="margin-top:12px;color:#374151;">
              {escape(comentarios)}
            </p>
            """

        html = f"""
        <html>
          <body style="margin:0;padding:0;background:#f8fafc;font-family:Arial,sans-serif;color:#111827;">
            <div style="max-width:720px;margin:0 auto;padding:24px;">
              <div style="background:#ffffff;border:1px solid #e5e7eb;border-radius:14px;padding:28px;">
                <div style="margin-bottom:20px;">
                  <div style="font-size:12px;letter-spacing:.06em;text-transform:uppercase;color:#64748b;">
                    Evalua Soluciones · Cobranza
                  </div>
                  <h1 style="margin:8px 0 0 0;font-size:22px;line-height:1.2;color:#0f172a;">
                    Recordatorio de pago pendiente
                  </h1>
                </div>

                <p style="margin:0 0 12px 0;">
                  Estimado(a) <strong>{escape(str(nombre_cliente))}</strong>,
                </p>

                <p style="margin:0 0 14px 0;color:#374151;">
                  Junto con saludar, te recordamos que mantienes documentos pendientes de pago registrados en nuestro sistema.
                </p>

                <div style="margin:16px 0;padding:16px;border-radius:12px;background:#fef2f2;border:1px solid #fecaca;">
                  <div style="font-size:12px;text-transform:uppercase;letter-spacing:.05em;color:#991b1b;">
                    Total saldo pendiente
                  </div>
                  <div style="margin-top:6px;font-size:28px;font-weight:700;color:#b91c1c;">
                    {_clp(total_saldo)}
                  </div>
                </div>

                {detalle_html}

                {comentarios_html}

                <p style="margin-top:16px;color:#374151;">
                  Agradecemos gestionar el pago a la brevedad posible o, si ya fue regularizado, por favor omitir este mensaje.

                  Cuenta bancaria
                  Javier Hernán Aguilera Cofré
                  RUT: 179067889
                  Mercado Pago
                  Cuenta Vista
                  Número de cuenta: 1015878844
                  Javieraguileracofre@gmail.com
                </p>

                <p style="margin-top:18px;margin-bottom:0;">
                  Saludos cordiales,<br>
                  <strong>Equipo de Cobranza<br>Evalua Soluciones</strong>
                </p>
              </div>
            </div>
          </body>
        </html>
        """

        meta = {
            "cliente_nombre": str(nombre_cliente),
            "cliente_id": cliente_id,
            "total_saldo": str(total_saldo),
            "cantidad_cuentas": len(cuentas or []),
            "cuentas": cuentas_meta,
            "comentarios": comentarios,
        }

        cxc_id = getattr(cuentas[0], "id", None) if len(cuentas or []) == 1 else None

        return self.send_and_log(
            db=db,
            modulo="COBRANZA",
            evento="RECORDATORIO",
            to=to_email,
            subject=subject,
            html_body=html,
            text_body=None,
            reply_to=reply_to,
            cliente_id=cliente_id,
            cxc_id=cxc_id,
            include_detalle=incluir_detalle,
            meta=meta,
        )


email_service = EmailService(
    host=SMTP_HOST,
    port=SMTP_PORT,
    username=SMTP_USER,
    password=SMTP_PASSWORD,
    from_name=FROM_NAME,
    reply_to_default=REPLY_TO_DEFAULT,
)


def enviar_recordatorio_cobranza(
    db: Session,
    cliente: Any,
    cuentas: list[Any],
    *,
    incluir_detalle: bool = True,
    comentarios: str | None = None,
    reply_to: str | None = None,
) -> Any:
    return email_service.send_cobranza_recordatorio_lote(
        db=db,
        cliente=cliente,
        cuentas=list(cuentas or []),
        incluir_detalle=incluir_detalle,
        comentarios=comentarios,
        reply_to=reply_to,
    )