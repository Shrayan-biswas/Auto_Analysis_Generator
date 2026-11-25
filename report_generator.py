import html
import re
from html.parser import HTMLParser
from io import BytesIO

from docx import Document
from pptx import Presentation
from pptx.dml.color import RGBColor as PptxColor
from pptx.enum.shapes import MSO_SHAPE
from pptx.enum.text import PP_ALIGN, MSO_ANCHOR
from pptx.util import Inches as PptxInches, Pt as PptxPt
from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import (
    Paragraph,
    SimpleDocTemplate,
    Spacer,
)

from dashboard_generator import THEMES


class _HTMLTextParser(HTMLParser):
    _BLOCK_TAGS = {
        "article", "br", "div", "footer", "h1", "h2", "h3", "h4", "header",
        "li", "p", "section", "text", "tr",
    }

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.lines = []
        self.current = []
        self.skip_depth = 0

    def handle_starttag(self, tag, attrs):
        if tag in {"script", "style"}:
            self.skip_depth += 1
        if self.skip_depth:
            return
        if tag == "svg":
            self.svg_depth = getattr(self, "svg_depth", 0) + 1
            return
        if tag == "text" and getattr(self, "svg_depth", 0):
            self.svg_text = True
        if tag in self._BLOCK_TAGS:
            self._flush()

    def handle_endtag(self, tag):
        if tag in {"script", "style"} and self.skip_depth:
            self.skip_depth -= 1
        if tag == "svg" and getattr(self, "svg_depth", 0):
            self.svg_depth -= 1
            return
        if tag == "text" and getattr(self, "svg_depth", 0):
            self.svg_text = False
        if not self.skip_depth and tag in self._BLOCK_TAGS:
            self._flush()

    def handle_data(self, data):
        if self.skip_depth:
            return
        text = " ".join(data.split())
        if text:
            self.current.append(text)

    def _flush(self):
        line = " ".join(self.current).strip()
        if line and (not self.lines or self.lines[-1] != line):
            self.lines.append(line)
        self.current.clear()

    def close(self):
        super().close()
        self._flush()


def _hex_rgb(hex_color):
    value = hex_color.lstrip("#")
    return tuple(int(value[index:index + 2], 16) for index in (0, 2, 4))


def _extract_svg_bar_charts(html_content):
    charts = []
    for svg in re.finditer(r"<svg\b([^>]*)>(.*?)</svg>", html_content, re.IGNORECASE | re.DOTALL):
        attributes, contents = svg.groups()
        title_match = re.search(r'\baria-label="([^"]*)"', attributes, re.IGNORECASE)
        if not title_match:
            continue
        texts = [
            html.unescape(re.sub(r"<[^>]*>", "", text)).strip()
            for text in re.findall(
                r"<text\b[^>]*>(.*?)</text>",
                contents,
                re.IGNORECASE | re.DOTALL,
            )
        ]
        rectangles = re.findall(
            r"<rect\b([^>]*)>",
            contents,
            re.IGNORECASE | re.DOTALL,
        )
        bars = []
        rect_index = 0
        for index in range(0, len(texts) - 1, 2):
            while rect_index < len(rectangles):
                attributes = rectangles[rect_index]
                rect_index += 1
                height = re.search(r'\bheight="([\d.]+)"', attributes)
                if height and float(height.group(1)) == 22:
                    width = re.search(r'\bwidth="([\d.]+)"', attributes)
                    color = re.search(r'\bfill="(#[0-9a-fA-F]{6})"', attributes)
                    bars.append(
                        {
                            "label": texts[index],
                            "value": texts[index + 1],
                            "width": float(width.group(1)) if width else 1.0,
                            "color": color.group(1) if color else "#b52e46",
                        }
                    )
                    break
        if bars:
            charts.append(
                {
                    "title": html.unescape(title_match.group(1)),
                    "bars": bars,
                }
            )
    return charts


