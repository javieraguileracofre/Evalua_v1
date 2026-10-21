# services/operacion/database_backup_service.py
# -*- coding: utf-8 -*-
"""Respaldos pg_dump de la BD operacional autorizada. Sin restauración desde UI."""
from __future__ import annotations

import hashlib
import logging
import os
import re
import shutil
import subprocess
import threading
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urlparse

from sqlalchemy import create_engine, func, select, text
from sqlalchemy.orm import Session, sessionmaker

from core.config import settings
from core.paths import operational_storage
from models.ops.backup import DatabaseBackup

logger = logging.getLogger("evalua.ops.backup")

BACKUP_ERROR_PUBLIC = "No se pudo crear el respaldo."

_LOCK = threading.Lock()
_RUNNING = False


def pg_dump_available() -> bool:
    return shutil.which("pg_dump") is not None


def _operational_url() -> str:
    if settings.database_per_company:
        from db.company_engine import CompanyDatabaseUnavailable, get_active_company_engine

        try:
            eng = get_active_company_engine()
        except CompanyDatabaseUnavailable:
            raise
        return str(eng.url.render_as_string(hide_password=False))
    url = (settings.database_url or "").strip()
    if not url:
        raise RuntimeError("No hay DATABASE_URL operacional configurada.")
    return url


def _parse_db_name(url: str) -> str:
    try:
        u = urlparse(url.replace("postgresql+psycopg://", "postgresql://", 1))
        name = (u.path or "").lstrip("/")
        return unquote(name.split("?")[0]) or "postgres"
    except Exception:
        return "postgres"


def backup_status(db: Session, *, company_code: str | None = None) -> dict[str, Any]:
    tool = pg_dump_available()
    url = ""
    try:
        url = _operational_url()
    except Exception as exc:
        logger.warning("Estado respaldo: sin URL operacional (%s)", type(exc).__name__)
    db_name = _parse_db_name(url) if url else ""
    q = select(DatabaseBackup).where(DatabaseBackup.status == "success").order_by(
        DatabaseBackup.finished_at.desc().nullslast(), DatabaseBackup.id.desc()
    )
    if company_code:
        q = q.where(DatabaseBackup.company_code == company_code)
    last = db.scalars(q.limit(1)).first()
    count_q = select(func.count()).select_from(DatabaseBackup).where(DatabaseBackup.status == "success")
    if company_code:
        count_q = count_q.where(DatabaseBackup.company_code == company_code)
    count = int(db.scalar(count_q) or 0)
    running = db.scalars(
        select(DatabaseBackup)
        .where(DatabaseBackup.status.in_(("pending", "running")))
        .order_by(DatabaseBackup.id.desc())
        .limit(1)
    ).first()
    size_approx = None
    if url:
        try:
            eng = create_engine(url, pool_pre_ping=True)
            with eng.connect() as conn:
                row = conn.execute(
                    text("SELECT pg_database_size(current_database())")
                ).scalar()
                size_approx = int(row or 0)
            eng.dispose()
        except Exception:
            size_approx = None
    return {
        "toolAvailable": tool,
        "engine": "postgresql",
        "databaseName": db_name,
        "approxSizeBytes": size_approx,
        "availableCount": count,
        "running": bool(running) or _RUNNING,
        "runningBackupId": int(running.id) if running else None,
        "lastSuccess": _serialize(last) if last else None,
        "createEnabled": bool(tool and url and not running and not _RUNNING),
    }


def list_backups(db: Session, *, company_code: str | None = None, limit: int = 50) -> list[DatabaseBackup]:
    q = select(DatabaseBackup).order_by(DatabaseBackup.created_at.desc(), DatabaseBackup.id.desc())
    if company_code:
        q = q.where(DatabaseBackup.company_code == company_code)
    return list(db.scalars(q.limit(max(1, min(limit, 200)))))


