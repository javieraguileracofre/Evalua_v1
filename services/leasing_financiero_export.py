# services/leasing_financiero_export.py
# -*- coding: utf-8 -*-
from __future__ import annotations

import io
import re
from datetime import date
from decimal import Decimal
from typing import TYPE_CHECKING, List

from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.page import PageMargins

from schemas.comercial.leasing_amortizacion import AmortizacionCuota
from services.leasing_financiero_estados import etiqueta_estado

if TYPE_CHECKING:
    from models.comercial.leasing_financiero_cotizacion import LeasingFinancieroCotizacion

NAVY = "0B1F3B"
GOLD = "D4AF37"
HEADER_FILL = PatternFill(start_color=NAVY, end_color=NAVY, fill_type="solid")
GOLD_FILL = PatternFill(start_color="F7F1DE", end_color="F7F1DE", fill_type="solid")
ALT_FILL = PatternFill(start_color="F8FAFC", end_color="F8FAFC", fill_type="solid")
TOTAL_FILL = PatternFill(start_color="EEF2FF", end_color="EEF2FF", fill_type="solid")
THIN = Border(
    left=Side(style="thin", color="D1D5DB"),
    right=Side(style="thin", color="D1D5DB"),
    top=Side(style="thin", color="D1D5DB"),
    bottom=Side(style="thin", color="D1D5DB"),
)
WHITE_BOLD = Font(bold=True, color="FFFFFF", name="Calibri", size=10)
TITLE_FONT = Font(bold=True, color=NAVY, name="Calibri", size=16)
SUB_FONT = Font(bold=True, color=NAVY, name="Calibri", size=12)
LABEL_FONT = Font(bold=True, name="Calibri", size=10, color="374151")
BODY_FONT = Font(name="Calibri", size=10)


def _decimales_moneda(moneda: str | None) -> int:
    m = str(moneda or "CLP").upper()
    if m in {"UF", "USD"}:
        return 2
    return 0


def _num_format(moneda: str | None) -> str:
    if _decimales_moneda(moneda) == 2:
        return '#,##0.00'
    return '#,##0'


def _cliente_slug(cotizacion: "LeasingFinancieroCotizacion") -> str:
    nombre = ""
    cli = getattr(cotizacion, "cliente", None)
    if cli is not None:
        nombre = str(getattr(cli, "razon_social", "") or "")
    slug = re.sub(r"[^\w\-]+", "_", nombre.strip(), flags=re.UNICODE)
    slug = slug.strip("_")[:40] or "cliente"
    return slug


def nombre_archivo_export(cotizacion: "LeasingFinancieroCotizacion", ext: str) -> str:
    cid = getattr(cotizacion, "id", "sin_id")
    return f"leasing_financiero_cotizacion_{cid}_{_cliente_slug(cotizacion)}.{ext}"


def _tasa_pct(cotizacion) -> float:
    t = getattr(cotizacion, "tasa", None)
    if t is None:
        return 0.0
    t = Decimal(str(t))
    if t <= Decimal("1"):
        t = t * Decimal("100")
    return float(t)


def _totales(tabla: List[AmortizacionCuota]) -> dict[str, Decimal]:
    rentas = [c for c in tabla if not c.es_gracia and not c.es_opcion_compra]
    return {
        "cuota": sum((c.cuota for c in tabla), Decimal("0")),
        "interes": sum((c.interes for c in tabla), Decimal("0")),
        "amortizacion": sum((c.amortizacion for c in tabla), Decimal("0")),
        "iva": sum((getattr(c, "iva", Decimal("0")) or Decimal("0") for c in tabla), Decimal("0")),
        "total_cuota": sum(
            (getattr(c, "total_cuota", None) or c.cuota for c in tabla),
            Decimal("0"),
        ),
        "rentas": sum((c.cuota for c in rentas), Decimal("0")),
        "residual": sum((c.cuota for c in tabla if c.es_opcion_compra), Decimal("0")),
    }


