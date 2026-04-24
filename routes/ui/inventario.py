# routes/ui/inventario.py
# -*- coding: utf-8 -*-
from __future__ import annotations

import csv
import logging
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
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from core.bulk_limits import BULK_CSV_MAX_BYTES, BULK_CSV_MAX_ROWS, LIST_PAGE_DEFAULT, LIST_PAGE_MAX
from core.paths import TEMPLATES_DIR
from core.public_errors import public_error_message
from crud.inventario import inventario as crud_inventario
from db.session import get_db
from schemas.inventario.inventario import (
    CategoriaProductoCreate,
    InventarioAjusteCreate,
    InventarioIngresoStockCreate,
    ProductoCreate,
    ProductoUpdate,
    UnidadMedidaCreate,
)

logger = logging.getLogger("evalua.inventario.ui")

router = APIRouter(prefix="/inventario", tags=["Inventario"])
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


def _to_int(value: str | None) -> int | None:
    if value is None:
        return None
    value = value.strip()
    if not value:
        return None
    try:
        return int(value)
    except ValueError as exc:
        raise ValueError("Se esperaba un valor entero válido.") from exc


def _to_float(value: str | None, default: float = 0.0) -> float:
    if value is None:
        return default
    value = value.replace(",", ".").strip()
    if not value:
        return default
    try:
        return float(value)
    except ValueError as exc:
        raise ValueError("Se esperaba un valor numérico válido.") from exc


def _to_bool(value: str | None, default: bool = False) -> bool:
    if value is None:
        return default
    return value.strip().lower() in ("true", "1", "si", "sí", "on")


@router.get("/productos/buscar-por-codigo", name="producto_buscar_por_codigo_api")
def producto_buscar_por_codigo_api(
    request: Request,
    codigo: str = Query(..., min_length=1),
    db: Session = Depends(get_db),
):
    termino = (codigo or "").strip()
    if not termino:
        return JSONResponse(
            status_code=400,
            content={
                "ok": False,
                "found": False,
                "message": "Debes indicar un código o código de barra.",
            },
        )

    producto = crud_inventario.buscar_producto_por_lector(db, termino)

    if not producto:
        return JSONResponse(
            content={
                "ok": True,
                "found": False,
                "message": "Producto no existe. Continúa con la creación de nuevo producto.",
                "codigo_consultado": termino,
            }
        )

    return JSONResponse(
        content={
            "ok": True,
            "found": True,
            "message": "Producto existente encontrado.",
            "producto": {
                "id": producto.id,
                "codigo": producto.codigo,
                "codigo_barra": producto.codigo_barra,
                "nombre": producto.nombre,
                "descripcion": producto.descripcion,
                "precio_compra": float(producto.precio_compra or 0),
                "precio_venta": float(producto.precio_venta or 0),
                "stock_minimo": float(producto.stock_minimo or 0),
                "stock_actual": float(producto.stock_actual or 0),
                "controla_stock": bool(getattr(producto, "controla_stock", True)),
                "permite_venta_fraccionada": bool(getattr(producto, "permite_venta_fraccionada", False)),
                "es_servicio": bool(getattr(producto, "es_servicio", False)),
                "activo": bool(getattr(producto, "activo", True)),
                "categoria_id": producto.categoria_id,
                "unidad_medida_id": producto.unidad_medida_id,
                "edit_url": str(request.url_for("producto_form_editar", producto_id=producto.id)),
            },
        }
    )


@router.get("/productos", response_class=HTMLResponse, name="productos_list")
def productos_list(
    request: Request,
    activos_solo: bool = Query(False),
    q: str | None = Query(None),
    skip: int = Query(0, ge=0),
    limit: int = Query(LIST_PAGE_DEFAULT, ge=1, le=LIST_PAGE_MAX),
    msg: str | None = Query(None),
    sev: str = Query("info"),
    db: Session = Depends(get_db),
):
    lim = min(max(limit, 1), LIST_PAGE_MAX)
    sk = max(skip, 0)
    productos, hay_mas = crud_inventario.listar_productos(
        db,
        activos_solo=activos_solo,
        q=q,
        skip=sk,
        limit=lim,
    )
    categorias = crud_inventario.listar_categorias(db)
    unidades = crud_inventario.listar_unidades_medida(db)

    return templates.TemplateResponse(
        "inventario/productos.html",
        {
            "request": request,
            "productos": productos,
            "categorias": categorias,
            "unidades": unidades,
            "activos_solo": activos_solo,
            "q": q or "",
            "skip": sk,
            "limit": lim,
            "hay_mas": hay_mas,
            "list_page_max": LIST_PAGE_MAX,
            "msg": msg,
            "sev": sev,
            "active_menu": "inventario",
        },
    )


