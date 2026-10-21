# services/leasing_financiero_cotizacion_pdf.py
# -*- coding: utf-8 -*-
"""PDF corporativo de cotización de leasing financiero."""
from __future__ import annotations

from datetime import date
from decimal import Decimal
from io import BytesIO
from typing import Any
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_RIGHT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.platypus import (
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

from services.leasing_financiero_estados import etiqueta_estado

NAVY = colors.HexColor("#0B1F3B")
GOLD = colors.HexColor("#D4AF37")
MUTED = colors.HexColor("#6B7280")
LINE = colors.HexColor("#E5E7EB")
ROW_ALT = colors.HexColor("#F8FAFC")
HEADER_BG = colors.HexColor("#0B1F3B")


def _fmt_money(x: Any, moneda: str = "CLP") -> str:
    try:
        v = float(x or 0)
    except (TypeError, ValueError):
        v = 0.0
    m = (moneda or "CLP").upper()
    if m in {"UF", "USD"}:
        s = f"{v:,.2f}"
    else:
        s = f"{v:,.0f}"
    return s.replace(",", ".")


def _p(text: Any, style: ParagraphStyle) -> Paragraph:
    return Paragraph(escape(str(text if text not in (None, "") else "—")), style)


def _header_footer(canvas, doc) -> None:
    canvas.saveState()
    width, height = A4
    canvas.setFillColor(NAVY)
    canvas.rect(0, height - 32, width, 32, fill=1, stroke=0)
    canvas.setFillColor(GOLD)
    canvas.rect(0, height - 34, width, 2.2, fill=1, stroke=0)
    canvas.setFillColor(colors.white)
    canvas.setFont("Helvetica-Bold", 9)
    from core.company_context import document_footer_text, document_header_text

    issuer = document_header_text() or "Cotización"
    canvas.drawString(1.4 * cm, height - 20, issuer[:70])
    canvas.setFont("Helvetica", 9)
    canvas.drawRightString(width - 1.4 * cm, height - 20, "Cotización Leasing Financiero")

    canvas.setFillColor(LINE)
    canvas.rect(0, 0, width, 28, fill=1, stroke=0)
    canvas.setFillColor(MUTED)
    canvas.setFont("Helvetica", 7.5)
    canvas.drawString(
        1.4 * cm,
        12,
        "Documento confidencial · " + document_footer_text(),
    )
    canvas.drawRightString(width - 1.4 * cm, 12, f"Página {doc.page}")
    canvas.restoreState()


def build_cotizador_pdf(
    *,
    cotizacion: Any,
    resumen: Any,
    tabla: list[Any] | None = None,
    condiciones: str | None = None,
) -> bytes:
    buf = BytesIO()
    doc = SimpleDocTemplate(
        buf,
        pagesize=A4,
        rightMargin=1.3 * cm,
        leftMargin=1.3 * cm,
        topMargin=1.6 * cm,
        bottomMargin=1.4 * cm,
        title=f"Cotización Leasing Financiero #{getattr(cotizacion, 'id', '')}",
        author="EvaluaERP",
    )
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        "LFTitle",
        parent=styles["Heading1"],
        fontName="Helvetica-Bold",
        fontSize=14,
        textColor=NAVY,
        spaceAfter=2,
        leading=18,
    )
    h3 = ParagraphStyle(
        "LFH3",
        parent=styles["Heading3"],
        fontName="Helvetica-Bold",
        fontSize=10,
        textColor=NAVY,
        spaceBefore=8,
        spaceAfter=4,
        leading=13,
    )
    small = ParagraphStyle(
        "LFSmall",
        parent=styles["Normal"],
        fontName="Helvetica",
        fontSize=8,
        textColor=MUTED,
        leading=11,
    )
    body = ParagraphStyle(
        "LFBody",
        parent=styles["Normal"],
        fontName="Helvetica",
        fontSize=8.5,
        leading=11.5,
        textColor=colors.HexColor("#111827"),
    )
    cell = ParagraphStyle(
        "LFCell",
        parent=styles["Normal"],
        fontName="Helvetica",
        fontSize=7,
        leading=9,
        textColor=colors.HexColor("#111827"),
    )
    cell_r = ParagraphStyle("LFCellR", parent=cell, alignment=TA_RIGHT)
    cell_c = ParagraphStyle("LFCellC", parent=cell, alignment=TA_CENTER)
    th = ParagraphStyle(
        "LFTh",
        parent=styles["Normal"],
        fontName="Helvetica-Bold",
        fontSize=7,
        leading=9,
        textColor=colors.white,
        alignment=TA_CENTER,
    )
    legal = ParagraphStyle(
        "LFLegal",
        parent=styles["Normal"],
        fontName="Helvetica",
        fontSize=7.5,
        leading=10,
        textColor=MUTED,
    )

    story: list[Any] = []
    cli = getattr(cotizacion, "cliente", None)
    moneda = str(getattr(cotizacion, "moneda", "CLP") or "CLP")
    cid = getattr(cotizacion, "id", "—")
    emision = date.today().isoformat()

    story.append(Paragraph("Cotización Leasing Financiero", title_style))
    story.append(
        Paragraph(
            f"N° {escape(str(cid))}  ·  Fecha de emisión {emision}  ·  "
            f"Estado: {escape(etiqueta_estado(getattr(cotizacion, 'estado', None)))}",
            small,
        )
    )
    story.append(Spacer(1, 0.2 * cm))

    def _kv_table(rows: list[list[str]], col1: float = 5.2, col2: float = 12.0) -> Table:
        data = []
        for label, value in rows:
            data.append([Paragraph(f"<b>{escape(label)}</b>", cell), _p(value, cell)])
        t = Table(data, colWidths=[col1 * cm, col2 * cm])
        t.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (0, -1), colors.HexColor("#F3F4F6")),
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    ("LEFTPADDING", (0, 0), (-1, -1), 5),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 5),
                    ("TOPPADDING", (0, 0), (-1, -1), 3),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
                    ("GRID", (0, 0), (-1, -1), 0.25, LINE),
                ]
            )
        )
        return t

    prov = getattr(cotizacion, "proveedor", None)
    story.append(Paragraph("Datos del cliente", h3))
    story.append(
        _kv_table(
            [
                ["Cliente", getattr(cli, "razon_social", None) or "—"],
                ["RUT", getattr(cli, "rut", None) or "—"],
                ["Email", getattr(cli, "email", None) or "—"],
                ["Ejecutivo", getattr(cotizacion, "ejecutivo", None) or "—"],
            ]
        )
    )

    story.append(Paragraph("Datos del activo", h3))
    story.append(
        _kv_table(
            [
                ["Tipo de activo", getattr(cotizacion, "bien_tipo", None) or "—"],
                ["Descripción", getattr(cotizacion, "bien_descripcion", None) or "—"],
                [
                    "Proveedor sugerido",
                    getattr(prov, "razon_social", None)
                    or getattr(cotizacion, "concesionario", None)
                    or "—",
                ],
                ["Marca / modelo", " / ".join(
                    x for x in (
                        getattr(getattr(cotizacion, "activo", None), "marca", None),
                        getattr(getattr(cotizacion, "activo", None), "modelo", None),
                    ) if x
                ) or "—"],
            ]
        )
    )

    tasa = getattr(cotizacion, "tasa", None)
    if tasa is None:
        tasa_txt = "—"
    else:
        tdec = Decimal(str(tasa))
        if tdec <= 1:
            tdec = tdec * Decimal("100")
        tasa_txt = f"{float(tdec):.2f}% {str(getattr(cotizacion, 'tasa_tipo', 'ANUAL') or 'ANUAL').lower()}"

    pie = getattr(resumen, "pago_inicial", 0) if resumen is not None else 0
    cuota = getattr(resumen, "renta_mensual", 0) if resumen is not None else 0
    intereses = getattr(resumen, "total_intereses", 0) if resumen is not None else 0
    total_pagar = getattr(resumen, "total_desembolso", 0) if resumen is not None else 0
    monto_fin = getattr(resumen, "monto_financiado", None) if resumen is not None else None
    if monto_fin is None:
        monto_fin = getattr(cotizacion, "monto_financiado", 0)

    story.append(Paragraph("Condiciones financieras", h3))
    story.append(
        _kv_table(
            [
                ["Moneda", moneda],
                ["Valor del activo", f"{_fmt_money(getattr(cotizacion, 'valor_neto', 0), moneda)} {moneda}"],
                ["Pie / cuota inicial", f"{_fmt_money(pie, moneda)} {moneda}"],
                ["Monto a financiar", f"{_fmt_money(monto_fin, moneda)} {moneda}"],
                ["Tasa", tasa_txt],
                ["Plazo", f"{getattr(cotizacion, 'plazo', '—')} meses"],
                ["Periodicidad de pago", str(getattr(cotizacion, "periodicidad", "MENSUAL") or "MENSUAL")],
                ["Fecha de inicio estimada", str(getattr(cotizacion, "fecha_inicio", None) or "—")],
                [
                    "Valor residual / opción de compra",
                    f"{_fmt_money(getattr(cotizacion, 'opcion_compra', 0), moneda)} {moneda}",
                ],
                [
                    "Gastos administrativos",
                    f"{_fmt_money(getattr(cotizacion, 'gastos_administrativos', 0), moneda)} {moneda}",
                ],
                ["Comisión", f"{_fmt_money(getattr(cotizacion, 'comision_apertura', 0), moneda)} {moneda}"],
                ["Seguro (UF)", _fmt_money(getattr(cotizacion, "seguro_monto_uf", 0), "UF")],
            ]
        )
    )

    story.append(Paragraph("Resumen financiero", h3))
    kpi = [
        [
            Paragraph("<b>Indicador</b>", th),
            Paragraph("<b>Monto</b>", th),
        ],
        ["Valor del activo", f"{_fmt_money(getattr(cotizacion, 'valor_neto', 0), moneda)} {moneda}"],
        ["Pie", f"{_fmt_money(pie, moneda)} {moneda}"],
        ["Monto financiado", f"{_fmt_money(monto_fin, moneda)} {moneda}"],
        ["Cuota estimada (neta)", f"{_fmt_money(cuota, moneda)} {moneda}"],
        ["Total intereses", f"{_fmt_money(intereses, moneda)} {moneda}"],
        ["Total a pagar", f"{_fmt_money(total_pagar, moneda)} {moneda}"],
        [
            "Valor residual",
            f"{_fmt_money(getattr(cotizacion, 'opcion_compra', 0), moneda)} {moneda}",
        ],
    ]
    t1 = Table(kpi, colWidths=[9 * cm, 8.2 * cm])
    t1.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), HEADER_BG),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("FONTNAME", (0, 1), (-1, -1), "Helvetica"),
                ("FONTSIZE", (0, 0), (-1, -1), 8),
                ("ALIGN", (1, 1), (1, -1), "RIGHT"),
                ("GRID", (0, 0), (-1, -1), 0.25, LINE),
                ("BACKGROUND", (0, 1), (-1, -1), colors.white),
                ("BACKGROUND", (0, -1), (-1, -1), colors.HexColor("#EEF2FF")),
                ("TOPPADDING", (0, 0), (-1, -1), 4),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
                ("LEFTPADDING", (0, 0), (-1, -1), 6),
            ]
        )
    )
    story.append(t1)

    obs = getattr(cotizacion, "observaciones", None)
    if obs:
        story.append(Paragraph("Observaciones comerciales", h3))
        story.append(_p(obs, body))

    if condiciones:
        story.append(Paragraph("Condiciones aceptadas", h3))
        story.append(Paragraph(escape(str(condiciones)).replace("\n", "<br/>"), body))

    if tabla:
        story.append(Paragraph("Tabla de amortización", h3))
        story.append(
            Paragraph(
                "Cuota neta = interés + amortización de capital. "
                "Total cuota = cuota neta + IVA (si corresponde). "
                "El residual / opción de compra se informa en la última línea cuando aplica.",
                small,
            )
        )
        headers = [
            "#",
            "Vencimiento",
            "Saldo inicial",
            "Cuota",
            "Interés",
            "Amortización",
            "IVA",
            "Total",
            "Saldo final",
        ]
        data = [[Paragraph(h, th) for h in headers]]
        for c in tabla:
            tipo_mark = ""
            if getattr(c, "es_opcion_compra", False):
                tipo_mark = " *"
            elif getattr(c, "es_gracia", False):
                tipo_mark = " g"
            fecha = str(getattr(c, "fecha_cuota", None) or "—")
            iva = getattr(c, "iva", 0) or 0
            total_c = getattr(c, "total_cuota", None)
            if total_c is None:
                total_c = (getattr(c, "cuota", 0) or 0) + iva
            data.append(
                [
                    Paragraph(f"{getattr(c, 'numero_cuota', '')}{tipo_mark}", cell_c),
                    Paragraph(fecha, cell_c),
                    Paragraph(_fmt_money(getattr(c, "saldo_inicial", 0), moneda), cell_r),
                    Paragraph(_fmt_money(getattr(c, "cuota", 0), moneda), cell_r),
                    Paragraph(_fmt_money(getattr(c, "interes", 0), moneda), cell_r),
                    Paragraph(_fmt_money(getattr(c, "amortizacion", 0), moneda), cell_r),
                    Paragraph(_fmt_money(iva, moneda), cell_r),
                    Paragraph(_fmt_money(total_c, moneda), cell_r),
                    Paragraph(_fmt_money(getattr(c, "saldo_final", 0), moneda), cell_r),
                ]
            )

        tot_cuota = sum((getattr(c, "cuota", 0) or 0 for c in tabla), Decimal("0"))
        tot_int = sum((getattr(c, "interes", 0) or 0 for c in tabla), Decimal("0"))
        tot_amort = sum((getattr(c, "amortizacion", 0) or 0 for c in tabla), Decimal("0"))
        tot_iva = sum((getattr(c, "iva", 0) or 0 for c in tabla), Decimal("0"))
        tot_tot = sum(
            ((getattr(c, "total_cuota", None) or ((getattr(c, "cuota", 0) or 0) + (getattr(c, "iva", 0) or 0))) for c in tabla),
            Decimal("0"),
        )
        data.append(
            [
                Paragraph("", cell),
                Paragraph("<b>Totales</b>", cell),
                Paragraph("", cell),
                Paragraph(f"<b>{_fmt_money(tot_cuota, moneda)}</b>", cell_r),
                Paragraph(f"<b>{_fmt_money(tot_int, moneda)}</b>", cell_r),
                Paragraph(f"<b>{_fmt_money(tot_amort, moneda)}</b>", cell_r),
                Paragraph(f"<b>{_fmt_money(tot_iva, moneda)}</b>", cell_r),
                Paragraph(f"<b>{_fmt_money(tot_tot, moneda)}</b>", cell_r),
                Paragraph("", cell),
            ]
        )

        col_w = [1.15 * cm, 2.15 * cm, 2.15 * cm, 1.9 * cm, 1.8 * cm, 2.15 * cm, 1.55 * cm, 1.9 * cm, 2.15 * cm]
        t2 = Table(data, colWidths=col_w, repeatRows=1)
        style_cmds = [
            ("BACKGROUND", (0, 0), (-1, 0), HEADER_BG),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("GRID", (0, 0), (-1, -1), 0.2, LINE),
            ("TOPPADDING", (0, 0), (-1, -1), 3),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
            ("LEFTPADDING", (0, 0), (-1, -1), 3),
            ("RIGHTPADDING", (0, 0), (-1, -1), 3),
            ("BACKGROUND", (0, -1), (-1, -1), colors.HexColor("#EEF2FF")),
        ]
        for i in range(1, len(data) - 1):
            if i % 2 == 0:
                style_cmds.append(("BACKGROUND", (0, i), (-1, i), ROW_ALT))
            row_obj = tabla[i - 1] if i - 1 < len(tabla) else None
            if row_obj is not None and getattr(row_obj, "es_opcion_compra", False):
                style_cmds.append(("BACKGROUND", (0, i), (-1, i), colors.HexColor("#F7F1DE")))
        t2.setStyle(TableStyle(style_cmds))
        story.append(t2)
        story.append(Paragraph("* Opción de compra / valor residual &nbsp;&nbsp; g Periodo de gracia.", small))

    story.append(Spacer(1, 0.35 * cm))
    story.append(Paragraph("Notas legales y comerciales", h3))
    story.append(
        Paragraph(
            "1. Esta cotización es referencial y no constituye oferta irrevocable ni aprobación de crédito. "
            "Las condiciones finales quedan sujetas a evaluación comercial y crediticia de la compañía emisora y/o la "
            "entidad financiadora.<br/>"
            "2. En leasing financiero el activo se adquiere al proveedor <b>después</b> de firmar el acuerdo. "
            "Cotizar o aprobar condiciones no implica compra ni activación contable del bien.<br/>"
            "3. La tabla de amortización se calcula por método francés (cuota fija). La tasa anual se convierte "
            "a tasa periódica efectiva: i = (1 + r)^(1/n) − 1. Los montos se redondean a 2 decimales "
            "(HALF UP).<br/>"
            "4. El IVA informado es referencial según la configuración de la operación. El tratamiento tributario "
            "definitivo debe validarse con el área fiscal.<br/>"
            "5. Gastos, comisiones, seguros y tipo de cambio pueden variar a la fecha de formalización.",
            legal,
        )
    )

    doc.build(story, onFirstPage=_header_footer, onLaterPages=_header_footer)
    return buf.getvalue()