def build_amortizacion_excel(
    cotizacion: "LeasingFinancieroCotizacion",
    tabla: List[AmortizacionCuota],
    resumen: object | None = None,
) -> io.BytesIO:
    wb = Workbook()
    _hoja_resumen(wb.active, cotizacion, tabla, resumen)
    _hoja_amortizacion(wb.create_sheet("Amortización"), cotizacion, tabla)

    output = io.BytesIO()
    wb.save(output)
    output.seek(0)
    return output


def _set_col_widths(ws, widths: dict[int, float]) -> None:
    for col, width in widths.items():
        ws.column_dimensions[get_column_letter(col)].width = width


def _kv(ws, row: int, label: str, value, *, money: bool = False, moneda: str | None = None, pct: bool = False) -> None:
    c1 = ws.cell(row=row, column=1, value=label)
    c1.font = LABEL_FONT
    c1.fill = GOLD_FILL
    c1.border = THIN
    c2 = ws.cell(row=row, column=2, value=value)
    c2.font = BODY_FONT
    c2.border = THIN
    if money and isinstance(value, (int, float, Decimal)):
        c2.number_format = _num_format(moneda)
        c2.alignment = Alignment(horizontal="right")
    elif pct and isinstance(value, (int, float, Decimal)):
        c2.number_format = '0.00" %"'
        c2.alignment = Alignment(horizontal="right")
    ws.merge_cells(start_row=row, start_column=2, end_row=row, end_column=4)