@router.get("/producto/form", response_class=HTMLResponse, name="producto_form_nuevo")
def producto_form_nuevo(
    request: Request,
    msg: str | None = Query(None),
    sev: str = Query("info"),
    db: Session = Depends(get_db),
):
    categorias = crud_inventario.listar_categorias(db)
    unidades = crud_inventario.listar_unidades_medida(db)

    return templates.TemplateResponse(
        "inventario/producto_form.html",
        {
            "request": request,
            "producto": None,
            "categorias": categorias,
            "unidades": unidades,
            "msg": msg,
            "sev": sev,
            "active_menu": "inventario",
        },
    )


@router.get("/producto/form/{producto_id}", response_class=HTMLResponse, name="producto_form_editar")
def producto_form_editar(
    request: Request,
    producto_id: int,
    msg: str | None = Query(None),
    sev: str = Query("info"),
    db: Session = Depends(get_db),
):
    producto = crud_inventario.get_producto(db, producto_id)
    if not producto:
        raise HTTPException(status_code=404, detail="Producto no encontrado")

    categorias = crud_inventario.listar_categorias(db)
    unidades = crud_inventario.listar_unidades_medida(db)

    return templates.TemplateResponse(
        "inventario/producto_form.html",
        {
            "request": request,
            "producto": producto,
            "categorias": categorias,
            "unidades": unidades,
            "msg": msg,
            "sev": sev,
            "active_menu": "inventario",
        },
    )


@router.post("/productos", name="producto_create")
def producto_create(
    request: Request,
    nombre: str = Form(...),
    codigo: str | None = Form(None),
    codigo_barra: str | None = Form(None),
    categoria_id: str | None = Form(None),
    unidad_medida_id: str | None = Form(None),
    precio_compra: str | None = Form(None),
    precio_venta: str | None = Form(None),
    stock_minimo: str | None = Form(None),
    stock_actual: str | None = Form(None),
    descripcion: str | None = Form(None),
    controla_stock: str | None = Form(None),
    permite_venta_fraccionada: str | None = Form(None),
    es_servicio: str | None = Form(None),
    activo: str | None = Form(None),
    db: Session = Depends(get_db),
):
    try:
        data = ProductoCreate(
            codigo=(codigo or "").strip() or None,
            codigo_barra=(codigo_barra or "").strip() or None,
            nombre=nombre.strip(),
            descripcion=(descripcion or "").strip() or None,
            categoria_id=_to_int(categoria_id),
            unidad_medida_id=_to_int(unidad_medida_id),
            precio_compra=_to_float(precio_compra),
            precio_venta=_to_float(precio_venta),
            stock_minimo=_to_float(stock_minimo),
            stock_actual=_to_float(stock_actual),
            controla_stock=_to_bool(controla_stock, True),
            permite_venta_fraccionada=_to_bool(permite_venta_fraccionada, False),
            es_servicio=_to_bool(es_servicio, False),
            activo=_to_bool(activo, True),
        )

        crud_inventario.crear_producto(db, data)
        return _redirect(
            request,
            "productos_list",
            msg="Producto creado correctamente.",
            sev="success",
        )
    except ValueError as e:
        return _redirect(
            request,
            "producto_form_nuevo",
            msg=public_error_message(e),
            sev="warning",
        )
    except Exception as exc:
        return _redirect(
            request,
            "productos_list",
            msg=public_error_message(exc, default="Error al crear el producto."),
            sev="danger",
        )


