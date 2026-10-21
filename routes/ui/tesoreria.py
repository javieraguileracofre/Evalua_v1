# routes/ui/tesoreria.py
# -*- coding: utf-8 -*-
"""Pantallas de Tesorería. La importación vive en services.tesoreria."""
from __future__ import annotations

import json
from datetime import date
from urllib.parse import quote

from fastapi import APIRouter, Depends, Form, Query, Request, status
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from sqlalchemy.orm import Session

from core.paths import TEMPLATES_DIR
from core.rbac import usuario_puede_actualizar_sii, usuario_puede_ver_tesoreria
from core.ui_templates import EvaluaTemplates as Jinja2Templates
from crud.finanzas import periodos as crud_periodos
from crud.tesoreria import sii as crud_sii
from db.session import get_db, get_session_local
from services.tesoreria.actualizacion import (
    TesoreriaError,
    continuar_ejecucion,
    ejecucion_en_curso,
    iniciar_actualizacion,
    puede_continuar,
)
from services.tesoreria.consultas import etiqueta_periodo, resumen, vista_ejecucion
from services.tesoreria.crypto import SiiCryptoError, encrypt_secret
from integrations.sii.rut import normalizar_rut, rut_es_valido
from services.tesoreria.precondiciones import parse_periodo, rut_de_empresa_activa, rut_para_consulta_sii

router = APIRouter(tags=["Tesorería"])
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))


def _redir(request: Request, route_name: str, *, msg: str, sev: str = "danger", **params) -> RedirectResponse:
    url = str(request.url_for(route_name, **params))
    sep = "&" if "?" in url else "?"
    return RedirectResponse(
        url=f"{url}{sep}msg={quote(msg)}&sev={sev}",
        status_code=status.HTTP_303_SEE_OTHER,
    )


def _negar(request: Request):
    return _redir(request, "menu_principal", msg="No tiene permiso para ver Tesorería.", sev="danger")


def _empresa(request: Request) -> dict | None:
    from core.company_context import get_company_context
    from core.config import settings

    auth = getattr(request.state, "auth_user", None) or {}
    ctx = get_company_context()
    if settings.database_per_company:
        if ctx is None or not ctx.authorized:
            return None
        return {
            "id": int(ctx.company_id),
            "nombre": ctx.legal_name,
            "rut": rut_de_empresa_activa(por_base=True, rut_contexto=ctx.rut, rut_legado=""),
        }
    import os

    rut_legado = str(auth.get("company_rut") or os.environ.get("EVALUA_RUT_EMISOR") or "")
    return {
        "id": int(auth.get("active_company_id") or 0),
        "nombre": str(auth.get("company_legal_name") or "Empresa activa"),
        "rut": rut_de_empresa_activa(por_base=False, rut_contexto="", rut_legado=rut_legado),
    }


def _fijar_rut_de_la_base(db: Session, empresa: dict) -> str | None:
    """Usa el RUT de public.empresa en la base abierta. Avisa si no coincide."""
    try:
        empresa["rut"] = rut_para_consulta_sii(
            rut_base=crud_sii.rut_fiscal_de_la_base(db),
            rut_contexto=str(empresa.get("rut") or ""),
        )
    except ValueError as exc:
        return str(exc)
    return None


def _periodo_default() -> tuple[int, int]:
    hoy = date.today()
    if hoy.month == 1:
        return hoy.year - 1, 12
    return hoy.year, hoy.month - 1


@router.get("/tesoreria", response_class=HTMLResponse, name="tesoreria_home")
def tesoreria_home(
    request: Request,
    periodo: str | None = Query(None),
    db: Session = Depends(get_db),
):
    auth = getattr(request.state, "auth_user", None)
    if not usuario_puede_ver_tesoreria(auth):
        return _negar(request)
    empresa = _empresa(request)
    if empresa is None:
        return _redir(request, "menu_principal", msg="Seleccione una empresa antes de abrir Tesorería.")
    listo = crud_sii.esquema_listo(db)
    opciones: list[dict] = []
    anio, mes = _periodo_default()
    if listo:
        hoy = date.today()
        crud_periodos.ensure_periodos_rango(db, anio_ini=hoy.year - 1, mes_ini=1, anio_fin=hoy.year, mes_fin=hoy.month)
        for row in crud_periodos.list_periodos(db, limit=24):
            opciones.append(
                {
                    "valor": f"{int(row['anio']):04d}-{int(row['mes']):02d}",
                    "etiqueta": etiqueta_periodo(int(row["anio"]), int(row["mes"])),
                }
            )
    if periodo:
        try:
            anio, mes = parse_periodo(periodo)
        except ValueError:
            anio, mes = _periodo_default()
    seleccionado = f"{anio:04d}-{mes:02d}"
    if not any(item["valor"] == seleccionado for item in opciones):
        opciones.insert(0, {"valor": seleccionado, "etiqueta": etiqueta_periodo(anio, mes)})
    conflicto_rut = _fijar_rut_de_la_base(db, empresa) if listo else None
    libros = resumen(db, anio=anio, mes=mes) if listo else resumen(db, anio=anio, mes=mes)
    credencial = crud_sii.obtener_credencial_publica(db) if listo else None
    if listo and not ejecucion_en_curso(empresa["id"]):
        crud_sii.cerrar_ejecuciones_stale(db, empresa["id"], minutos=0)
        db.commit()
    activa = bool(listo and (ejecucion_en_curso(empresa["id"]) or crud_sii.hay_ejecucion_activa(db, empresa["id"])))
    recientes = crud_sii.listar_ejecuciones(db, empresa["id"]) if listo else []
    return templates.TemplateResponse(
        "tesoreria/home.html",
        {
            "request": request,
            "active_menu": "tesoreria",
            "empresa": empresa,
            "periodo": seleccionado,
            "periodo_etiqueta": etiqueta_periodo(anio, mes),
            "opciones": opciones,
            "libros": libros,
            "credencial": credencial,
            "esquema_listo": listo,
            "actualizacion_activa": activa,
            "puede_actualizar": usuario_puede_actualizar_sii(auth),
            "conflicto_rut": conflicto_rut,
            "recientes": recientes,
            "etiqueta_periodo": etiqueta_periodo,
        },
    )


