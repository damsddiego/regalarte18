# -*- coding: utf-8 -*-
"""Build the user manual as a searchable PDF and standalone HTML.

Usage: /opt/odoo18/odoo18-venv/bin/python docs/build_manual.py
No Odoo database access is needed.
"""
import base64
import html
import re
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (
    PageBreak, Paragraph, SimpleDocTemplate, Spacer,
    Table, TableStyle,
)
from reportlab.lib.utils import ImageReader


ROOT = Path(__file__).resolve().parent
SOURCE = ROOT / "manual_usuario.md"
PDF = ROOT / "Manual_usuario_conteos_ciclicos_Regalarte.pdf"
HTML = ROOT / "Manual_usuario_conteos_ciclicos_Regalarte.html"
ASSETS = ROOT / "assets"
LOGO = ASSETS / "logo.png"  # logo horizontal de regalarte.cr, blanco sobre transparente
# Colores de marca (kit Elementor de https://regalarte.cr/)
DARK_GREEN = colors.HexColor("#245501")
GREEN = colors.HexColor("#538D22")
RED = colors.HexColor("#E52529")
CREAM = colors.HexColor("#F5ECD0")
INK = colors.HexColor("#292929")
MUTED = colors.HexColor("#7A7A7A")
for font, filename in [("Manual", "Roboto-Regular.ttf"), ("ManualBold", "Roboto-Bold.ttf"),
                       ("Slab", "RobotoSlab_400.ttf"), ("SlabBold", "RobotoSlab_700.ttf")]:
    pdfmetrics.registerFont(TTFont(font, str(ASSETS / filename)))
# Roboto no trae la flecha de las rutas de menú; se toma de DejaVu
pdfmetrics.registerFont(TTFont("Arrow", "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"))
pdfmetrics.registerFontFamily("Manual", normal="Manual", bold="ManualBold", italic="Manual", boldItalic="ManualBold")

styles = {
    "body": ParagraphStyle("Body", fontName="Manual", fontSize=9.6, leading=13.8,
                           textColor=INK, spaceAfter=8, linkUnderline=0),
    "h1": ParagraphStyle("Title", fontName="SlabBold", fontSize=21, leading=26,
                         textColor=DARK_GREEN, spaceAfter=17, keepWithNext=True),
    "h2": ParagraphStyle("Subtitle", fontName="Slab", fontSize=14.5, leading=19,
                         textColor=GREEN, spaceAfter=14, keepWithNext=True),
    "h3": ParagraphStyle("Subhead", fontName="SlabBold", fontSize=11, leading=15,
                         textColor=GREEN, spaceBefore=8, spaceAfter=8, keepWithNext=True),
    "step": ParagraphStyle("Step", fontName="Manual", fontSize=9.6, leading=13.8,
                           textColor=INK, leftIndent=13, firstLineIndent=-13, spaceAfter=7),
    "quote": ParagraphStyle("Callout", fontName="Manual", fontSize=9.7, leading=14,
                            textColor=INK, spaceAfter=10, borderPadding=10,
                            backColor=colors.HexColor("#FAF5E6"), borderColor=GREEN,
                            borderWidth=0.8),
    "warn": ParagraphStyle("Warning", fontName="Manual", fontSize=9.7, leading=14,
                           textColor=INK, spaceAfter=10, borderPadding=10,
                           backColor=colors.HexColor("#FCEBEB"), borderColor=RED,
                           borderWidth=0.8),
    "cell": ParagraphStyle("Cell", fontName="Manual", fontSize=8.6, leading=11.8,
                           textColor=INK, alignment=TA_LEFT),
    "th": ParagraphStyle("TH", fontName="ManualBold", fontSize=8.6, leading=11.8,
                         textColor=colors.white),
}


def inline(value, pdf=False):
    value = html.escape(value, quote=False)
    if pdf:
        value = value.replace("→", '<font name="Arrow">→</font>')
    value = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", value)
    value = re.sub(r"https://[^\s<]+(?<![.,])", lambda match: '<a href="' + match[0] + '">' + match[0] + '</a>', value)
    return value


def pdf_inline(value):
    return inline(value, pdf=True)


class ManualDoc(SimpleDocTemplate):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.sections = []

    def afterFlowable(self, flowable):
        if getattr(flowable, "manual_heading", None):
            title, anchor, expected = flowable.manual_heading
            self.canv.bookmarkPage(anchor)
            self.canv.addOutlineEntry(title, anchor, level=0)
            self.sections.append((title, self.page, expected))


COVER_BAND = 118