@router.post("/productos/{producto_id}", name="producto_update")
def producto_update(
    request: Request,
    producto_id: int,
    nombre: str = Form(...),
    codigo_barra: str | None = Form(None),
    categoria_id: str | None = Form(None),
    unidad_medida_id: str | None = Form(None),
    precio_compra: str | None = Form(None),
    precio_venta: str | None = Form(None),
    stock_minimo: str | None = Form(None),
    descripcion: str | None = Form(None),
    controla_stock: str | None = Form(None),
    permite_venta_fraccionada: str | None = Form(None),
    es_servicio: str | None = Form(None),
    activo: str | None = Form(None),
    db: Session = Depends(get_db),
):
    producto = crud_inventario.get_producto(db, producto_id)
    if not producto:
        raise HTTPException(status_code=404, detail="Producto no encontrado")

    try:
        data = ProductoUpdate(
            nombre=nombre.strip(),
            descripcion=(descripcion or "").strip() or None,
            categoria_id=_to_int(categoria_id),
            unidad_medida_id=_to_int(unidad_medida_id),
            codigo_barra=(codigo_barra or "").strip() or None,
            precio_compra=_to_float(precio_compra),
            precio_venta=_to_float(precio_venta),
            stock_minimo=_to_float(stock_minimo),
            controla_stock=_to_bool(controla_stock, True),
            permite_venta_fraccionada=_to_bool(permite_venta_fraccionada, False),
            es_servicio=_to_bool(es_servicio, False),
            activo=_to_bool(activo, True),
        )

        crud_inventario.actualizar_producto(db, producto, data)
        return _redirect(
            request,
            "productos_list",
            msg="Producto actualizado correctamente.",
            sev="success",
        )
    except ValueError as e:
        return _redirect(
            request,
            "producto_form_editar",
            producto_id=producto_id,
            msg=public_error_message(e),
            sev="warning",
        )
    except Exception as exc:
        return _redirect(
            request,
            "productos_list",
            msg=public_error_message(exc, default="Error al actualizar el producto."),
            sev="danger",
        )


@router.post("/productos/{producto_id}/ingresar-stock", name="producto_ingresar_stock")
def producto_ingresar_stock(
    request: Request,
    producto_id: int,
    cantidad_ingreso: str = Form(...),
    costo_unitario_ingreso: str | None = Form(None),
    observacion_ingreso: str | None = Form(None),
    db: Session = Depends(get_db),
):
    producto = crud_inventario.get_producto(db, producto_id)
    if not producto:
        raise HTTPException(status_code=404, detail="Producto no encontrado")

    try:
        data = InventarioIngresoStockCreate(
            producto_id=producto_id,
            cantidad=_to_float(cantidad_ingreso),
            costo_unitario=_to_float(costo_unitario_ingreso),
            observacion=(observacion_ingreso or "").strip() or None,
        )
        crud_inventario.ingresar_stock_producto(
            db,
            data=data,
            usuario=None,
        )

        producto_actualizado = crud_inventario.get_producto(db, producto_id)

        return _redirect(
            request,
            "producto_form_nuevo",
            msg=(
                f"Stock ingresado correctamente para {producto.nombre}. "
                f"Nuevo stock: {producto_actualizado.stock_actual if producto_actualizado else producto.stock_actual}."
            ),
            sev="success",
        )
    except ValueError as e:
        return _redirect(
            request,
            "producto_form_nuevo",
            msg=public_error_message(e),
            sev="warning",
        )
    except Exception as exc:
        return _redirect(
            request,
            "producto_form_nuevo",
            msg=public_error_message(exc, default="No fue posible ingresar stock."),
            sev="danger",
        )


@router.post("/productos/{producto_id}/desactivar", name="producto_deactivate")
def producto_deactivate(
    request: Request,
    producto_id: int,
    db: Session = Depends(get_db),
):
    producto = crud_inventario.get_producto(db, producto_id)
    if not producto:
        raise HTTPException(status_code=404, detail="Producto no encontrado")

    try:
        crud_inventario.desactivar_producto(db, producto)
        return _redirect(
            request,
            "productos_list",
            msg="Producto desactivado correctamente.",
            sev="success",
        )
    except ValueError as e:
        return _redirect(
            request,
            "productos_list",
            msg=public_error_message(e),
            sev="warning",
        )
    except Exception as exc:
        return _redirect(
            request,
            "productos_list",
            msg=public_error_message(exc, default="Error al desactivar el producto."),
            sev="danger",
        )


@router.post("/productos/{producto_id}/activar", name="producto_activate")
def producto_activate(
    request: Request,
    producto_id: int,
    db: Session = Depends(get_db),
):
    producto = crud_inventario.get_producto(db, producto_id)
    if not producto:
        raise HTTPException(status_code=404, detail="Producto no encontrado")

    try:
        crud_inventario.activar_producto(db, producto)
        return _redirect(
            request,
            "productos_list",
            msg="Producto activado correctamente.",
            sev="success",
        )
    except ValueError as e:
        return _redirect(
            request,
            "productos_list",
            msg=public_error_message(e),
            sev="warning",
        )
    except Exception as exc:
        return _redirect(
            request,
            "productos_list",
            msg=public_error_message(exc, default="Error al activar el producto."),
            sev="danger",
        )


