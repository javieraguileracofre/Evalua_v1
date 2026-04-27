# routes/ui/cliente.py
# -*- coding: utf-8 -*-
from __future__ import annotations

import csv
import io
from typing import Any

from fastapi import (
    APIRouter,
    Depends,
    File,
    Form,
    HTTPException,
    Query,
    Request,
    UploadFile,
    status,
)
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from core.bulk_limits import BULK_CSV_MAX_BYTES, BULK_CSV_MAX_ROWS, LIST_PAGE_DEFAULT, LIST_PAGE_MAX
from core.paths import TEMPLATES_DIR
from core.public_errors import public_error_message
from core.rbac import guard_operacion_consulta, guard_operacion_mutacion
from crud.maestros import cliente as crud_cliente
from db.session import get_db
from schemas.maestros.cliente import ClienteCreate, ClienteUpdate

router = APIRouter(tags=["Clientes"])
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))


def _redirect(
    request: Request,
    route_name: str,
    *,
    msg: str | None = None,
    sev: str = "info",
    status_code: int = status.HTTP_303_SEE_OTHER,
    **path_params: Any,
) -> RedirectResponse:
    url = str(request.url_for(route_name, **path_params))
    if msg:
        sep = "&" if "?" in url else "?"
        url = f"{url}{sep}msg={msg}&sev={sev}"
    return RedirectResponse(url=url, status_code=status_code)


@router.get("/clientes", response_class=HTMLResponse, name="clientes_list")
def clientes_list(
    request: Request,
    q: str | None = Query(None),
    activos_solo: bool = Query(False),
    skip: int = Query(0, ge=0),
    limit: int = Query(LIST_PAGE_DEFAULT, ge=1, le=LIST_PAGE_MAX),
    msg: str | None = Query(None),
    sev: str = Query("info"),
    db: Session = Depends(get_db),
):
    if (redir := guard_operacion_consulta(request)) is not None:
        return redir
    lim = min(max(limit, 1), LIST_PAGE_MAX)
    sk = max(skip, 0)
    clientes, hay_mas = crud_cliente.listar_clientes(
        db,
        activos_solo=activos_solo,
        busqueda=q,
        skip=sk,
        limit=lim,
    )

    return templates.TemplateResponse(
        "clientes/clientes.html",
        {
            "request": request,
            "clientes": clientes,
            "q": q,
            "activos_solo": activos_solo,
            "skip": sk,
            "limit": lim,
            "hay_mas": hay_mas,
            "list_page_max": LIST_PAGE_MAX,
            "msg": msg,
            "sev": sev,
            "active_menu": "clientes",
        },
    )


@router.get("/clientes/form", response_class=HTMLResponse, name="clientes_form_nuevo")
def clientes_form_nuevo(
    request: Request,
    db: Session = Depends(get_db),
):
    if (redir := guard_operacion_consulta(request)) is not None:
        return redir
    return templates.TemplateResponse(
        "clientes/form_cliente.html",
        {
            "request": request,
            "cliente": None,
            "active_menu": "clientes",
        },
    )


@router.get("/clientes/form/{cliente_id}", response_class=HTMLResponse, name="clientes_form_editar")
def clientes_form_editar(
    request: Request,
    cliente_id: int,
    db: Session = Depends(get_db),
):
    if (redir := guard_operacion_consulta(request)) is not None:
        return redir
    cliente = crud_cliente.get_cliente(db, cliente_id)
    if not cliente:
        raise HTTPException(status_code=404, detail="Cliente no encontrado")

    return templates.TemplateResponse(
        "clientes/form_cliente.html",
        {
            "request": request,
            "cliente": cliente,
            "active_menu": "clientes",
        },
    )


@router.post("/clientes", name="clientes_create")
def clientes_create(
    request: Request,
    rut: str = Form(...),
    razon_social: str = Form(...),
    nombre_fantasia: str | None = Form(None),
    giro: str | None = Form(None),
    direccion: str | None = Form(None),
    comuna: str | None = Form(None),
    ciudad: str | None = Form(None),
    telefono: str | None = Form(None),
    email: str | None = Form(None),
    activo: str = Form("true"),
    db: Session = Depends(get_db),
):
    if (redir := guard_operacion_mutacion(request)) is not None:
        return redir
    data = ClienteCreate(
        rut=rut,
        razon_social=razon_social,
        nombre_fantasia=nombre_fantasia,
        giro=giro,
        direccion=direccion,
        comuna=comuna,
        ciudad=ciudad,
        telefono=telefono,
        email=email or None,
        activo=(activo == "true"),
    )

    try:
        crud_cliente.crear_cliente(db, data)
        return _redirect(request, "clientes_list", msg="Cliente creado", sev="success")
    except ValueError as e:
        return _redirect(request, "clientes_form_nuevo", msg=public_error_message(e), sev="warning")