def html_to_pptx(html_content, title="Insight Studio dashboard", theme_name=None):
    parser = _HTMLTextParser()
    parser.feed(html_content)
    lines = [line for line in parser.lines if line]
    if not lines:
        raise ValueError("No readable text was found in the HTML document.")

    palette = THEMES.get(theme_name or "", THEMES["Ruby & Amber"])
    charts = _extract_svg_bar_charts(html_content)
    presentation = Presentation()
    presentation.slide_width = PptxInches(13.333)
    presentation.slide_height = PptxInches(7.5)
    content_lines = lines
    slide_groups = []
    current = []
    for line in content_lines:
        if len(current) >= 12:
            slide_groups.append(current)
            current = []
        current.append(line)
    if current:
        slide_groups.append(current)

    background = _hex_rgb(palette["background"])
    primary = _hex_rgb(palette["primary"])
    ink = _hex_rgb(palette["ink"])
    muted = _hex_rgb(palette["muted"])

    for slide_index, group in enumerate(slide_groups):
        slide = presentation.slides.add_slide(presentation.slide_layouts[6])
        fill = slide.background.fill
        fill.solid()
        fill.fore_color.rgb = PptxColor(*background)

        header = slide.shapes.add_shape(
            MSO_SHAPE.RECTANGLE,
            0,
            0,
            presentation.slide_width,
            PptxInches(0.16),
        )
        header.fill.solid()
        header.fill.fore_color.rgb = PptxColor(*primary)
        header.line.fill.background()

        title_box = slide.shapes.add_textbox(
            PptxInches(0.6),
            PptxInches(0.42),
            PptxInches(12.1),
            PptxInches(0.65),
        )
        title_frame = title_box.text_frame
        title_frame.text = title if slide_index == 0 else group[0][:110]
        title_paragraph = title_frame.paragraphs[0]
        title_paragraph.font.name = "Aptos Display"
        title_paragraph.font.size = PptxPt(26)
        title_paragraph.font.bold = True
        title_paragraph.font.color.rgb = PptxColor(*primary)

        body_lines = group if slide_index == 0 else group[1:]
        body_box = slide.shapes.add_textbox(
            PptxInches(0.72),
            PptxInches(1.3),
            PptxInches(11.9),
            PptxInches(5.55),
        )
        text_frame = body_box.text_frame
        text_frame.clear()
        text_frame.word_wrap = True
        text_frame.margin_left = PptxInches(0.08)
        text_frame.margin_right = PptxInches(0.08)
        text_frame.vertical_anchor = MSO_ANCHOR.TOP

        if not body_lines:
            body_lines = group
        for line_index, line in enumerate(body_lines):
            paragraph = (
                text_frame.paragraphs[0]
                if line_index == 0
                else text_frame.add_paragraph()
            )
            paragraph.text = line[:500]
            paragraph.font.name = "Aptos"
            paragraph.font.size = PptxPt(
                16 if line.startswith(("#", "Executive Summary", "At a glance")) else 13
            )
            paragraph_color = ink if line_index == 0 else muted
            paragraph.font.color.rgb = PptxColor(*paragraph_color)
            paragraph.space_after = PptxPt(9)
            paragraph.level = 0
            if line.startswith(("#", "Executive Summary", "Key Findings")):
                paragraph.font.bold = True
                paragraph.font.color.rgb = PptxColor(*primary)

        footer = slide.shapes.add_textbox(
            PptxInches(0.7),
            PptxInches(7.12),
            PptxInches(11.9),
            PptxInches(0.18),
        )
        footer.text_frame.text = f"Insight Studio · {slide_index + 1} / {len(slide_groups)}"
        footer_paragraph = footer.text_frame.paragraphs[0]
        footer_paragraph.font.size = PptxPt(8)
        footer_paragraph.font.color.rgb = PptxColor(*muted)
        footer_paragraph.alignment = PP_ALIGN.RIGHT

    for chart in charts:
        slide = presentation.slides.add_slide(presentation.slide_layouts[6])
        slide.background.fill.solid()
        slide.background.fill.fore_color.rgb = PptxColor(*background)
        header = slide.shapes.add_shape(
            MSO_SHAPE.RECTANGLE,
            0,
            0,
            presentation.slide_width,
            PptxInches(0.16),
        )
        header.fill.solid()
        header.fill.fore_color.rgb = PptxColor(*primary)
        header.line.fill.background()

        title_box = slide.shapes.add_textbox(
            PptxInches(0.6),
            PptxInches(0.42),
            PptxInches(12.1),
            PptxInches(0.65),
        )
        title_box.text_frame.text = chart["title"][:110]
        title_paragraph = title_box.text_frame.paragraphs[0]
        title_paragraph.font.name = "Aptos Display"
        title_paragraph.font.size = PptxPt(24)
        title_paragraph.font.bold = True
        title_paragraph.font.color.rgb = PptxColor(*primary)

        maximum_width = max(bar["width"] for bar in chart["bars"]) or 1
        for index, bar in enumerate(chart["bars"]):
            y = PptxInches(1.55 + index * 0.58)
            label = slide.shapes.add_textbox(
                PptxInches(0.72),
                y,
                PptxInches(2.15),
                PptxInches(0.34),
            )
            label.text_frame.text = bar["label"][:36]
            label_paragraph = label.text_frame.paragraphs[0]
            label_paragraph.font.size = PptxPt(11)
            label_paragraph.font.color.rgb = PptxColor(*muted)

            bar_width = max(
                0.06,
                7.0 * bar["width"] / maximum_width,
            )
            shape = slide.shapes.add_shape(
                MSO_SHAPE.ROUNDED_RECTANGLE,
                PptxInches(2.95),
                y + PptxInches(0.025),
                PptxInches(bar_width),
                PptxInches(0.26),
            )
            shape.fill.solid()
            shape.fill.fore_color.rgb = PptxColor(*_hex_rgb(bar["color"]))
            shape.line.fill.background()

            value_box = slide.shapes.add_textbox(
                PptxInches(min(10.25, 3.05 + bar_width)),
                y,
                PptxInches(1.35),
                PptxInches(0.34),
            )
            value_box.text_frame.text = bar["value"][:24]
            value_paragraph = value_box.text_frame.paragraphs[0]
            value_paragraph.font.size = PptxPt(10)
            value_paragraph.font.bold = True
            value_paragraph.font.color.rgb = PptxColor(*ink)

        footer = slide.shapes.add_textbox(
            PptxInches(0.7),
            PptxInches(7.12),
            PptxInches(11.9),
            PptxInches(0.18),
        )
        footer.text_frame.text = "Insight Studio · Editable chart"
        footer.text_frame.paragraphs[0].font.size = PptxPt(8)
        footer.text_frame.paragraphs[0].font.color.rgb = PptxColor(*muted)
        footer.text_frame.paragraphs[0].alignment = PP_ALIGN.RIGHT

    output = BytesIO()
    presentation.save(output)
    return output.getvalue()