@router.post("/productos/{producto_id}/eliminar", name="producto_delete")
def producto_delete(
    request: Request,
    producto_id: int,
    db: Session = Depends(get_db),
):
    producto = crud_inventario.get_producto(db, producto_id)
    if not producto:
        raise HTTPException(status_code=404, detail="Producto no encontrado")

    try:
        crud_inventario.eliminar_producto(db, producto)
        return _redirect(
            request,
            "productos_list",
            msg="Producto eliminado correctamente.",
            sev="success",
        )
    except ValueError as e:
        return _redirect(
            request,
            "productos_list",
            msg=public_error_message(e),
            sev="warning",
        )
    except Exception as exc:
        return _redirect(
            request,
            "productos_list",
            msg=public_error_message(exc, default="Error al eliminar el producto."),
            sev="danger",
        )


@router.post("/productos/{producto_id}/ajustar", name="producto_ajustar_stock")
def producto_ajustar_stock(
    request: Request,
    producto_id: int,
    tipo_ajuste: str = Form(...),
    cantidad: str = Form(...),
    costo_unitario: str | None = Form(None),
    observacion: str | None = Form(None),
    db: Session = Depends(get_db),
):
    producto = crud_inventario.get_producto(db, producto_id)
    if not producto:
        raise HTTPException(status_code=404, detail="Producto no encontrado")

    try:
        data = InventarioAjusteCreate(
            producto_id=producto_id,
            tipo_ajuste=tipo_ajuste.strip().upper(),
            cantidad=_to_float(cantidad),
            costo_unitario=_to_float(costo_unitario),
            observacion=(observacion or "").strip() or None,
        )

        crud_inventario.registrar_ajuste_inventario(
            db,
            data=data,
            usuario=None,
        )

        return _redirect(
            request,
            "productos_list",
            msg=f"Ajuste registrado correctamente para {producto.nombre}.",
            sev="success",
        )
    except ValueError as e:
        return _redirect(
            request,
            "productos_list",
            msg=public_error_message(e),
            sev="warning",
        )
    except Exception as exc:
        return _redirect(
            request,
            "productos_list",
            msg=public_error_message(exc, default="No fue posible registrar el ajuste de inventario."),
            sev="danger",
        )


@router.get("/categorias", response_class=HTMLResponse, name="categorias_list")
def categorias_list(
    request: Request,
    msg: str | None = Query(None),
    sev: str = Query("info"),
    db: Session = Depends(get_db),
):
    categorias = crud_inventario.listar_categorias(db)
    return templates.TemplateResponse(
        "inventario/categorias.html",
        {
            "request": request,
            "categorias": categorias,
            "msg": msg,
            "sev": sev,
            "active_menu": "inventario",
        },
    )


@router.post("/categorias", name="categoria_create")
def categoria_create(
    request: Request,
    nombre: str = Form(...),
    descripcion: str | None = Form(None),
    db: Session = Depends(get_db),
):
    try:
        crud_inventario.crear_categoria(
            db,
            CategoriaProductoCreate(
                nombre=nombre.strip(),
                descripcion=(descripcion or "").strip() or None,
                activo=True,
            ),
        )
        return _redirect(
            request,
            "categorias_list",
            msg="Categoría creada correctamente.",
            sev="success",
        )
    except ValueError as e:
        return _redirect(
            request,
            "categorias_list",
            msg=public_error_message(e),
            sev="warning",
        )
    except Exception as exc:
        return _redirect(
            request,
            "categorias_list",
            msg=public_error_message(exc, default="Error al crear la categoría."),
            sev="danger",
        )


@router.get("/unidades-medida", response_class=HTMLResponse, name="unidades_medida_list")
def unidades_medida_list(
    request: Request,
    msg: str | None = Query(None),
    sev: str = Query("info"),
    db: Session = Depends(get_db),
):
    unidades = crud_inventario.listar_unidades_medida(db)
    return templates.TemplateResponse(
        "inventario/unidades_medida.html",
        {
            "request": request,
            "unidades": unidades,
            "msg": msg,
            "sev": sev,
            "active_menu": "inventario",
        },
    )