def footer(canvas, doc):
    canvas.saveState()
    width, height = A4
    logo = ImageReader(str(LOGO))
    logo_w, logo_h = logo.getSize()
    band = COVER_BAND if doc.page == 1 else 38
    canvas.setFillColor(DARK_GREEN)
    canvas.rect(0, height - band, width, band, stroke=0, fill=1)
    canvas.setFillColor(GREEN)
    canvas.rect(0, height - band - 3, width, 3, stroke=0, fill=1)
    if doc.page == 1:
        draw_h = 58
        canvas.drawImage(logo, 42, height - band + (band - draw_h) / 2, draw_h * logo_w / logo_h, draw_h, mask="auto")
        canvas.setFillColor(CREAM)
        canvas.setFont("ManualBold", 9)
        canvas.drawRightString(width - 42, height - 52, "MANUAL DE USUARIO")
        canvas.setFont("Manual", 8.5)
        canvas.drawRightString(width - 42, height - 66, "Inventario · Conteos cíclicos")
    else:
        draw_h = 30
        canvas.drawImage(logo, 42, height - band + (band - draw_h) / 2, draw_h * logo_w / logo_h, draw_h, mask="auto")
        canvas.setFillColor(CREAM)
        canvas.setFont("ManualBold", 8)
        canvas.drawRightString(width - 42, height - 22, "MANUAL DE CONTEOS CÍCLICOS")
    canvas.setStrokeColor(CREAM)
    canvas.setLineWidth(1)
    canvas.line(42, 36, width - 42, 36)
    canvas.setFont("Manual", 7.5)
    canvas.setFillColor(MUTED)
    canvas.drawString(42, 24, "Versión 1.0 · 16/09/2026 · Uso operativo")
    canvas.setFont("ManualBold", 8)
    canvas.setFillColor(DARK_GREEN)
    canvas.drawRightString(width - 42, 24, f"{doc.page} / 13")
    canvas.restoreState()


