"""One-page model factsheet as a PDF (reportlab, free).

The factsheet is the model's identity card for the Management Risk Committee,
the CRO, auditors and QCB: what it does, who is accountable, how risky it is,
its validation standing, open findings, monitoring position and limitations —
all generated from the live record, never retyped.
"""

from __future__ import annotations

from datetime import date
from io import BytesIO
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle


NAVY = colors.HexColor("#14284b")
GOLD = colors.HexColor("#b8933d")
GREY = colors.HexColor("#5f6b7a")
LIGHT = colors.HexColor("#f4f6fa")
RAG = {"Green": colors.HexColor("#2e7d32"), "Amber": colors.HexColor("#ed6c02"),
       "Red": colors.HexColor("#c62828")}
SEV = {"High": colors.HexColor("#c62828"), "Medium": colors.HexColor("#ed6c02"),
       "Low": colors.HexColor("#607d8b")}


def _d(iso: str | None, empty: str = "—") -> str:
    if not iso:
        return empty
    try:
        return date.fromisoformat(str(iso)[:10]).strftime("%d %b %Y")
    except ValueError:
        return str(iso)


def _styles():
    ss = getSampleStyleSheet()
    base = ParagraphStyle("b", parent=ss["Normal"], fontName="Helvetica", fontSize=8, leading=10.2)
    return {
        "title": ParagraphStyle("t", parent=base, fontName="Helvetica-Bold", fontSize=14,
                                leading=17, textColor=NAVY),
        "sub": ParagraphStyle("s", parent=base, textColor=GREY, fontSize=8.5),
        "h": ParagraphStyle("h", parent=base, fontName="Helvetica-Bold", fontSize=9,
                            textColor=NAVY, spaceBefore=5, spaceAfter=2),
        "b": base,
        "small": ParagraphStyle("sm", parent=base, fontSize=7, leading=8.5, textColor=GREY),
        "cell": ParagraphStyle("c", parent=base, fontSize=7.6, leading=9.2),
        "label": ParagraphStyle("l", parent=base, fontSize=7.2, leading=9, textColor=GREY),
    }


def _p(text, style):
    return Paragraph(escape(str(text if text not in (None, "") else "—")), style)


def _grid(rows, widths, st, header=False):
    t = Table(rows, colWidths=widths)
    style = [
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("TOPPADDING", (0, 0), (-1, -1), 2.2),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 2.2),
        ("LEFTPADDING", (0, 0), (-1, -1), 3),
        ("RIGHTPADDING", (0, 0), (-1, -1), 3),
        ("LINEBELOW", (0, 0), (-1, -1), 0.25, colors.HexColor("#dde2ea")),
    ]
    if header:
        style += [("BACKGROUND", (0, 0), (-1, 0), LIGHT)]
    t.setStyle(TableStyle(style))
    return t