def _hoja_resumen(ws, cotizacion, tabla, resumen) -> None:
    ws.title = "Resumen"
    ws.page_setup.orientation = "landscape"
    ws.page_setup.fitToPage = True
    ws.page_setup.fitToWidth = 1
    ws.page_setup.fitToHeight = 1
    ws.page_margins = PageMargins(left=0.5, right=0.5, top=0.6, bottom=0.5)
    ws.sheet_properties.tabColor = NAVY
    moneda = str(getattr(cotizacion, "moneda", None) or "CLP")
    cli = getattr(cotizacion, "cliente", None)
    tot = _totales(tabla)
    cuota_est = None
    rentas = [c for c in tabla if not c.es_gracia and not c.es_opcion_compra]
    if rentas:
        cuota_est = rentas[0].cuota
    if resumen is not None and getattr(resumen, "renta_mensual", None) is not None:
        cuota_est = resumen.renta_mensual

    ws.merge_cells("A1:D1")
    t = ws.cell(row=1, column=1, value="EvaluaERP  ·  Cotización Leasing Financiero")
    t.font = TITLE_FONT
    t.alignment = Alignment(vertical="center")
    ws.row_dimensions[1].height = 22

    ws.merge_cells("A2:D2")
    sub = ws.cell(
        row=2,
        column=1,
        value=f"Cotización #{getattr(cotizacion, 'id', '')}  ·  Emisión {date.today().isoformat()}  ·  {etiqueta_estado(getattr(cotizacion, 'estado', None))}",
    )
    sub.font = Font(name="Calibri", size=10, color="6B7280")

    row = 4
    ws.cell(row=row, column=1, value="Cliente y activo").font = SUB_FONT
    ws.merge_cells(start_row=row, start_column=1, end_row=row, end_column=4)
    row += 1
    _kv(ws, row, "Cliente", getattr(cli, "razon_social", None) or "—")
    row += 1
    _kv(ws, row, "RUT", getattr(cli, "rut", None) or "—")
    row += 1
    _kv(ws, row, "Tipo de activo", getattr(cotizacion, "bien_tipo", None) or "—")
    row += 1
    _kv(ws, row, "Descripción del activo", getattr(cotizacion, "bien_descripcion", None) or "—")
    row += 1
    prov = getattr(cotizacion, "proveedor", None)
    _kv(
        ws,
        row,
        "Proveedor sugerido",
        getattr(prov, "razon_social", None) or getattr(cotizacion, "concesionario", None) or "—",
    )
    row += 1
    _kv(ws, row, "Observaciones", getattr(cotizacion, "observaciones", None) or "—")

    row += 2
    ws.cell(row=row, column=1, value="Condiciones financieras").font = SUB_FONT
    ws.merge_cells(start_row=row, start_column=1, end_row=row, end_column=4)
    row += 1
    valor_neto = getattr(cotizacion, "valor_neto", None) or Decimal("0")
    pie = getattr(resumen, "pago_inicial", None)
    if pie is None:
        pie = Decimal("0")
    monto_fin = getattr(cotizacion, "monto_financiado", None) or valor_neto
    _kv(ws, row, "Moneda", moneda)
    row += 1
    _kv(ws, row, "Valor del activo", float(valor_neto or 0), money=True, moneda=moneda)
    row += 1
    _kv(ws, row, "Pie / cuota inicial", float(pie or 0), money=True, moneda=moneda)
    row += 1
    _kv(ws, row, "Monto a financiar", float(monto_fin or 0), money=True, moneda=moneda)
    row += 1
    tipo_tasa = str(getattr(cotizacion, "tasa_tipo", "ANUAL") or "ANUAL").upper()
    _kv(ws, row, "Tipo de tasa", tipo_tasa)
    row += 1
    _kv(ws, row, "Tasa", _tasa_pct(cotizacion), pct=True)
    row += 1
    _kv(ws, row, "Plazo (meses)", int(getattr(cotizacion, "plazo", 0) or 0))
    row += 1
    _kv(ws, row, "Periodicidad", str(getattr(cotizacion, "periodicidad", "MENSUAL") or "MENSUAL"))
    row += 1
    _kv(ws, row, "Fecha inicio estimada", str(getattr(cotizacion, "fecha_inicio", None) or "—"))
    row += 1
    _kv(ws, row, "Valor residual / opción de compra", float(getattr(cotizacion, "opcion_compra", 0) or 0), money=True, moneda=moneda)
    row += 1
    _kv(ws, row, "Gastos administrativos", float(getattr(cotizacion, "gastos_administrativos", 0) or 0), money=True, moneda=moneda)
    row += 1
    _kv(ws, row, "Comisión", float(getattr(cotizacion, "comision_apertura", 0) or 0), money=True, moneda=moneda)
    row += 1
    _kv(ws, row, "Seguro (UF)", float(getattr(cotizacion, "seguro_monto_uf", 0) or 0), money=True, moneda="UF")

    row += 2
    ws.cell(row=row, column=1, value="Indicadores").font = SUB_FONT
    ws.merge_cells(start_row=row, start_column=1, end_row=row, end_column=4)
    row += 1
    _kv(ws, row, "Cuota estimada (neta)", float(cuota_est or 0), money=True, moneda=moneda)
    row += 1
    _kv(ws, row, "Total intereses", float(tot["interes"]), money=True, moneda=moneda)
    row += 1
    _kv(ws, row, "Total IVA cuotas", float(tot["iva"]), money=True, moneda=moneda)
    row += 1
    total_pagar = Decimal(str(pie or 0)) + tot["total_cuota"]
    if resumen is not None and getattr(resumen, "total_desembolso", None) is not None:
        total_pagar = Decimal(str(resumen.total_desembolso))
    _kv(ws, row, "Total a pagar", float(total_pagar), money=True, moneda=moneda)
    row += 1
    _kv(ws, row, "Valor residual", float(tot["residual"]), money=True, moneda=moneda)

    row += 2
    ws.merge_cells(start_row=row, start_column=1, end_row=row, end_column=4)
    nota = ws.cell(
        row=row,
        column=1,
        value=(
            "Documento generado por EvaluaERP. Cotización referencial sujeta a evaluación crediticia "
            "y formalización del acuerdo. El activo no se adquiere al cotizar: la compra al proveedor "
            "se habilita únicamente después del acuerdo firmado."
        ),
    )
    nota.font = Font(name="Calibri", size=8, italic=True, color="6B7280")
    nota.alignment = Alignment(wrap_text=True)
    ws.row_dimensions[row].height = 36
    _set_col_widths(ws, {1: 38, 2: 28, 3: 18, 4: 18})
    ws.freeze_panes = "A4"
    ws.print_title_rows = "1:2"


