# services/leasing_operativo/contrato_pdf.py
# -*- coding: utf-8 -*-
"""Contrato de arrendamiento operativo en PDF."""
from __future__ import annotations

from io import BytesIO
from typing import Any

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle


def _fmt_num(x: Any) -> str:
    try:
        v = float(x or 0)
        return f"{v:,.0f}".replace(",", ".")
    except (TypeError, ValueError):
        return "0"


def generar_contrato_pdf_bytes(
    *,
    contrato_codigo: str,
    sim_codigo: str,
    cliente_nombre: str | None,
    tipo_nombre: str,
    plazo_meses: int,
    renta_mensual: Any,
    moneda: str,
    indexacion_tipo: str,
    indexacion_pct: Any,
    fecha_inicio: str,
    cuotas: list[dict[str, Any]],
) -> bytes:
    buf = BytesIO()
    doc = SimpleDocTemplate(
        buf,
        pagesize=A4,
        rightMargin=1.5 * cm,
        leftMargin=1.5 * cm,
        topMargin=1.2 * cm,
        bottomMargin=1.2 * cm,
        title=f"Contrato {contrato_codigo}",
    )
    styles = getSampleStyleSheet()
    story: list[Any] = []
    story.append(Paragraph("<b>EvaluaERP — Contrato de arrendamiento operativo</b>", styles["Title"]))
    story.append(Paragraph(f"<b>{contrato_codigo}</b>", styles["Heading2"]))
    story.append(Spacer(1, 0.3 * cm))

    meta = [
        ["Simulación", sim_codigo or "—"],
        ["Cliente arrendatario", cliente_nombre or "—"],
        ["Tipo activo", tipo_nombre or "—"],
        ["Plazo", f"{plazo_meses} meses"],
        ["Renta base mensual", f"{_fmt_num(renta_mensual)} {moneda}"],
        ["Indexación", f"{indexacion_tipo} ({indexacion_pct}%)" if indexacion_tipo != "NINGUNA" else "Sin reajuste"],
        ["Fecha inicio", fecha_inicio or "—"],
    ]
    t0 = Table(meta, colWidths=[4.5 * cm, 12 * cm])
    t0.setStyle(
        TableStyle(
            [
                ("FONTNAME", (0, 0), (-1, -1), "Helvetica"),
                ("FONTSIZE", (0, 0), (-1, -1), 9),
                ("BACKGROUND", (0, 0), (0, -1), colors.HexColor("#f0f4f8")),
                ("GRID", (0, 0), (-1, -1), 0.25, colors.grey),
            ]
        )
    )
    story.append(t0)
    story.append(Spacer(1, 0.5 * cm))
    story.append(Paragraph("<b>Plan de cuotas (cronograma de rentas)</b>", styles["Heading3"]))
    story.append(Spacer(1, 0.2 * cm))

    rows = [["#", "Vencimiento", "Renta neta", "Estado"]]
    for q in cuotas[:48]:
        rows.append(
            [
                str(q.get("nro") or ""),
                str(q.get("fecha_vencimiento") or ""),
                _fmt_num(q.get("monto_renta")),
                str(q.get("estado") or "PENDIENTE"),
            ]
        )
    if len(cuotas) > 48:
        rows.append(["…", f"+ {len(cuotas) - 48} cuotas", "", ""])

    t1 = Table(rows, colWidths=[1.2 * cm, 3.5 * cm, 4 * cm, 3 * cm])
    t1.setStyle(
        TableStyle(
            [
                ("FONTNAME", (0, 0), (-1, -1), "Helvetica"),
                ("FONTSIZE", (0, 0), (-1, -1), 8),
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#0B1F3B")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("GRID", (0, 0), (-1, -1), 0.25, colors.grey),
                ("ALIGN", (0, 0), (-1, -1), "CENTER"),
            ]
        )
    )
    story.append(t1)
    story.append(Spacer(1, 0.4 * cm))
    story.append(
        Paragraph(
            "<i>Documento generado por Evalua ERP. Las cláusulas contractuales definitivas "
            "deben ser revisadas por el área legal antes de firma.</i>",
            styles["Normal"],
        )
    )
    doc.build(story)
    return buf.getvalue()
