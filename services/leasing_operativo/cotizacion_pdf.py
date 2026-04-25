# services/leasing_operativo/cotizacion_pdf.py
# -*- coding: utf-8 -*-
"""Cotización leasing operativo en PDF (ReportLab)."""
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


def generar_cotizacion_pdf_bytes(
    *,
    codigo: str,
    nombre: str,
    tipo_nombre: str,
    cliente_nombre: str | None,
    sim_meta: dict[str, Any],
    result: dict[str, Any],
) -> bytes:
    buf = BytesIO()
    doc = SimpleDocTemplate(
        buf,
        pagesize=A4,
        rightMargin=1.5 * cm,
        leftMargin=1.5 * cm,
        topMargin=1.2 * cm,
        bottomMargin=1.2 * cm,
        title=f"Cotización {codigo}",
    )
    styles = getSampleStyleSheet()
    story: list[Any] = []
    story.append(Paragraph("<b>EvaluaERP — Leasing operativo</b>", styles["Title"]))
    story.append(Paragraph(f"<b>Cotización {codigo}</b>", styles["Heading2"]))
    story.append(Spacer(1, 0.3 * cm))
    meta = [
        ["Operación", nombre or "—"],
        ["Tipo activo", tipo_nombre or "—"],
        ["Cliente", cliente_nombre or "—"],
        ["Escenario", str(sim_meta.get("escenario") or "—")],
        ["Plazo (meses)", str(sim_meta.get("plazo_meses") or "—")],
        ["Método pricing", str(sim_meta.get("metodo_pricing") or "—")],
    ]
    t0 = Table(meta, colWidths=[4.2 * cm, 12 * cm])
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
    story.append(Paragraph("<b>Indicadores económicos</b>", styles["Heading3"]))
    vr = result.get("valor_residual") or {}
    kpi = [
        ["CAPEX total", _fmt_num(result.get("capex_total"))],
        ["Residual ajustado", _fmt_num(vr.get("valor_residual_ajustado"))],
        ["LTV %", f"{float(result.get('ltv_pct') or 0):.2f}"],
        ["Renta mínima", _fmt_num(result.get("renta_minima"))],
        ["Renta sugerida", _fmt_num(result.get("renta_sugerida"))],
        ["VAN (desc. WACC)", _fmt_num(result.get("van"))],
        ["TIR anual %", f"{float(result.get('tir_anual_pct') or 0):.2f}" if result.get("tir_anual_pct") is not None else "—"],
        ["Decisión motor", str(sim_meta.get("decision_codigo") or result.get("decision", {}).get("decision_codigo") or "—")],
    ]
    t1 = Table(kpi, colWidths=[5 * cm, 11 * cm])
    t1.setStyle(
        TableStyle(
            [
                ("FONTNAME", (0, 0), (-1, -1), "Helvetica"),
                ("FONTSIZE", (0, 0), (-1, -1), 9),
                ("BACKGROUND", (0, 0), (0, -1), colors.HexColor("#eef6ff")),
                ("GRID", (0, 0), (-1, -1), 0.25, colors.grey),
            ]
        )
    )
    story.append(t1)
    story.append(Spacer(1, 0.5 * cm))
    story.append(Paragraph("<b>Flujo mensual (primeros 18 meses)</b>", styles["Heading3"]))
    rows: list[list[str]] = [["Mes", "Venta", "C. fondo", "Depr.", "Op.", "Riesgo", "Res. op."]]
    for row in (result.get("flujo_mensual") or [])[:18]:
        rows.append(
            [
                str(row.get("mes")),
                _fmt_num(row.get("venta")),
                _fmt_num(row.get("costo_fondo")),
                _fmt_num(row.get("depreciacion")),
                _fmt_num(row.get("costos_operativos")),
                _fmt_num(row.get("prima_riesgo")),
                _fmt_num(row.get("resultado_operacional")),
            ]
        )
    tw = [1.2 * cm, 2.2 * cm, 2 * cm, 2 * cm, 2 * cm, 2 * cm, 2.4 * cm]
    t2 = Table(rows, colWidths=tw, repeatRows=1)
    t2.setStyle(
        TableStyle(
            [
                ("FONTNAME", (0, 0), (-1, -1), "Helvetica"),
                ("FONTSIZE", (0, 0), (-1, -1), 7),
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1a365d")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.whitesmoke),
                ("GRID", (0, 0), (-1, -1), 0.2, colors.grey),
            ]
        )
    )
    story.append(t2)
    story.append(Spacer(1, 0.4 * cm))
    story.append(Paragraph("<i>Documento generado por el sistema. Cifras referenciales según simulación almacenada.</i>", styles["Normal"]))
    doc.build(story)
    data = buf.getvalue()
    buf.close()
    return data