def _hoja_amortizacion(ws, cotizacion, tabla: List[AmortizacionCuota]) -> None:
    ws.sheet_properties.tabColor = GOLD
    ws.page_setup.orientation = "landscape"
    ws.page_setup.fitToPage = True
    ws.page_setup.fitToWidth = 1
    ws.page_setup.fitToHeight = 0
    ws.page_margins = PageMargins(left=0.4, right=0.4, top=0.5, bottom=0.5)
    moneda = str(getattr(cotizacion, "moneda", None) or "CLP")
    nf = _num_format(moneda)

    ws.merge_cells("A1:J1")
    t = ws.cell(row=1, column=1, value=f"Tabla de amortización · Cotización #{getattr(cotizacion, 'id', '')}")
    t.font = TITLE_FONT

    headers = [
        "N°",
        "Fecha vencimiento",
        "Saldo inicial",
        "Cuota neta",
        "Interés",
        "Amortización",
        "IVA",
        "Total cuota",
        "Saldo final",
        "Tipo",
    ]
    for col, h in enumerate(headers, start=1):
        cell = ws.cell(row=3, column=col, value=h)
        cell.font = WHITE_BOLD
        cell.fill = HEADER_FILL
        cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
        cell.border = THIN
    ws.row_dimensions[3].height = 28
    ws.auto_filter.ref = f"A3:J{3 + max(len(tabla), 1)}"
    ws.freeze_panes = "A4"

    money_cols = {3, 4, 5, 6, 7, 8, 9}
    row = 4
    for idx, cuota in enumerate(tabla):
        if cuota.es_gracia:
            tipo = "Gracia"
        elif cuota.es_opcion_compra:
            tipo = "Residual / opción de compra"
        else:
            tipo = "Cuota"
        iva = getattr(cuota, "iva", None) or Decimal("0")
        total_c = getattr(cuota, "total_cuota", None) or (cuota.cuota + iva)
        values = [
            cuota.numero_cuota,
            cuota.fecha_cuota,
            float(cuota.saldo_inicial),
            float(cuota.cuota),
            float(cuota.interes),
            float(cuota.amortizacion),
            float(iva),
            float(total_c),
            float(cuota.saldo_final),
            tipo,
        ]
        fill = ALT_FILL if idx % 2 else None
        if cuota.es_opcion_compra:
            fill = GOLD_FILL
        for col, val in enumerate(values, start=1):
            cell = ws.cell(row=row, column=col, value=val)
            cell.font = BODY_FONT
            cell.border = THIN
            if fill:
                cell.fill = fill
            if col in money_cols:
                cell.number_format = nf
                cell.alignment = Alignment(horizontal="right")
            elif col == 2 and cuota.fecha_cuota:
                cell.number_format = "YYYY-MM-DD"
                cell.alignment = Alignment(horizontal="center")
            else:
                cell.alignment = Alignment(horizontal="center")
        row += 1

    tot = _totales(tabla)
    totals = [
        "",
        "TOTALES",
        "",
        float(tot["cuota"]),
        float(tot["interes"]),
        float(tot["amortizacion"]),
        float(tot["iva"]),
        float(tot["total_cuota"]),
        "",
        "",
    ]
    for col, val in enumerate(totals, start=1):
        cell = ws.cell(row=row, column=col, value=val if val != "" else None)
        cell.font = Font(bold=True, name="Calibri", size=10, color=NAVY)
        cell.fill = TOTAL_FILL
        cell.border = THIN
        if col in money_cols and val != "":
            cell.number_format = nf
            cell.alignment = Alignment(horizontal="right")
    _set_col_widths(ws, {1: 6, 2: 18, 3: 16, 4: 14, 5: 14, 6: 16, 7: 12, 8: 14, 9: 16, 10: 26})
    ws.print_title_rows = "1:3"


def _fmt_moneda(value: Decimal | int | float, moneda: str | None) -> str:
    dec = _decimales_moneda(moneda)
    fmt = f"{{:,.{dec}f}}"
    return fmt.format(value).replace(",", "X").replace(".", ",").replace("X", ".")


def build_amortizacion_pdf(
    cotizacion: "LeasingFinancieroCotizacion",
    tabla: List[AmortizacionCuota],
    resumen: object | None = None,
) -> io.BytesIO:
    from services.leasing_financiero_cotizacion_pdf import build_cotizador_pdf

    pdf = build_cotizador_pdf(cotizacion=cotizacion, resumen=resumen, tabla=tabla)
    return io.BytesIO(pdf)
