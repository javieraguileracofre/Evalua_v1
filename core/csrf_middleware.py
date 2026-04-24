# core/csrf_middleware.py
# -*- coding: utf-8 -*-
from __future__ import annotations

import secrets
from collections.abc import AsyncIterator
from urllib.parse import parse_qs, urlparse

from starlette.datastructures import Headers, MutableHeaders
from starlette.formparsers import MultiPartException, MultiPartParser
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from core.auth_paths import is_public_path
from core.config import settings

_SAFE_METHODS = {"GET", "HEAD", "OPTIONS", "TRACE"}
_CSRF_SESSION_KEY = "csrf_global"


def _request_origin(request: Request) -> str | None:
    origin = (request.headers.get("origin") or "").strip()
    if origin:
        return origin
    referer = (request.headers.get("referer") or "").strip()
    if not referer:
        return None
    parsed = urlparse(referer)
    if not parsed.scheme or not parsed.netloc:
        return None
    return f"{parsed.scheme}://{parsed.netloc}"


def _same_origin(request: Request) -> bool:
    src = _request_origin(request)
    if not src:
        return False
    dst = str(request.base_url).rstrip("/")
    return src.rstrip("/") == dst


async def _stream_one_chunk(data: bytes) -> AsyncIterator[bytes]:
    if data:
        yield data


def _csrf_token_from_urlencoded(raw: bytes) -> str:
    if not raw:
        return ""
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError:
        text = raw.decode("latin-1", errors="replace")
    try:
        pairs = parse_qs(text, keep_blank_values=True, strict_parsing=False)
    except ValueError:
        return ""
    vals = pairs.get("csrf_token") or []
    return str(vals[0]).strip() if vals else ""


async def _csrf_token_from_multipart(headers: Headers, raw: bytes) -> str:
    if not raw:
        return ""
    try:
        parser = MultiPartParser(headers, _stream_one_chunk(raw))
        form_data = await parser.parse()
    except (MultiPartException, AssertionError, KeyError, ValueError):
        return ""
    val = form_data.get("csrf_token")
    if val is None:
        return ""
    if not isinstance(val, str):
        return ""
    return val.strip()


async def _read_raw_body(receive: Receive) -> bytes:
    chunks: list[bytes] = []
    while True:
        message = await receive()
        if message["type"] == "http.disconnect":
            break
        if message["type"] == "http.request":
            chunks.append(message.get("body", b""))
            if not message.get("more_body", False):
                break
    return b"".join(chunks)


def _replay_receive_factory(body: bytes) -> Receive:
    sent = False

    async def replay_receive() -> Message:
        nonlocal sent
        if not sent:
            sent = True
            return {"type": "http.request", "body": body, "more_body": False}
        return {"type": "http.disconnect"}

    return replay_receive


def _send_with_csrf_header(send: Send, sess: dict) -> Send:
    async def wrapped(message: Message) -> None:
        if message["type"] == "http.response.start":
            tok = str(sess.get(_CSRF_SESSION_KEY) or "").strip()
            if tok:
                h = MutableHeaders(scope=message)
                h.append("x-csrf-token", tok)
        await send(message)

    return wrapped


class CSRFMiddleware:
    """
    Protección CSRF (ASGI puro, sin BaseHTTPMiddleware).

    Varias capas de BaseHTTPMiddleware + lectura del cuerpo pueden dejar el POST vacío
    para FastAPI (422 en Form(...)). Aquí se lee `receive` una vez y se reinyecta.
    """

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        method_raw = scope.get("method", b"GET")
        if isinstance(method_raw, bytes):
            method = method_raw.decode("ascii", errors="replace").upper()
        else:
            method = str(method_raw).upper()

        path_raw = scope.get("path", "")
        if isinstance(path_raw, bytes):
            path = path_raw.decode("utf-8", errors="replace")
        else:
            path = str(path_raw)

        sess = scope.get("session")
        if not isinstance(sess, dict):
            sess = {}
            scope["session"] = sess
        if not sess.get(_CSRF_SESSION_KEY):
            sess[_CSRF_SESSION_KEY] = secrets.token_urlsafe(32)

        if method in _SAFE_METHODS:
            await self.app(scope, receive, send)
            return

        if is_public_path(path, settings):
            await self.app(scope, receive, send)
            return

        req = Request(scope)

        if not _same_origin(req):
            resp = JSONResponse(
                {"detail": "CSRF validation failed: invalid origin."},
                status_code=403,
            )
            await resp(scope, _replay_receive_factory(b""), send)
            return

        headers = Headers(scope=scope)
        ctype = (headers.get("content-type") or "").lower()
        token_hdr = (headers.get("x-csrf-token") or "").strip()
        expected = str(sess.get(_CSRF_SESSION_KEY) or "").strip()

        if "application/json" in ctype or "application/merge-patch+json" in ctype:
            supplied = token_hdr
            if not supplied or not expected or supplied != expected:
                resp = JSONResponse(
                    {"detail": "CSRF validation failed: missing or invalid token."},
                    status_code=403,
                )
                await resp(scope, _replay_receive_factory(b""), send)
                return
            await self.app(scope, receive, _send_with_csrf_header(send, sess))
            return

        if "application/x-www-form-urlencoded" in ctype or "multipart/form-data" in ctype:
            raw_body = await _read_raw_body(receive)
            if "application/x-www-form-urlencoded" in ctype:
                token_form = _csrf_token_from_urlencoded(raw_body)
            else:
                token_form = await _csrf_token_from_multipart(headers, raw_body)

            supplied = token_hdr or token_form
            if not supplied or not expected or supplied != expected:
                resp = JSONResponse(
                    {"detail": "CSRF validation failed: missing or invalid token."},
                    status_code=403,
                )
                await resp(scope, _replay_receive_factory(b""), send)
                return

            replay = _replay_receive_factory(raw_body)
            await self.app(scope, replay, _send_with_csrf_header(send, sess))
            return

        supplied = token_hdr
        if not supplied or not expected or supplied != expected:
            resp = JSONResponse(
                {"detail": "CSRF validation failed: missing or invalid token."},
                status_code=403,
            )
            await resp(scope, _replay_receive_factory(b""), send)
            return

        await self.app(scope, receive, _send_with_csrf_header(send, sess))