def build_factsheet(model: dict, requests: list[dict], monitoring: list[dict],
                    documentation: dict, validation_status: str) -> bytes:
    """Return the factsheet PDF as bytes."""
    st = _styles()
    buf = BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, leftMargin=14 * mm, rightMargin=14 * mm,
                            topMargin=12 * mm, bottomMargin=12 * mm,
                            title=f"{model['model_id']} factsheet", author="QDB Model Risk Management")
    W = A4[0] - 28 * mm
    story = []

    # ------------------------------------------------ header
    story.append(_p(f"{model['model_id']} — {model['name']}", st["title"]))
    story.append(_p(
        f"Model factsheet · {model['risk_type']} · {model['business_line']} · "
        f"version {model['version']} · generated {_d(date.today().isoformat())}", st["sub"]))
    story.append(Spacer(1, 3))
    bar = Table([[""]], colWidths=[W], rowHeights=[1.6])
    bar.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, -1), GOLD)]))
    story.append(bar)
    story.append(Spacer(1, 4))

    # ------------------------------------------------ headline tiles
    tier_note = "confirmed" if model.get("tier_confirmed") else "awaiting sign-off"
    if model.get("tier_override"):
        tier_note = f"override (rule-based {model.get('computed_tier')})"
    tiles = [
        ("Tier", f"Tier {model['tier']}", tier_note),
        ("Status", model["status"], f"approved {_d(model.get('approval_date'), 'not approved')}"),
        ("Validation rating", model.get("last_rating") or "Not validated",
         f"last {_d(model.get('last_validation'), 'never')}"),
        ("Next validation", _d(model.get("next_validation_due")), validation_status),
        ("Exposure covered", f"QAR {model['exposure_covered_qar_mn']:,} mn", model["approval_body"]),
    ]
    tile_cells = [[Paragraph(f"<font color='#5f6b7a' size='7'>{escape(a)}</font><br/>"
                             f"<b>{escape(str(b))}</b><br/>"
                             f"<font color='#5f6b7a' size='6.8'>{escape(str(c))}</font>", st["cell"])
                   for a, b, c in tiles]]
    tt = Table(tile_cells, colWidths=[W / 5] * 5)
    tt.setStyle(TableStyle([
        ("BOX", (0, 0), (-1, -1), 0.4, colors.HexColor("#dde2ea")),
        ("INNERGRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#dde2ea")),
        ("LINEBEFORE", (0, 0), (0, 0), 2, GOLD),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("TOPPADDING", (0, 0), (-1, -1), 4), ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]))
    story.append(tt)

    # ------------------------------------------------ purpose and uses
    story.append(_p("Purpose", st["h"]))
    story.append(_p(model["description"], st["b"]))
    uses = model.get("uses") or []
    if uses:
        story.append(_p("Uses", st["h"]))
        rows = [[_p("Use", st["label"]), _p("Business area", st["label"]),
                 _p("Decision supported", st["label"]), _p("Status", st["label"])]]
        for u in uses:
            rows.append([_p(u.get("use"), st["cell"]), _p(u.get("business_area"), st["cell"]),
                         _p(u.get("decision"), st["cell"]), _p(u.get("status"), st["cell"])])
        story.append(_grid(rows, [W * 0.25, W * 0.22, W * 0.41, W * 0.12], st, header=True))

    # ------------------------------------------------ identity and accountability (two columns)
    left = [
        ("Owner", model["owner"]), ("Developer", model["developer"]),
        ("Validator", model["validator"]), ("Sponsor", model["sponsor"]),
        ("Approval body", model["approval_body"]),
    ]
    right = [
        ("Methodology", model["methodology"]),
        ("Source", model["source"] + (f" — {model['vendor']}" if model.get("vendor") else "")),
        ("Platform / frequency", f"{model['implementation_platform']} · {model['usage_frequency']}"),
        ("AI system (QCB)", ("Yes — high-risk" if model.get("qcb_ai_high_risk") else "Yes")
         if model.get("ai_system") else "No"),
        ("Tier rationale", model.get("tier_rationale")),
    ]
    kv = []
    for (a, b), (c, d) in zip(left, right):
        kv.append([_p(a, st["label"]), _p(b, st["cell"]), _p(c, st["label"]), _p(d, st["cell"])])
    story.append(_p("Accountability and design", st["h"]))
    story.append(_grid(kv, [W * 0.13, W * 0.33, W * 0.16, W * 0.38], st))

    # ------------------------------------------------ findings and monitoring side by side
    open_f = [r for r in requests if r["type"] == "FND" and r["status"] != "Closed"]
    today = date.today().isoformat()
    f_rows = [[_p("Finding", st["label"]), _p("Severity", st["label"]), _p("Due", st["label"])]]
    for r in sorted(open_f, key=lambda r: ({"High": 0, "Medium": 1, "Low": 2}.get(r.get("severity"), 3),
                                           r.get("due_date") or "")):
        due = _d(r.get("due_date"))
        if r.get("due_date") and r["due_date"] < today:
            due += " (overdue)"
        f_rows.append([_p(f"{r['request_id']} {r['title']}", st["cell"]),
                       Paragraph(f"<font color='{SEV.get(r.get('severity'), GREY).hexval()}'><b>"
                                 f"{escape(r.get('severity') or '—')}</b></font>", st["cell"]),
                       _p(due, st["cell"])])
    if len(f_rows) == 1:
        f_rows.append([_p("No open findings", st["cell"]), "", ""])

    latest = {}
    for row in monitoring:
        if row["metric"] not in latest or row["period"] > latest[row["metric"]]["period"]:
            latest[row["metric"]] = row
    m_rows = [[_p("Metric", st["label"]), _p("Latest", st["label"]), _p("RAG", st["label"])]]
    for row in latest.values():
        m_rows.append([_p(f"{row['metric']} ({row['period']})", st["cell"]),
                       _p(f"{row['value']:g}", st["cell"]),
                       Paragraph(f"<font color='{RAG.get(row['rag'], GREY).hexval()}'><b>"
                                 f"{escape(row['rag'])}</b></font>", st["cell"])])
    if len(m_rows) == 1:
        m_rows.append([_p("No quantitative monitoring", st["cell"]), "", ""])

    half = (W - 6 * mm) / 2
    pair = Table([[
        [_p(f"Open findings ({len(open_f)})", st["h"]),
         _grid(f_rows, [half * 0.62, half * 0.16, half * 0.22], st, header=True)],
        [_p("Monitoring — latest position", st["h"]),
         _grid(m_rows, [half * 0.62, half * 0.18, half * 0.20], st, header=True)],
    ]], colWidths=[half + 3 * mm, half + 3 * mm])
    pair.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"),
                              ("LEFTPADDING", (0, 0), (-1, -1), 0),
                              ("RIGHTPADDING", (0, 0), (0, 0), 6 * mm)]))
    story.append(pair)

    # ------------------------------------------------ limitations, dependencies, documentation
    story.append(_p("Key limitations", st["h"]))
    lims = model.get("known_limitations") or ["None recorded"]
    story.append(Paragraph("<br/>".join("• " + escape(x) for x in lims), st["b"]))

    deps = model["dependencies"]
    story.append(_p("Dependencies", st["h"]))
    story.append(_p(
        f"Upstream: {', '.join(deps['upstream']) or 'none'}   ·   "
        f"Downstream: {', '.join(deps['downstream']) or 'none'}", st["b"]))

    done = sum(documentation.values())
    missing = [k for k, v in documentation.items() if not v]
    story.append(_p("Documentation", st["h"]))
    story.append(_p(
        f"{done} of {len(documentation)} required artefacts in place"
        + (f" — missing: {', '.join(missing)}" if missing else ""), st["b"]))

    story.append(Spacer(1, 6))
    story.append(_p(
        "Generated from the QDB model governance platform. Validation dates and rating are "
        "derived from closed validation requests; tier from confirmed tier scores. "
        + ("Placeholder record — details to be confirmed. " if model.get("placeholder") else "")
        + "PoC: attributes other than model names are mock data.", st["small"]))

    doc.build(story)
    return buf.getvalue()


def factsheet_filename(model: dict) -> str:
    return f"{model['model_id']}_factsheet_{date.today().isoformat()}.pdf"