@router.get("/tesoreria/credenciales", response_class=HTMLResponse, name="tesoreria_credenciales")
def tesoreria_credenciales(request: Request, db: Session = Depends(get_db)):
    auth = getattr(request.state, "auth_user", None)
    if not usuario_puede_ver_tesoreria(auth):
        return _negar(request)
    empresa = _empresa(request)
    if empresa is None:
        return _redir(request, "menu_principal", msg="Seleccione una empresa antes de configurar el SII.")
    conflicto_rut = _fijar_rut_de_la_base(db, empresa)
    credencial = crud_sii.obtener_credencial_publica(db) if crud_sii.esquema_listo(db) else None
    largo_clave = None
    if credencial and credencial.get("tiene_secreto"):
        try:
            from services.tesoreria.crypto import decrypt_secret

            largo_clave = len(decrypt_secret(crud_sii.leer_secreto_cifrado(db)))
        except SiiCryptoError:
            largo_clave = None
    return templates.TemplateResponse(
        "tesoreria/credenciales.html",
        {
            "request": request,
            "active_menu": "tesoreria_credenciales",
            "empresa": empresa,
            "credencial": credencial,
            "largo_clave": largo_clave,
            "conflicto_rut": conflicto_rut,
            "puede_guardar": usuario_puede_actualizar_sii(auth),
            "esquema_listo": crud_sii.esquema_listo(db),
        },
    )


@router.post("/tesoreria/credenciales", name="tesoreria_credenciales_guardar")
def tesoreria_credenciales_guardar(
    request: Request,
    clave: str = Form(""),
    db: Session = Depends(get_db),
):
    auth = getattr(request.state, "auth_user", None)
    if not usuario_puede_actualizar_sii(auth):
        return _negar(request)
    empresa = _empresa(request)
    if empresa is None:
        return _redir(request, "menu_principal", msg="Seleccione una empresa antes de configurar el SII.")
    if not crud_sii.esquema_listo(db):
        return _redir(request, "tesoreria_credenciales", msg="Falta aplicar la migración de Tesorería.")
    conflicto_rut = _fijar_rut_de_la_base(db, empresa)
    if conflicto_rut:
        return _redir(request, "tesoreria_credenciales", msg=conflicto_rut)
    rut = normalizar_rut(empresa["rut"])
    if not rut_es_valido(rut):
        return _redir(request, "tesoreria_credenciales", msg="La empresa activa no tiene un RUT válido.")
    secreto = None
    aviso = "No escribió una clave nueva. Se mantuvo la que ya estaba guardada."
    if clave.strip():
        try:
            secreto = encrypt_secret(clave)
        except SiiCryptoError as exc:
            return _redir(request, "tesoreria_credenciales", msg=str(exc))
        aviso = f"Clave tributaria guardada ({len(clave)} caracteres) para la empresa activa."
    elif not (crud_sii.obtener_credencial_publica(db) or {}).get("tiene_secreto"):
        return _redir(request, "tesoreria_credenciales", msg="Ingrese la clave tributaria de la empresa.")
    crud_sii.guardar_credencial(
        db,
        rut=rut,
        usuario=rut,
        secreto_cifrado=secreto,
        actor_id=auth.get("uid") if isinstance(auth, dict) else None,
    )
    db.commit()
    return _redir(request, "tesoreria_credenciales", msg=aviso, sev="success")


