# routes/ui/admin_backups.py
# -*- coding: utf-8 -*-
"""Respaldos de BD operacional. Solo ADMIN. Sin restauración desde UI."""
from __future__ import annotations

import json
from urllib.parse import urlencode

from fastapi import APIRouter, Depends, Request, status
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse, Response
from core.ui_templates import EvaluaTemplates as Jinja2Templates
from sqlalchemy.orm import Session

from core.paths import TEMPLATES_DIR
from core.rbac import usuario_es_admin
from db.session import get_db, get_session_local
from services.audit import audit_event
from services.operacion import database_backup_service as backup_svc

router = APIRouter(prefix="/seguridad/respaldos", tags=["Respaldos"])
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))


def _guard(request: Request) -> RedirectResponse | None:
    if usuario_es_admin(getattr(request.state, "auth_user", None)):
        return None
    q = urlencode({"msg": "No tiene permiso para administrar respaldos (se requiere Administrador).", "sev": "danger"})
    return RedirectResponse(url=f"/?{q}", status_code=status.HTTP_303_SEE_OTHER)


def _actor(request: Request) -> int | None:
    auth = getattr(request.state, "auth_user", None) or {}
    try:
        return int(auth.get("uid")) if auth.get("uid") is not None else None
    except (TypeError, ValueError):
        return None


def _company_code(request: Request) -> str | None:
    auth = getattr(request.state, "auth_user", None) or {}
    code = str(auth.get("company_code") or "").strip()
    return code or None


@router.get("", response_class=HTMLResponse, name="admin_backups")
def backups_home(request: Request, db: Session = Depends(get_db)):
    if (redir := _guard(request)) is not None:
        return redir
    code = _company_code(request)
    st = backup_svc.backup_status(db, company_code=code)
    rows = backup_svc.list_backups(db, company_code=code)
    readiness = backup_svc.migration_readiness(db, company_code=code)
    return templates.TemplateResponse(
        "seguridad/backups.html",
        {
            "request": request,
            "active_menu": "admin_backups",
            "status": st,
            "backups": rows,
            "readiness": readiness,
        },
    )


@router.post("/crear", name="admin_backups_crear")
def backups_crear(request: Request, db: Session = Depends(get_db)):
    if (redir := _guard(request)) is not None:
        return redir
    auth = getattr(request.state, "auth_user", None)
    code = _company_code(request)
    try:
        bid = backup_svc.start_backup_async(
            actor_id=_actor(request),
            company_code=code,
            session_factory=get_session_local(),
        )
        audit_event(
            action="backup_create",
            result="accepted",
            auth=auth if isinstance(auth, dict) else None,
            request=request,
            db=db,
            module="backups",
            entity="ops_database_backup",
            entity_id=bid,
        )
        db.commit()
        msg = "Respaldo en proceso. La página se actualizará automáticamente."
        sev = "info"
    except Exception as exc:
        db.rollback()
        audit_event(
            action="backup_create",
            result="error",
            auth=auth if isinstance(auth, dict) else None,
            request=request,
            db=db,
            module="backups",
            detail={"error": type(exc).__name__},
        )
        try:
            db.commit()
        except Exception:
            db.rollback()
        msg = "No fue posible iniciar el respaldo. Verifique que pg_dump esté instalado y reintente."
        sev = "danger"
    url = str(request.url_for("admin_backups")) + "?" + urlencode({"msg": msg, "sev": sev})
    return RedirectResponse(url=url, status_code=status.HTTP_303_SEE_OTHER)


@router.get("/estado.json", name="admin_backups_estado_json")
def backups_estado_json(request: Request, db: Session = Depends(get_db)):
    if not usuario_es_admin(getattr(request.state, "auth_user", None)):
        return Response(status_code=403, content='{"detail":"forbidden"}', media_type="application/json")
    st = backup_svc.backup_status(db, company_code=_company_code(request))
    return Response(content=json.dumps(st), media_type="application/json")


@router.post("/{backup_id}/verificar", name="admin_backups_verificar")
def backups_verificar(request: Request, backup_id: int, db: Session = Depends(get_db)):
    if (redir := _guard(request)) is not None:
        return redir
    auth = getattr(request.state, "auth_user", None)
    try:
        result = backup_svc.verify_backup(db, backup_id, company_code=_company_code(request))
        audit_event(
            action="backup_verify",
            result="ok" if result.get("ok") else "mismatch",
            auth=auth if isinstance(auth, dict) else None,
            request=request,
            db=db,
            module="backups",
            entity="ops_database_backup",
            entity_id=backup_id,
        )
        db.commit()
        msg = "Integridad verificada correctamente." if result.get("ok") else "El checksum no coincide. El archivo puede estar corrupto."
        sev = "success" if result.get("ok") else "danger"
    except ValueError as exc:
        db.rollback()
        msg = str(exc)
        sev = "warning"
    url = str(request.url_for("admin_backups")) + "?" + urlencode({"msg": msg, "sev": sev})
    return RedirectResponse(url=url, status_code=status.HTTP_303_SEE_OTHER)