def generate_docx(title, report):
    document = Document()
    document.add_heading(title, level=0)
    for line in report.splitlines():
        value = line.strip()
        if not value:
            continue
        if value.startswith("### "):
            document.add_heading(value[4:], level=3)
        elif value.startswith("## "):
            document.add_heading(value[3:], level=2)
        elif value.startswith("# "):
            document.add_heading(value[2:], level=1)
        elif value.startswith(("- ", "* ")):
            document.add_paragraph(value[2:], style="List Bullet")
        elif re.match(r"^\d+[.)]\s+", value):
            document.add_paragraph(re.sub(r"^\d+[.)]\s+", "", value), style="List Number")
        else:
            document.add_paragraph(value)
    output = BytesIO()
    document.save(output)
    return output.getvalue()


def generate_pdf(title, report):
    output = BytesIO()
    document = SimpleDocTemplate(
        output,
        pagesize=A4,
        rightMargin=20 * mm,
        leftMargin=20 * mm,
        topMargin=20 * mm,
        bottomMargin=18 * mm,
        title=title,
    )
    styles = getSampleStyleSheet()
    styles.add(
        ParagraphStyle(
            name="InsightTitle",
            parent=styles["Title"],
            textColor=colors.HexColor("#9f263b"),
            alignment=TA_LEFT,
            spaceAfter=12,
        )
    )
    styles.add(
        ParagraphStyle(
            name="InsightHeading",
            parent=styles["Heading2"],
            textColor=colors.HexColor("#9f263b"),
            spaceBefore=11,
            spaceAfter=5,
        )
    )
    story = [Paragraph(html.escape(title), styles["InsightTitle"]), Spacer(1, 4)]
    for line in report.splitlines():
        value = line.strip()
        if not value:
            story.append(Spacer(1, 4))
        elif value.startswith("#"):
            heading = value.lstrip("#").strip()
            story.append(Paragraph(html.escape(heading), styles["InsightHeading"]))
        elif value.startswith(("- ", "* ")):
            story.append(
                Paragraph(
                    "&#8226;&nbsp; " + html.escape(value[2:]),
                    styles["BodyText"],
                )
            )
        else:
            story.append(Paragraph(html.escape(value), styles["BodyText"]))
    document.build(story)
    return output.getvalue()