def build():
    source = SOURCE.read_text(encoding="utf-8")
    pages = source.split("<!-- pagebreak -->")
    story = [Spacer(1, COVER_BAND - 53)]
    sections_html = []
    contents = []
    for page_index, text in enumerate(pages):
        if page_index:
            story.append(PageBreak())
        anchor = "inicio" if not page_index else f"seccion-{page_index}"
        page_html = [f'<section id="{anchor}" class="page">']
        lines = text.strip().splitlines()
        i = 0
        while i < len(lines):
            line = lines[i].strip()
            if not line:
                i += 1
                continue
            if line.startswith("|"):
                table_lines = []
                while i < len(lines) and lines[i].strip().startswith("|"):
                    cells = [v.strip() for v in lines[i].strip().strip("|").split("|")]
                    if not all(re.fullmatch(r"[:\- ]+", cell) for cell in cells):
                        table_lines.append(cells)
                    i += 1
                count = len(table_lines[0])
                available = A4[0] - 84
                if page_index == 0:
                    widths = [available * .34, available * .55, available * .11]
                elif count == 4:
                    widths = [available / 4] * 4
                elif count == 3:
                    widths = [available * .30, available * .35, available * .35]
                elif page_index == 11:
                    widths = [available * .39, available * .61]
                else:
                    widths = [available * .38, available * .62]
                cells_pdf, rows_html = [], []
                for row_index, row in enumerate(table_lines):
                    formatted = [inline(v, pdf=True) for v in row]
                    formatted_html = [inline(v) for v in row]
                    if page_index == 0 and row_index:
                        target = f"seccion-{row_index}"
                        formatted[0] = f'<a href="#{target}">{formatted[0]}</a>'
                        formatted_html[0] = f'<a href="#{target}">{formatted_html[0]}</a>'
                    cells_pdf.append([Paragraph(cell, styles["th" if row_index == 0 else "cell"]) for cell in formatted])
                    tag = "th" if row_index == 0 else "td"
                    rows_html.append("<tr>" + "".join(f"<{tag}>{cell}</{tag}>" for cell in formatted_html) + "</tr>")
                table = Table(cells_pdf, colWidths=widths, repeatRows=1, hAlign="LEFT")
                table.setStyle(TableStyle([
                    ("BACKGROUND", (0, 0), (-1, 0), DARK_GREEN),
                    ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.HexColor("#FAF5E6"), colors.white]),
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    ("LEFTPADDING", (0, 0), (-1, -1), 8),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 8),
                    ("TOPPADDING", (0, 0), (-1, -1), 6),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
                    ("LINEBELOW", (0, 0), (-1, 0), 2, GREEN),
                    ("LINEBELOW", (0, -1), (-1, -1), .8, CREAM),
                ]))
                story.extend([table, Spacer(1, 10)])
                page_html.append('<div class="table-wrap"><table>' + "".join(rows_html) + "</table></div>")
                continue
            if line.startswith("# "):
                title = line[2:]
                paragraph = Paragraph(pdf_inline(title), styles["h1"])
                paragraph.manual_heading = (title, anchor, page_index + 1)
                story.append(paragraph)
                page_html.append("<h1>" + inline(title) + "</h1>")
                contents.append((title, anchor))
            elif line.startswith("## "):
                story.append(Paragraph(pdf_inline(line[3:]), styles["h2"]))
                page_html.append("<h2>" + inline(line[3:]) + "</h2>")
            elif line.startswith("### "):
                story.append(Paragraph(pdf_inline(line[4:]), styles["h3"]))
                page_html.append("<h3>" + inline(line[4:]) + "</h3>")
            elif line.startswith("> "):
                story.append(Spacer(1, 6))
                warning = line[2:].startswith("Ojo")
                story.append(Paragraph(pdf_inline(line[2:]), styles["warn" if warning else "quote"]))
                page_html.append('<aside class="warn">' if warning else "<aside>")
                page_html[-1] += inline(line[2:]) + "</aside>"
            elif line.startswith("- ") or re.match(r"\d+\. ", line):
                content = "• " + line[2:] if line.startswith("- ") else line
                story.append(Paragraph(pdf_inline(content), styles["step"]))
                page_html.append('<p class="step">' + inline(content) + "</p>")
            else:
                story.append(Paragraph(pdf_inline(line), styles["body"]))
                page_html.append("<p>" + inline(line) + "</p>")
            i += 1
        page_html.append('</section>')
        sections_html.append("\n".join(page_html))
    document = ManualDoc(str(PDF), pagesize=A4, leftMargin=42, rightMargin=42,
                         topMargin=58, bottomMargin=42,
                         title="Manual de conteos cíclicos Regalarte",
                         author="Diego Mora · Regalarte", subject="Operadores, Jefatura y Gerencia")
    document.build(story, onFirstPage=footer, onLaterPages=footer)
    if document.page != 13 or any(actual != expected for _, actual, expected in document.sections):
        raise RuntimeError(f"Revise paginación e índice: {document.page} páginas; {document.sections}")
    css = """
    :root {--dark:#245501;--green:#538D22;--red:#E52529;--cream:#F5ECD0;--ink:#292929;} * {box-sizing:border-box}
    body {margin:0;background:#f7f2e2;color:var(--ink);font:16px/1.6 Roboto,system-ui,sans-serif}
    nav {position:fixed;inset:0 auto 0 0;width:260px;padding:25px 18px;background:var(--dark);color:white;overflow:auto;border-right:4px solid var(--green)}
    nav a {display:block;color:var(--cream);text-decoration:none;padding:6px 0;font-size:13px}
    nav a:hover {text-decoration:underline} nav img {display:block;width:190px;margin-bottom:22px}
    main {max-width:1120px;margin-left:260px;padding:24px}
    .page {background:white;padding:38px 45px;margin-bottom:24px;border-radius:6px;scroll-margin-top:20px}
    h1,h2,h3 {font-family:"Roboto Slab",Georgia,serif}
    h1 {font-size:29px;line-height:1.25;margin-top:0;color:var(--dark)} h2,h3 {color:var(--green);line-height:1.4}
    h2 {font-size:22px} h3 {font-size:18px;margin-top:26px} p {margin:12px 0}
    aside {background:#FAF5E6;border-left:4px solid var(--green);padding:16px;margin:20px 0}
    aside.warn {background:#FCEBEB;border-left-color:var(--red)}
    a {color:var(--green);overflow-wrap:anywhere} .table-wrap {overflow-x:auto}
    table {border-collapse:collapse;width:100%;font-size:14px;margin:18px 0} th,td {padding:10px;text-align:left;vertical-align:top}
    th {background:var(--dark);color:white;border-bottom:3px solid var(--green)} tr:nth-child(even) {background:#FAF5E6}
    .step {padding-left:18px;text-indent:-18px}
    @media(max-width:850px) {nav {position:static;width:auto} main {margin:0;padding:12px}.page {padding:24px}}
    @media print {nav {display:none}main {margin:0;padding:0}.page {break-after:page;padding:0;border-radius:0}body {background:white;font-size:10pt}}
    """
    logo_uri = "data:image/png;base64," + base64.b64encode(LOGO.read_bytes()).decode()
    navigation = "".join(f'<a href="#{anchor}">{html.escape(title)}</a>' for title, anchor in contents)
    HTML.write_text('<!doctype html><html lang="es"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">'
                    '<title>Manual de conteos cíclicos | Regalarte</title>'
                    '<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Roboto:wght@400;700&family=Roboto+Slab:wght@400;700&display=swap">'
                    '<style>' + css + '</style></head><body>'
                    '<nav aria-label="Índice"><img src="' + logo_uri + '" alt="Regalarte">' + navigation + '</nav><main>'
                    + "\n".join(sections_html) + '</main></body></html>', encoding="utf-8")
    print(f"Generated {document.page} pages: {PDF}\nHTML: {HTML}")


if __name__ == "__main__":
    build()
