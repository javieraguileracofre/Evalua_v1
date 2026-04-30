# services/remuneraciones/liquidacion_pdf.py
# -*- coding: utf-8 -*-
from __future__ import annotations

from decimal import Decimal
from io import BytesIO
from typing import Any

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle


def _fmt_monto(v: Any) -> str:
    try:
        n = Decimal(str(v or 0))
        return f"{n:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    except Exception:
        return "0,00"


def generar_liquidacion_pdf_bytes(
    *,
    periodo_label: str,
    empleado_nombre: str,
    empleado_cargo: str | None,
    detalle_resumen: dict[str, Any],
    items_rows: list[dict[str, Any]],
) -> bytes:
    buffer = BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        rightMargin=1.5 * cm,
        leftMargin=1.5 * cm,
        topMargin=1.2 * cm,
        bottomMargin=1.2 * cm,
        title=f"Liquidacion_{empleado_nombre}_{periodo_label}",
    )
    styles = getSampleStyleSheet()
    story: list[Any] = []
    story.append(Paragraph("<b>Evalua ERP - Liquidacion de remuneraciones</b>", styles["Title"]))
    story.append(Paragraph(f"<b>Periodo:</b> {periodo_label}", styles["Heading3"]))
    story.append(Paragraph(f"<b>Trabajador:</b> {empleado_nombre}", styles["Heading3"]))
    story.append(Paragraph(f"<b>Cargo:</b> {(empleado_cargo or '-').strip() or '-'}", styles["Normal"]))
    story.append(Spacer(1, 0.3 * cm))

    resumen_tbl = Table(
        [
            ["Haberes imponibles", _fmt_monto(detalle_resumen.get("hab_imp"))],
            ["Haberes no imponibles", _fmt_monto(detalle_resumen.get("hab_no"))],
            ["Descuentos legales", _fmt_monto(detalle_resumen.get("des_leg"))],
            ["Otros descuentos", _fmt_monto(detalle_resumen.get("des_otr"))],
            ["Liquido a pagar", _fmt_monto(detalle_resumen.get("liquido"))],
        ],
        colWidths=[6.0 * cm, 5.0 * cm],
    )
    resumen_tbl.setStyle(
        TableStyle(
            [
                ("FONTNAME", (0, 0), (-1, -1), "Helvetica"),
                ("FONTSIZE", (0, 0), (-1, -1), 9),
                ("BACKGROUND", (0, 0), (0, -1), colors.HexColor("#f2f6fa")),
                ("GRID", (0, 0), (-1, -1), 0.25, colors.grey),
                ("ALIGN", (1, 0), (1, -1), "RIGHT"),
            ]
        )
    )
    story.append(resumen_tbl)
    story.append(Spacer(1, 0.45 * cm))

    rows = [["Concepto", "Origen", "Cantidad", "Valor unitario", "Monto total"]]
    for item in items_rows:
        rows.append(
            [
                str(item.get("concepto") or "-"),
                str(item.get("origen") or "-"),
                str(item.get("cantidad") or "1"),
                _fmt_monto(item.get("valor_unitario")),
                _fmt_monto(item.get("monto_total")),
            ]
        )
    tbl = Table(rows, colWidths=[5.2 * cm, 2.8 * cm, 2.2 * cm, 3.0 * cm, 3.0 * cm], repeatRows=1)
    tbl.setStyle(
        TableStyle(
            [
                ("FONTNAME", (0, 0), (-1, -1), "Helvetica"),
                ("FONTSIZE", (0, 0), (-1, -1), 8),
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1f3b5b")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.whitesmoke),
                ("GRID", (0, 0), (-1, -1), 0.2, colors.grey),
                ("ALIGN", (2, 1), (-1, -1), "RIGHT"),
            ]
        )
    )
    story.append(tbl)
    story.append(Spacer(1, 0.3 * cm))
    story.append(Paragraph("<i>Documento generado automaticamente por el sistema.</i>", styles["Normal"]))
    doc.build(story)
    data = buffer.getvalue()
    buffer.close()
    return data