def _serialize(row: DatabaseBackup) -> dict[str, Any]:
    return {
        "id": int(row.id),
        "status": row.status,
        "backupType": row.backup_type,
        "engineName": row.engine_name,
        "databaseName": row.database_name,
        "fileName": row.file_name,
        "sizeBytes": int(row.size_bytes) if row.size_bytes is not None else None,
        "checksumSha256": row.checksum_sha256,
        "checksumShort": (row.checksum_sha256 or "")[:12] or None,
        "createdById": row.created_by_id,
        "errorMessage": row.error_message,
        "companyCode": row.company_code,
        "startedAt": row.started_at.isoformat(sep=" ") if row.started_at else None,
        "finishedAt": row.finished_at.isoformat(sep=" ") if row.finished_at else None,
        "createdAt": row.created_at.isoformat(sep=" ") if row.created_at else None,
    }


def get_backup(db: Session, backup_id: int, *, company_code: str | None = None) -> DatabaseBackup | None:
    row = db.get(DatabaseBackup, int(backup_id))
    if row is None:
        return None
    if company_code and (row.company_code or "") != company_code:
        return None
    return row


def confined_backup_path(file_path: str | None, *, root: Path | None = None) -> Path | None:
    """Ruta absoluta solo si el archivo queda dentro del directorio de respaldos."""
    raw = (file_path or "").strip()
    if not raw:
        return None
    base = (root if root is not None else operational_storage("backups")).resolve()
    candidate = Path(raw)
    if not candidate.is_absolute():
        candidate = base / candidate
    try:
        resolved = candidate.resolve()
    except OSError:
        return None
    try:
        resolved.relative_to(base)
    except ValueError:
        return None
    return resolved


def _redact_process_output(raw: str) -> str:
    text_out = (raw or "").replace("\n", " ").strip()
    text_out = re.sub(r"postgres(?:ql)?(?:\+\w+)?://\S+", "[url]", text_out, flags=re.I)
    text_out = re.sub(r"(?i)(password\s*[=:]\s*)\S+", r"\1[redacted]", text_out)
    return text_out[:240]


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _run_pg_dump(url: str, out_path: Path) -> None:
    env = os.environ.copy()
    parsed = urlparse(url.replace("postgresql+psycopg://", "postgresql://", 1))
    if parsed.password:
        env["PGPASSWORD"] = unquote(parsed.password)
    host = parsed.hostname or "localhost"
    port = str(parsed.port or 5432)
    user = unquote(parsed.username or "postgres")
    dbname = _parse_db_name(url)
    cmd = [
        "pg_dump",
        "-h",
        host,
        "-p",
        port,
        "-U",
        user,
        "-d",
        dbname,
        "-F",
        "c",
        "-f",
        str(out_path),
    ]
    proc = subprocess.run(cmd, env=env, capture_output=True, text=True, timeout=3600)
    if proc.returncode != 0:
        logger.warning(
            "pg_dump falló: %s",
            _redact_process_output(proc.stderr or proc.stdout or ""),
        )
        raise RuntimeError(BACKUP_ERROR_PUBLIC)