@router.post("/unidades-medida", name="unidad_medida_create")
def unidad_medida_create(
    request: Request,
    codigo: str = Form(...),
    nombre: str = Form(...),
    simbolo: str | None = Form(None),
    db: Session = Depends(get_db),
):
    try:
        crud_inventario.crear_unidad_medida(
            db,
            UnidadMedidaCreate(
                codigo=codigo.strip(),
                nombre=nombre.strip(),
                simbolo=(simbolo or "").strip() or None,
                activo=True,
            ),
        )
        return _redirect(
            request,
            "unidades_medida_list",
            msg="Unidad de medida creada correctamente.",
            sev="success",
        )
    except ValueError as e:
        return _redirect(
            request,
            "unidades_medida_list",
            msg=public_error_message(e),
            sev="warning",
        )
    except Exception as exc:
        return _redirect(
            request,
            "unidades_medida_list",
            msg=public_error_message(exc, default="Error al crear la unidad de medida."),
            sev="danger",
        )


@router.get("/productos/carga-masiva", response_class=HTMLResponse, name="productos_carga_masiva_form")
def productos_carga_masiva_form(
    request: Request,
    msg: str | None = Query(None),
    sev: str = Query("info"),
):
    return templates.TemplateResponse(
        "inventario/productos_carga_masiva.html",
        {
            "request": request,
            "msg": msg,
            "sev": sev,
            "active_menu": "inventario",
            "bulk_csv_max_mb": round(BULK_CSV_MAX_BYTES / (1024 * 1024), 2),
            "bulk_csv_max_rows": BULK_CSV_MAX_ROWS,
        },
    )


@router.post("/productos/carga-masiva", name="productos_carga_masiva_upload")
async def productos_carga_masiva_upload(
    request: Request,
    archivo: UploadFile = File(...),
    db: Session = Depends(get_db),
):
    try:
        nombre_archivo = (archivo.filename or "").lower()
        if not nombre_archivo.endswith(".csv"):
            return _redirect(
                request,
                "productos_carga_masiva_form",
                msg="Debes cargar un archivo CSV válido.",
                sev="warning",
            )

        contenido = await archivo.read()
        if len(contenido) > BULK_CSV_MAX_BYTES:
            return _redirect(
                request,
                "productos_carga_masiva_form",
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
                "productos_carga_masiva_form",
                msg=(
                    f"El CSV supera el máximo de {BULK_CSV_MAX_ROWS} filas de datos por carga "
                    f"(aprox. {lineas_aprox} líneas detectadas). Divida el archivo e importe en partes."
                ),
                sev="warning",
            )

        reader = csv.DictReader(io.StringIO(texto))

        creados = 0
        omitidos = 0

        for row in reader:
            try:
                nombre = (row.get("nombre") or "").strip()
                if not nombre:
                    omitidos += 1
                    continue

                data = ProductoCreate(
                    codigo=(row.get("codigo") or "").strip() or None,
                    codigo_barra=(row.get("codigo_barra") or "").strip() or None,
                    nombre=nombre,
                    descripcion=(row.get("descripcion") or "").strip() or None,
                    categoria_id=_to_int((row.get("categoria_id") or "").strip() or None),
                    unidad_medida_id=_to_int((row.get("unidad_medida_id") or "").strip() or None),
                    precio_compra=_to_float(row.get("precio_compra")),
                    precio_venta=_to_float(row.get("precio_venta")),
                    stock_minimo=_to_float(row.get("stock_minimo")),
                    stock_actual=_to_float(row.get("stock_actual")),
                    controla_stock=_to_bool(row.get("controla_stock"), True),
                    permite_venta_fraccionada=_to_bool(row.get("permite_venta_fraccionada"), False),
                    es_servicio=_to_bool(row.get("es_servicio"), False),
                    activo=_to_bool(row.get("activo"), True),
                )

                crud_inventario.crear_producto(db, data)
                creados += 1
            except Exception:
                omitidos += 1

        return _redirect(
            request,
            "productos_list",
            msg=f"Carga masiva completada. Creados: {creados}. Omitidos: {omitidos}.",
            sev="success",
        )

    except Exception as exc:
        logger.exception("Carga masiva de productos")
        return _redirect(
            request,
            "productos_carga_masiva_form",
            msg=public_error_message(exc, default="Ocurrió un error al procesar la carga masiva."),
            sev="danger",
        )