@router.post("/tesoreria/actualizar", name="tesoreria_actualizar")
def tesoreria_actualizar(
    request: Request,
    periodo: str = Form(...),
    db: Session = Depends(get_db),
):
    auth = getattr(request.state, "auth_user", None) or {}
    if not usuario_puede_actualizar_sii(auth):
        return _negar(request)
    empresa = _empresa(request)
    if empresa is None:
        return _redir(request, "menu_principal", msg="Seleccione una empresa antes de actualizar.")
    try:
        anio, mes = parse_periodo(periodo)
    except ValueError as exc:
        return _redir(request, "tesoreria_home", msg=str(exc))
    conflicto_rut = _fijar_rut_de_la_base(db, empresa)
    if conflicto_rut:
        return _redir(request, "tesoreria_home", msg=conflicto_rut)
    try:
        ejecucion_id = iniciar_actualizacion(
            db,
            session_factory=get_session_local(),
            company_id=empresa["id"],
            company_name=empresa["nombre"],
            rut=empresa["rut"],
            actor_id=auth.get("uid"),
            actor_email=str(auth.get("email") or ""),
            anio=anio,
            mes=mes,
            autenticado=True,
            puede_actualizar=True,
        )
    except TesoreriaError as exc:
        return _redir(request, "tesoreria_home", msg=exc.mensaje)
    return RedirectResponse(
        url=str(request.url_for("tesoreria_ejecucion", ejecucion_id=ejecucion_id)),
        status_code=status.HTTP_303_SEE_OTHER,
    )


@router.get("/tesoreria/ejecuciones/{ejecucion_id}", response_class=HTMLResponse, name="tesoreria_ejecucion")
def tesoreria_ejecucion(request: Request, ejecucion_id: int, db: Session = Depends(get_db)):
    auth = getattr(request.state, "auth_user", None)
    if not usuario_puede_ver_tesoreria(auth):
        return _negar(request)
    empresa = _empresa(request)
    if empresa is None:
        return _redir(request, "menu_principal", msg="Seleccione una empresa.")
    row = crud_sii.obtener_ejecucion(db, ejecucion_id, empresa["id"])
    if row is None:
        return _redir(request, "tesoreria_home", msg="Ejecución no encontrada para la empresa activa.")
    _fijar_rut_de_la_base(db, empresa)
    vista = vista_ejecucion(
        row,
        empresa=empresa["nombre"],
        rut=empresa["rut"],
        puede_continuar_flag=puede_continuar(empresa["id"], ejecucion_id),
    )
    return templates.TemplateResponse(
        "tesoreria/ejecucion.html",
        {
            "request": request,
            "active_menu": "tesoreria_ejecucion",
            "vista": vista,
            "empresa": empresa,
        },
    )


@router.get("/tesoreria/ejecuciones/{ejecucion_id}/estado", name="tesoreria_ejecucion_estado")
def tesoreria_ejecucion_estado(request: Request, ejecucion_id: int, db: Session = Depends(get_db)):
    auth = getattr(request.state, "auth_user", None)
    if not usuario_puede_ver_tesoreria(auth):
        return JSONResponse({"error": "sin permiso"}, status_code=403)
    empresa = _empresa(request)
    if empresa is None:
        return JSONResponse({"error": "sin empresa"}, status_code=403)
    row = crud_sii.obtener_ejecucion(db, ejecucion_id, empresa["id"])
    if row is None:
        return JSONResponse({"error": "no encontrada"}, status_code=404)
    _fijar_rut_de_la_base(db, empresa)
    vista = vista_ejecucion(
        row,
        empresa=empresa["nombre"],
        rut=empresa["rut"],
        puede_continuar_flag=puede_continuar(empresa["id"], ejecucion_id),
    )
    return JSONResponse(json.loads(json.dumps(vista, default=str)))


@router.post("/tesoreria/ejecuciones/{ejecucion_id}/continuar", name="tesoreria_continuar")
def tesoreria_continuar(request: Request, ejecucion_id: int, db: Session = Depends(get_db)):
    auth = getattr(request.state, "auth_user", None)
    if not usuario_puede_actualizar_sii(auth):
        return _negar(request)
    empresa = _empresa(request)
    if empresa is None:
        return _redir(request, "menu_principal", msg="Seleccione una empresa.")
    row = crud_sii.obtener_ejecucion(db, ejecucion_id, empresa["id"])
    if row is None:
        return _redir(request, "tesoreria_home", msg="Ejecución no encontrada para la empresa activa.")
    if not continuar_ejecucion(empresa["id"], ejecucion_id):
        return _redir(
            request,
            "tesoreria_ejecucion",
            ejecucion_id=ejecucion_id,
            msg="No hay un navegador esperando. Inicie nuevamente la actualización.",
            sev="warning",
        )
    return RedirectResponse(
        url=str(request.url_for("tesoreria_ejecucion", ejecucion_id=ejecucion_id)),
        status_code=status.HTTP_303_SEE_OTHER,
    )