def start_backup_async(
    *,
    actor_id: int | None,
    company_code: str | None,
    session_factory: sessionmaker,
) -> int:
    global _RUNNING
    with _LOCK:
        if _RUNNING:
            raise RuntimeError("Ya hay un respaldo en proceso.")
        _RUNNING = True

    db = session_factory()
    try:
        url = _operational_url()
        db_name = _parse_db_name(url)
        row = DatabaseBackup(
            status="pending",
            backup_type="manual",
            engine_name="postgresql",
            database_name=db_name,
            created_by_id=actor_id,
            company_code=company_code,
            started_at=datetime.utcnow(),
        )
        db.add(row)
        db.commit()
        backup_id = int(row.id)
    except Exception:
        db.rollback()
        with _LOCK:
            _RUNNING = False
        db.close()
        raise

    db.close()

    def _worker() -> None:
        global _RUNNING
        session = session_factory()
        try:
            row = session.get(DatabaseBackup, backup_id)
            if row is None:
                return
            row.status = "running"
            session.add(row)
            session.commit()
            dest_dir = operational_storage("backups")
            dest_dir.mkdir(parents=True, exist_ok=True)
            stamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
            file_name = f"{db_name}_{stamp}.dump"
            out_path = dest_dir / file_name
            url_local = _operational_url()
            _run_pg_dump(url_local, out_path)
            checksum = _sha256_file(out_path)
            row = session.get(DatabaseBackup, backup_id)
            if row is None:
                return
            row.status = "success"
            row.file_name = file_name
            row.file_path = str(out_path)
            row.size_bytes = out_path.stat().st_size
            row.checksum_sha256 = checksum
            row.finished_at = datetime.utcnow()
            row.error_message = None
            session.add(row)
            session.commit()
        except Exception as exc:
            logger.exception("Respaldo %s falló", backup_id)
            try:
                row = session.get(DatabaseBackup, backup_id)
                if row is not None:
                    row.status = "failed"
                    row.error_message = BACKUP_ERROR_PUBLIC
                    row.finished_at = datetime.utcnow()
                    session.add(row)
                    session.commit()
            except Exception:
                session.rollback()
        finally:
            session.close()
            with _LOCK:
                _RUNNING = False

    threading.Thread(target=_worker, name=f"pg-backup-{backup_id}", daemon=True).start()
    return backup_id


def verify_backup(db: Session, backup_id: int, *, company_code: str | None = None) -> dict[str, Any]:
    row = get_backup(db, backup_id, company_code=company_code)
    if row is None:
        raise ValueError("Respaldo no encontrado.")
    if row.status != "success" or not row.file_path:
        raise ValueError("Solo se pueden verificar respaldos exitosos.")
    path = confined_backup_path(row.file_path)
    if path is None or not path.is_file():
        return {"ok": False, "reason": "Archivo no encontrado en disco."}
    digest = _sha256_file(path)
    ok = bool(row.checksum_sha256 and digest.lower() == row.checksum_sha256.lower())
    return {
        "ok": ok,
        "checksumSha256": digest,
        "expected": row.checksum_sha256,
        "sizeBytes": path.stat().st_size,
    }


def delete_backup(db: Session, backup_id: int, *, company_code: str | None = None) -> None:
    row = get_backup(db, backup_id, company_code=company_code)
    if row is None:
        raise ValueError("Respaldo no encontrado.")
    if row.status in ("pending", "running"):
        raise ValueError("No se puede eliminar un respaldo en proceso.")
    if row.file_path:
        path = confined_backup_path(row.file_path)
        if path is None:
            raise ValueError("Respaldo no disponible.")
        if path.is_file():
            try:
                path.unlink()
            except OSError as exc:
                logger.warning("No se pudo borrar archivo de respaldo: %s", type(exc).__name__)
    db.delete(row)
    db.flush()


def migration_readiness(db: Session, *, company_code: str | None = None) -> dict[str, Any]:
    st = backup_status(db, company_code=company_code)
    last = st.get("lastSuccess") or {}
    checks = {
        "recent_backup": bool(last),
        "checksum_registered": bool(last.get("checksumSha256")),
        "env_documented": True,
        "backend_version": bool(settings.app_version),
        "frontend_version": True,
        "database_engine": st.get("engine") == "postgresql",
        "deploy_commands": True,
        "last_backup_date": bool(last.get("finishedAt") or last.get("createdAt")),
        "backup_tool": bool(st.get("toolAvailable")),
    }
    ready = all(checks.values())
    return {
        "overallStatus": "ready" if ready else "incomplete",
        "checks": checks,
        "status": st,
        "appVersion": settings.app_version,
        "appEnv": settings.app_env,
        "tenancyMode": settings.tenancy_mode,
    }
