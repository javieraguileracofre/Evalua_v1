# services/leasing_financiero_cotizacion_pdf.py
# -*- coding: utf-8 -*-
"""PDF cotizador formal leasing financiero."""
from __future__ import annotations

from io import BytesIO
from typing import Any

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle


def _fmt(x: Any) -> str:
    try:
        v = float(x or 0)
        return f"{v:,.0f}".replace(",", ".")
    except (TypeError, ValueError):
        return "0"


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
        rightMargin=1.4 * cm,
        leftMargin=1.4 * cm,
        topMargin=1.2 * cm,
        bottomMargin=1.2 * cm,
        title=f"Cotización leasing financiero #{getattr(cotizacion, 'id', '')}",
    )
    styles = getSampleStyleSheet()
    story: list[Any] = []
    cli = getattr(cotizacion, "cliente", None)
    cli_nombre = getattr(cli, "razon_social", None) or "—"
    cli_rut = getattr(cli, "rut", None) or "—"

    story.append(Paragraph("<b>EvaluaERP — Cotización Leasing Financiero</b>", styles["Title"]))
    story.append(Paragraph(f"<b>Cotización #{getattr(cotizacion, 'id', '—')}</b>", styles["Heading2"]))
    story.append(Spacer(1, 0.25 * cm))

    meta = [
        ["Cliente", str(cli_nombre)],
        ["RUT", str(cli_rut)],
        ["Estado", str(getattr(cotizacion, "estado", "") or "—")],
        ["Moneda", str(getattr(cotizacion, "moneda", "CLP") or "CLP")],
        ["Bien", str(getattr(cotizacion, "bien_descripcion", None) or "—")],
        ["Ejecutivo", str(getattr(cotizacion, "ejecutivo", None) or "—")],
        ["Fecha cotización", str(getattr(cotizacion, "fecha_cotizacion", None) or "—")],
    ]
    t0 = Table(meta, colWidths=[4.2 * cm, 12.2 * cm])
    t0.setStyle(
        TableStyle(
            [
                ("FONTNAME", (0, 0), (-1, -1), "Helvetica"),
                ("FONTSIZE", (0, 0), (-1, -1), 9),
                ("BACKGROUND", (0, 0), (0, -1), colors.HexColor("#f0f4f8")),
                ("GRID", (0, 0), (-1, -1), 0.25, colors.grey),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ]
        )
    )
    story.append(t0)
    story.append(Spacer(1, 0.45 * cm))
    story.append(Paragraph("<b>Resumen de la operación</b>", styles["Heading3"]))

    tasa = getattr(cotizacion, "tasa", None)
    tasa_pct = f"{float(tasa) * 100:.2f}%" if tasa is not None else "—"
    kpi = [
        ["Valor neto", _fmt(getattr(cotizacion, "valor_neto", None) or getattr(resumen, "valor_neto", None))],
        ["Pago inicial / pie", _fmt(getattr(resumen, "pago_inicial", 0))],
        ["Monto financiado", _fmt(getattr(resumen, "monto_financiado", 0))],
        ["Plazo (meses)", str(getattr(cotizacion, "plazo", None) or "—")],
        ["Periodicidad", str(getattr(cotizacion, "periodicidad", "MENSUAL") or "MENSUAL")],
        ["Tasa nominal anual", tasa_pct],
        ["Cuota estimada", _fmt(getattr(resumen, "renta_mensual", 0))],
        ["Total intereses", _fmt(getattr(resumen, "total_intereses", 0))],
        ["Costo total estimado", _fmt(getattr(resumen, "total_desembolso", 0))],
        ["Seguro financiado", _fmt(getattr(resumen, "seguro_financiado", 0))],
        ["GPS financiado", _fmt(getattr(resumen, "gps_financiado", 0))],
        ["Gastos admin. financiados", _fmt(getattr(resumen, "gastos_admin_financiados", 0))],
    ]
    t1 = Table(kpi, colWidths=[6 * cm, 10.4 * cm])
    t1.setStyle(
        TableStyle(
            [
                ("FONTNAME", (0, 0), (-1, -1), "Helvetica"),
                ("FONTSIZE", (0, 0), (-1, -1), 9),
                ("GRID", (0, 0), (-1, -1), 0.25, colors.grey),
                ("BACKGROUND", (0, 0), (0, -1), colors.HexColor("#fafafa")),
            ]
        )
    )
    story.append(t1)

    if condiciones:
        story.append(Spacer(1, 0.4 * cm))
        story.append(Paragraph("<b>Condiciones del crédito / aceptación</b>", styles["Heading3"]))
        story.append(Paragraph(str(condiciones).replace("\n", "<br/>"), styles["Normal"]))

    if tabla:
        story.append(Spacer(1, 0.4 * cm))
        story.append(Paragraph("<b>Tabla de amortización (extracto)</b>", styles["Heading3"]))
        rows = [["#", "Cuota", "Interés", "Amortización", "Saldo"]]
        for c in tabla[:24]:
            rows.append(
                [
                    str(getattr(c, "numero", getattr(c, "numero_cuota", ""))),
                    _fmt(getattr(c, "cuota", 0)),
                    _fmt(getattr(c, "interes", 0)),
                    _fmt(getattr(c, "amortizacion", 0)),
                    _fmt(getattr(c, "saldo_final", getattr(c, "saldo", 0))),
                ]
            )
        if len(tabla) > 24:
            rows.append(["…", f"+{len(tabla) - 24} cuotas", "", "", ""])
        t2 = Table(rows, colWidths=[1.5 * cm, 3.5 * cm, 3.5 * cm, 3.8 * cm, 3.8 * cm])
        t2.setStyle(
            TableStyle(
                [
                    ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                    ("FONTSIZE", (0, 0), (-1, -1), 8),
                    ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#0B1F3B")),
                    ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                    ("GRID", (0, 0), (-1, -1), 0.2, colors.grey),
                    ("ALIGN", (1, 1), (-1, -1), "RIGHT"),
                ]
            )
        )
        story.append(t2)

    story.append(Spacer(1, 0.5 * cm))
    story.append(
        Paragraph(
            "<font size='8'>Documento generado por EvaluaERP. Las condiciones finales "
            "quedan sujetas a aprobación de crédito y aceptación del cliente.</font>",
            styles["Normal"],
        )
    )
    doc.build(story)
    return buf.getvalue()