@router.post("/clientes/{cliente_id}", name="clientes_update")
def clientes_update(
    request: Request,
    cliente_id: int,
    razon_social: str = Form(...),
    nombre_fantasia: str | None = Form(None),
    giro: str | None = Form(None),
    direccion: str | None = Form(None),
    comuna: str | None = Form(None),
    ciudad: str | None = Form(None),
    telefono: str | None = Form(None),
    email: str | None = Form(None),
    activo: str = Form("true"),
    db: Session = Depends(get_db),
):
    if (redir := guard_operacion_mutacion(request)) is not None:
        return redir
    cliente = crud_cliente.get_cliente(db, cliente_id)
    if not cliente:
        raise HTTPException(status_code=404, detail="Cliente no encontrado")

    data = ClienteUpdate(
        razon_social=razon_social,
        nombre_fantasia=nombre_fantasia,
        giro=giro,
        direccion=direccion,
        comuna=comuna,
        ciudad=ciudad,
        telefono=telefono,
        email=email or None,
        activo=(activo == "true"),
    )

    try:
        crud_cliente.actualizar_cliente(db, cliente, data)
        return _redirect(request, "clientes_list", msg="Cliente actualizado", sev="success")
    except ValueError as e:
        return _redirect(
            request,
            "clientes_form_editar",
            cliente_id=cliente_id,
            msg=public_error_message(e),
            sev="warning",
        )


@router.post("/clientes/{cliente_id}/desactivar", name="clientes_desactivar")
def clientes_desactivar(
    request: Request,
    cliente_id: int,
    db: Session = Depends(get_db),
):
    if (redir := guard_operacion_mutacion(request)) is not None:
        return redir
    cliente = crud_cliente.get_cliente(db, cliente_id)
    if not cliente:
        raise HTTPException(status_code=404, detail="Cliente no encontrado")

    crud_cliente.desactivar_cliente(db, cliente)
    return _redirect(request, "clientes_list", msg="Cliente desactivado", sev="success")


@router.post("/clientes/{cliente_id}/eliminar", name="clientes_delete")
def clientes_delete(
    request: Request,
    cliente_id: int,
    db: Session = Depends(get_db),
):
    if (redir := guard_operacion_mutacion(request)) is not None:
        return redir
    cliente = crud_cliente.get_cliente(db, cliente_id)
    if not cliente:
        raise HTTPException(status_code=404, detail="Cliente no encontrado")

    result = crud_cliente.eliminar_cliente(db, cliente)
    sev = "success" if result.accion == "eliminado" else "warning"
    return _redirect(request, "clientes_list", msg=result.mensaje, sev=sev)


@router.get(
    "/clientes/carga-masiva",
    response_class=HTMLResponse,
    name="clientes_carga_masiva_form",
)
def clientes_carga_masiva_form(request: Request):
    if (redir := guard_operacion_consulta(request)) is not None:
        return redir
    return templates.TemplateResponse(
        "clientes/clientes_carga_masiva.html",
        {
            "request": request,
            "active_menu": "clientes",
            "bulk_csv_max_mb": round(BULK_CSV_MAX_BYTES / (1024 * 1024), 2),
            "bulk_csv_max_rows": BULK_CSV_MAX_ROWS,
        },
    )


@router.post("/clientes/carga-masiva", name="clientes_carga_masiva_upload")
async def clientes_carga_masiva_upload(
    request: Request,
    archivo: UploadFile = File(...),
    db: Session = Depends(get_db),
):
    if (redir := guard_operacion_mutacion(request)) is not None:
        return redir
    filename = (archivo.filename or "").lower()
    if not filename.endswith((".csv", ".txt")):
        return _redirect(request, "clientes_list", msg="Formato inválido", sev="warning")

    contenido = await archivo.read()
    if len(contenido) > BULK_CSV_MAX_BYTES:
        return _redirect(
            request,
            "clientes_carga_masiva_form",
            msg=(
                f"El archivo supera el tamaño máximo permitido ({round(BULK_CSV_MAX_BYTES / (1024 * 1024), 2)} MiB). "
                "Divida la carga o comprima el CSV."
            ),
            sev="warning",
        )

    texto = contenido.decode("utf-8-sig")
    lineas_aprox = max(0, texto.count("\n") - 1)
    if lineas_aprox > BULK_CSV_MAX_ROWS:
        return _redirect(
            request,
            "clientes_carga_masiva_form",
            msg=(
                f"El CSV supera el máximo de {BULK_CSV_MAX_ROWS} filas de datos permitidas por carga "
                f"(aprox. {lineas_aprox} líneas detectadas). Divida el archivo e importe en partes."
            ),
            sev="warning",
        )

    reader = csv.DictReader(io.StringIO(texto))

    creados = 0
    omitidos = 0

    for row in reader:
        rut = (row.get("rut") or row.get("RUT") or "").strip()
        razon_social = (row.get("razon_social") or row.get("RAZON_SOCIAL") or "").strip()

        if not rut or not razon_social:
            omitidos += 1
            continue

        try:
            data = ClienteCreate(
                rut=rut,
                razon_social=razon_social,
                nombre_fantasia=(row.get("nombre_fantasia") or row.get("NOMBRE_FANTASIA") or "").strip() or None,
                giro=(row.get("giro") or row.get("GIRO") or "").strip() or None,
                direccion=(row.get("direccion") or row.get("DIRECCION") or "").strip() or None,
                comuna=(row.get("comuna") or row.get("COMUNA") or "").strip() or None,
                ciudad=(row.get("ciudad") or row.get("CIUDAD") or "").strip() or None,
                telefono=(row.get("telefono") or row.get("TELEFONO") or "").strip() or None,
                email=(row.get("email") or row.get("EMAIL") or "").strip() or None,
                activo=str(row.get("activo") or row.get("ACTIVO") or "true").lower() in ("1", "true", "si", "sí"),
            )
            crud_cliente.crear_cliente(db, data)
            creados += 1
        except Exception:
            omitidos += 1

    return _redirect(
        request,
        "clientes_list",
        msg=f"Carga finalizada: creados={creados}, omitidos={omitidos}.",
        sev="success",
    )