@router.post("/{backup_id}/eliminar", name="admin_backups_eliminar")
def backups_eliminar(request: Request, backup_id: int, db: Session = Depends(get_db)):
    if (redir := _guard(request)) is not None:
        return redir
    auth = getattr(request.state, "auth_user", None)
    try:
        backup_svc.delete_backup(db, backup_id, company_code=_company_code(request))
        audit_event(
            action="backup_delete",
            result="ok",
            auth=auth if isinstance(auth, dict) else None,
            request=request,
            db=db,
            module="backups",
            entity="ops_database_backup",
            entity_id=backup_id,
        )
        db.commit()
        msg, sev = "Respaldo eliminado.", "success"
    except ValueError as exc:
        db.rollback()
        msg, sev = str(exc), "warning"
    url = str(request.url_for("admin_backups")) + "?" + urlencode({"msg": msg, "sev": sev})
    return RedirectResponse(url=url, status_code=status.HTTP_303_SEE_OTHER)


@router.get("/{backup_id}/descargar", name="admin_backups_descargar")
def backups_descargar(request: Request, backup_id: int, db: Session = Depends(get_db)):
    if (redir := _guard(request)) is not None:
        return redir
    row = backup_svc.get_backup(db, backup_id, company_code=_company_code(request))
    if row is None or row.status != "success" or not row.file_path:
        url = str(request.url_for("admin_backups")) + "?" + urlencode(
            {"msg": "Respaldo no disponible para descarga.", "sev": "warning"}
        )
        return RedirectResponse(url=url, status_code=status.HTTP_303_SEE_OTHER)
    path = backup_svc.confined_backup_path(row.file_path)
    if path is None or not path.is_file():
        url = str(request.url_for("admin_backups")) + "?" + urlencode(
            {"msg": "El archivo de respaldo ya no está en disco.", "sev": "danger"}
        )
        return RedirectResponse(url=url, status_code=status.HTTP_303_SEE_OTHER)
    auth = getattr(request.state, "auth_user", None)
    audit_event(
        action="backup_download",
        result="ok",
        auth=auth if isinstance(auth, dict) else None,
        request=request,
        db=db,
        module="backups",
        entity="ops_database_backup",
        entity_id=backup_id,
    )
    db.commit()
    return FileResponse(path, filename=row.file_name or path.name, media_type="application/octet-stream")


@router.get("/informe-migracion", name="admin_backups_informe")
def backups_informe(request: Request, db: Session = Depends(get_db), format: str = "md"):
    if (redir := _guard(request)) is not None:
        return redir
    fmt = (format or "md").lower()
    if fmt not in {"md", "json", "txt"}:
        fmt = "md"
    readiness = backup_svc.migration_readiness(db, company_code=_company_code(request))
    auth = getattr(request.state, "auth_user", None)
    audit_event(
        action="migration_report",
        result="ok",
        auth=auth if isinstance(auth, dict) else None,
        request=request,
        db=db,
        module="backups",
        detail={"format": fmt},
    )
    db.commit()
    if fmt == "json":
        body = json.dumps(readiness, ensure_ascii=False, indent=2)
        return Response(
            content=body,
            media_type="application/json",
            headers={"Content-Disposition": 'attachment; filename="migration-report.json"'},
        )
    lines = [
        "# Informe de migración EvaluaERP",
        "",
        f"- Estado general: {readiness.get('overallStatus')}",
        f"- Versión: {readiness.get('appVersion')}",
        f"- Entorno: {readiness.get('appEnv')}",
        f"- Tenancy: {readiness.get('tenancyMode')}",
        "",
        "## Checklist",
    ]
    for key, ok in (readiness.get("checks") or {}).items():
        lines.append(f"- [{'x' if ok else ' '}] {key}")
    body = "\n".join(lines) + "\n"
    media = "text/markdown" if fmt == "md" else "text/plain"
    ext = "md" if fmt == "md" else "txt"
    return Response(
        content=body,
        media_type=media,
        headers={"Content-Disposition": f'attachment; filename="migration-report.{ext}"'},
    )
