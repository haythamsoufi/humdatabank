"""InDesign IDML package for UPR visuals (optional Word narrative)."""

from __future__ import annotations

import re
import zipfile
from io import BytesIO
from pathlib import Path
from xml.sax.saxutils import escape

A4_W = 595.275590551181
A4_H = 841.8897637795276
_PAGE_TY = -A4_H / 2
_SPREAD_GAP = 72.0
_MASTER_ID = "uca"
_MASTER_PAGE_ID = "ucb"
_LAYER_ID = "ub3"
_NO_FILL = (
    'FillColor="Swatch/None" StrokeColor="Swatch/None" StrokeWeight="0" '
    'FillTint="-1" StrokeTint="-1" AppliedObjectStyle="ObjectStyle/NoFill"'
)

# Measured on the official combined WeasyPrint PDF (points).
HEADER_H = 121.6
FOOTER_TOP = 788.0
FOLLOW_MARGIN = 28.34645669291339  # 10 mm
LOGO = 78.0
LOGO_PAD = 18.0
LOGO_Y = 17.4
PNG_DPI = 150.0
MIN_CROP = 20.0

HEADING_PREFIXES = (
    "IN SUPPORT OF",
    "PEOPLE REACHED",
    "FINANCIAL OVERVIEW",
    "ONGOING EMERGENCY INDICATORS",
    "STRATEGIC PRIORITIES",
    "ENABLING FUNCTIONS",
    "IFRC NETWORK-SUPPORTED ACTIVITIES",
)

COLORS = {
    "Black": ("CMYK", "0 0 0 100"),
    "Paper": ("CMYK", "0 0 0 0"),
    "IFRCRed": ("RGB", "210 39 48"),
    "IFRCNavy": ("RGB", "1 30 65"),
    "IFRCGrey": ("RGB", "88 89 91"),
    "IFRCMuted": ("RGB", "176 177 179"),
    "AppealPink": ("RGB", "229 122 127"),
    "ReachGrey": ("RGB", "242 242 242"),
    "LightGrey": ("RGB", "241 241 241"),
    "QRed": ("RGB", "239 51 64"),
    "BannerNavy": ("RGB", "27 54 93"),
}

# Measured on Bangladesh_INP_AR_2025.pdf narrative pages (InDesign 21.3).
_STYLE_RUNS = {
    "QHeading": {"font": "Montserrat", "style": "Bold", "size": "20", "color": "Color/QRed"},
    "SectionHead": {"font": "Montserrat", "style": "Bold", "size": "15", "color": "Color/IFRCNavy"},
    "TopicHead": {"font": "Montserrat", "style": "Bold", "size": "14", "color": "Color/BannerNavy"},
    "BandHead": {"font": "Montserrat", "style": "Bold", "size": "16", "color": "Color/BannerNavy"},
    "Subhead": {"font": "Open Sans", "style": "Bold", "size": "10", "color": "Color/Black"},
    "Body": {"font": "Open Sans", "style": "Regular", "size": "10", "color": "Color/Black"},
    "AdditionalHead": {"font": "Montserrat", "style": "Bold", "size": "9.5", "color": "Color/Black"},
    "SourceItem": {"font": "Open Sans", "style": "Regular", "size": "9.5", "color": "Color/Black"},
    "ContactHead": {"font": "Open Sans", "style": "Bold", "size": "10", "color": "Color/QRed"},
    "ContactName": {"font": "Open Sans", "style": "Bold", "size": "9.5", "color": "Color/Black"},
    "ContactDetail": {"font": "Open Sans", "style": "Regular", "size": "9.5", "color": "Color/Black"},
    "Blank": {"font": "Open Sans", "style": "Regular", "size": "10", "color": "Color/Black"},
}


def _item_transform(x: float, y: float) -> str:
    return f"1 0 0 1 {x:.6f} {_PAGE_TY + y:.6f}"


def _xml_text(value: str) -> str:
    return "".join(ch for ch in (value or "") if ch == "\t" or ch == "\n" or ord(ch) >= 32)


class Idml:
    def __init__(self) -> None:
        self._n = 0x1000
        self.stories: dict[str, str] = {}
        self.spreads: list[str] = []
        self.spread_ids: list[str] = []
        self.hyperlinks: list[tuple[str, str, str, str]] = []
        self.page_count = 0

    def uid(self, prefix: str = "u") -> str:
        self._n += 1
        return f"u{self._n:x}"

    def _path(self, w: float, h: float) -> str:
        return (
            "<Properties><PathGeometry><GeometryPathType PathOpen='false'><PathPointArray>"
            f'<PathPointType Anchor="0 0" LeftDirection="0 0" RightDirection="0 0"/>'
            f'<PathPointType Anchor="0 {h:.4f}" LeftDirection="0 {h:.4f}" RightDirection="0 {h:.4f}"/>'
            f'<PathPointType Anchor="{w:.4f} {h:.4f}" LeftDirection="{w:.4f} {h:.4f}" RightDirection="{w:.4f} {h:.4f}"/>'
            f'<PathPointType Anchor="{w:.4f} 0" LeftDirection="{w:.4f} 0" RightDirection="{w:.4f} 0"/>'
            "</PathPointArray></GeometryPathType></PathGeometry></Properties>"
        )

    def story(
        self,
        runs: list[dict[str, str]],
        *,
        align: str = "LeftAlign",
    ) -> str:
        sid = self.uid()
        ranges = []
        for run in runs:
            font = run.get("font", "Arial")
            style = run.get("style", "Regular")
            size = run.get("size", "11")
            color = run.get("color", "Color/Black")
            text = run.get("text", "")
            content = escape(_xml_text(text)).replace("\n", "</Content><Br/><Content>")
            ranges.append(
                "<CharacterStyleRange "
                f'AppliedCharacterStyle="CharacterStyle/$ID/[No character style]" '
                f'FillColor="{color}" PointSize="{size}" FontStyle="{style}">'
                f"<Properties><AppliedFont type='string'>{escape(font)}</AppliedFont></Properties>"
                f"<Content>{content}</Content></CharacterStyleRange>"
            )
        body = (
            f'<Story Self="{sid}" AppliedTOCStyle="n" TrackChanges="false" StoryTitle="$ID/">'
            '<StoryPreference OpticalMarginAlignment="false" OpticalMarginSize="12" '
            'FrameType="TextFrameType"/>'
            f'<ParagraphStyleRange AppliedParagraphStyle="ParagraphStyle/$ID/NormalParagraphStyle" '
            f'Justification="{align}">'
            f"{''.join(ranges)}</ParagraphStyleRange></Story>"
        )
        self.stories[sid] = body
        return sid

    def _hyperlink_source(self, url: str, inner_xml: str) -> str:
        source_id = f"HyperlinkTextSource/{self.uid()}"
        dest_id = f"HyperlinkURLDestination/{self.uid()}"
        hid = self.uid()
        self.hyperlinks.append((hid, source_id, dest_id, url))
        name = escape(_xml_text(url), {'"': "&quot;"})
        return (
            f'<HyperlinkTextSource Self="{source_id}" Name="{name}" Hidden="false" '
            f'AppliedCharacterStyle="n">{inner_xml}</HyperlinkTextSource>'
        )

    def styled_story(self, paragraphs: list[dict]) -> str:
        sid = self.uid()
        ranges: list[str] = []
        for para in paragraphs:
            if para.get("kind") == "table":
                ranges.append(self._story_table(para.get("rows") or []))
                continue
            style_name = para["style"]
            base = _STYLE_RUNS[style_name]
            runs = para.get("runs") or [{"text": para.get("text") or "", "href": "", "bold": False}]
            parts: list[str] = []
            first = True
            for run in runs:
                text = run.get("text") or ""
                if first and style_name == "SourceItem":
                    text = f"• {text.lstrip()}"
                    first = False
                elif first:
                    first = False
                if not text:
                    continue
                href = (run.get("href") or "").strip()
                font_style = "Bold" if run.get("bold") and style_name != "AdditionalHead" else base["style"]
                if style_name == "ContactName":
                    font_style = "Bold"
                color = base["color"]
                extra = ""
                inner = f"<Content>{escape(_xml_text(text)).replace(chr(10), ' ')}</Content>"
                if href:
                    inner = self._hyperlink_source(href, inner)
                    color = "Color/QRed"
                    extra = (
                        ' Underline="true" UnderlineColor="Color/QRed" '
                        'UnderlineOffset="1" UnderlineWeight="0.75"'
                    )
                parts.append(
                    "<CharacterStyleRange "
                    'AppliedCharacterStyle="CharacterStyle/$ID/[No character style]" '
                    f'FillColor="{color}" PointSize="{base["size"]}" FontStyle="{font_style}"{extra}>'
                    f"<Properties><AppliedFont type='string'>{escape(base['font'])}</AppliedFont></Properties>"
                    f"{inner}</CharacterStyleRange>"
                )
            if not parts:
                parts.append(
                    "<CharacterStyleRange "
                    'AppliedCharacterStyle="CharacterStyle/$ID/[No character style]" '
                    f'FillColor="{base["color"]}" PointSize="{base["size"]}" FontStyle="{base["style"]}">'
                    f"<Properties><AppliedFont type='string'>{escape(base['font'])}</AppliedFont></Properties>"
                    "<Content> </Content></CharacterStyleRange>"
                )
            parts.append(
                "<CharacterStyleRange "
                'AppliedCharacterStyle="CharacterStyle/$ID/[No character style]">'
                "<Br/></CharacterStyleRange>"
            )
            ranges.append(
                f'<ParagraphStyleRange AppliedParagraphStyle="ParagraphStyle/{style_name}">'
                f"{''.join(parts)}</ParagraphStyleRange>"
            )
        body = (
            f'<Story Self="{sid}" AppliedTOCStyle="n" TrackChanges="false" StoryTitle="Narrative">'
            '<StoryPreference OpticalMarginAlignment="false" OpticalMarginSize="12" '
            'FrameType="TextFrameType"/>'
            f"{''.join(ranges)}</Story>"
        )
        self.stories[sid] = body
        return sid

    def _story_table(self, rows: list[list[list[dict]]]) -> str:
        if not rows:
            return ""
        cols = max(len(row) for row in rows)
        two = cols == 2
        label_w = NARRATIVE_W * 0.36 if two else NARRATIVE_W
        value_w = NARRATIVE_W - label_w if two else 0.0
        tid = self.uid()
        parts = [
            f'<Table Self="{tid}" HeaderRowCount="0" FooterRowCount="0" BodyRowCount="{len(rows)}" '
            f'ColumnCount="{cols}" AppliedTableStyle="TableStyle/$ID/[Basic Table]" '
            'TableDirection="LeftToRightDirection">'
        ]
        for r, row in enumerate(rows):
            height = max((_table_cell_height(cell) for cell in row), default=18.0)
            parts.append(
                f'<Row Self="{self.uid()}" Name="{r}" SingleRowHeight="{height:.2f}" '
                f'TextTopInset="3" TextBottomInset="3"/>'
            )
        for c in range(cols):
            width = label_w if c == 0 else (value_w if two else NARRATIVE_W / cols)
            parts.append(f'<Column Self="{self.uid()}" Name="{c}" SingleColumnWidth="{width:.2f}"/>')
        for r, row in enumerate(rows):
            padded = list(row) + [[] for _ in range(cols - len(row))]
            for c, cell in enumerate(padded[:cols]):
                label = two and c == 0
                fill = "Color/IFRCNavy" if label else "Color/LightGrey"
                text_color = "Color/Paper" if label else "Color/Black"
                font_style = "Bold" if label else "Regular"
                inner = self._table_cell_paras(cell, text_color=text_color, font_style=font_style, force_bold=label)
                parts.append(
                    f'<Cell Self="{self.uid()}" Name="{c}:{r}" RowSpan="1" ColumnSpan="1" '
                    f'AppliedCellStyle="CellStyle/$ID/[None]" FillColor="{fill}" '
                    'VerticalJustification="CenterAlign" LeftInset="6" RightInset="6" '
                    'TopInset="4" BottomInset="4" '
                    'TopEdgeStrokeWeight="0.4" LeftEdgeStrokeWeight="0.4" '
                    'BottomEdgeStrokeWeight="0.4" RightEdgeStrokeWeight="0.4" '
                    'TopEdgeStrokeColor="Color/Black" LeftEdgeStrokeColor="Color/Black" '
                    'BottomEdgeStrokeColor="Color/Black" RightEdgeStrokeColor="Color/Black">'
                    f"{inner}</Cell>"
                )
        parts.append("</Table>")
        return "".join(parts)

    def _table_cell_paras(self, paras: list[dict], *, text_color: str, font_style: str, force_bold: bool) -> str:
        if not paras:
            paras = [{"text": "", "runs": [{"text": "", "href": "", "bold": False}]}]
        chunks: list[str] = []
        for para in paras:
            runs = para.get("runs") or [{"text": para.get("text") or "", "href": "", "bold": False}]
            parts: list[str] = []
            for run in runs:
                text = run.get("text") or ""
                if not text:
                    continue
                href = (run.get("href") or "").strip()
                style = "Bold" if force_bold or run.get("bold") else font_style
                color = "Color/QRed" if href and not force_bold else text_color
                inner = f"<Content>{escape(_xml_text(text)).replace(chr(10), ' ')}</Content>"
                extra = ""
                if href:
                    inner = self._hyperlink_source(href, inner)
                    extra = (
                        ' Underline="true" UnderlineColor="Color/QRed" '
                        'UnderlineOffset="1" UnderlineWeight="0.75"'
                    )
                    if not force_bold:
                        color = "Color/QRed"
                parts.append(
                    "<CharacterStyleRange "
                    'AppliedCharacterStyle="CharacterStyle/$ID/[No character style]" '
                    f'FillColor="{color}" PointSize="9" FontStyle="{style}"{extra}>'
                    "<Properties><AppliedFont type='string'>Open Sans</AppliedFont></Properties>"
                    f"{inner}</CharacterStyleRange>"
                )
            if not parts:
                parts.append(
                    "<CharacterStyleRange AppliedCharacterStyle=\"CharacterStyle/$ID/[No character style]\">"
                    "<Content> </Content></CharacterStyleRange>"
                )
            chunks.append(
                '<ParagraphStyleRange AppliedParagraphStyle="ParagraphStyle/Body" '
                'Justification="LeftAlign" SpaceBefore="0" SpaceAfter="2">'
                f"{''.join(parts)}</ParagraphStyleRange>"
            )
        return "".join(chunks)

    def threaded_frame(
        self,
        x: float,
        y: float,
        w: float,
        h: float,
        story_id: str,
        fid: str,
        *,
        previous: str = "n",
        nxt: str = "n",
    ) -> str:
        return (
            f'<TextFrame Self="{fid}" ParentStory="{story_id}" NextTextFrame="{nxt}" '
            f'PreviousTextFrame="{previous}" ContentType="TextType" '
            f'ItemTransform="{_item_transform(x, y)}" ItemLayer="{_LAYER_ID}" Visible="true" '
            f'{_NO_FILL} Locked="false">'
            f"{self._path(w, h)}"
            '<TextFramePreference TextColumnCount="1" VerticalJustification="TopAlign"/>'
            '<TextWrapPreference Inverse="false" TextWrapMode="None"/>'
            "</TextFrame>"
        )

    def text_frame(
        self,
        x: float,
        y: float,
        w: float,
        h: float,
        story_id: str,
        *,
        valign: str = "TopAlign",
        inset: float | tuple[float, float, float, float] = 0.0,
        fill: str = "Swatch/None",
        stroke: str = "Swatch/None",
        weight: str = "0",
        radius: float = 0,
    ) -> str:
        fid = self.uid()
        inset_xml = ""
        if inset:
            if isinstance(inset, tuple):
                top, left, bottom, right = inset
            else:
                top = left = bottom = right = float(inset)
            inset_xml = (
                "<Properties><InsetSpacing type='list'>"
                f"<ListItem type='unit'>{top:.4f}</ListItem>"
                f"<ListItem type='unit'>{left:.4f}</ListItem>"
                f"<ListItem type='unit'>{bottom:.4f}</ListItem>"
                f"<ListItem type='unit'>{right:.4f}</ListItem>"
                "</InsetSpacing></Properties>"
            )
        corners = ""
        if radius:
            corners = (
                ' TopLeftCornerOption="RoundedCorner" TopRightCornerOption="RoundedCorner" '
                'BottomLeftCornerOption="RoundedCorner" BottomRightCornerOption="RoundedCorner" '
                f'TopLeftCornerRadius="{radius:.2f}" TopRightCornerRadius="{radius:.2f}" '
                f'BottomLeftCornerRadius="{radius:.2f}" BottomRightCornerRadius="{radius:.2f}"'
            )
        fill_attr = (
            f'FillColor="{fill}" StrokeColor="{stroke}" StrokeWeight="{weight}" '
            f'FillTint="-1" StrokeTint="-1" '
            f'AppliedObjectStyle="{"ObjectStyle/NoFill" if fill == "Swatch/None" else "ObjectStyle/Filled"}"'
        )
        return (
            f'<TextFrame Self="{fid}" ParentStory="{story_id}" NextTextFrame="n" PreviousTextFrame="n" '
            f'ContentType="TextType" ItemTransform="{_item_transform(x, y)}" '
            f'ItemLayer="{_LAYER_ID}" Visible="true" {fill_attr}{corners} Locked="false">'
            f"{self._path(w, h)}"
            f'<TextFramePreference TextColumnCount="1" VerticalJustification="{valign}" '
            'FirstBaselineOffset="CapHeight" MinimumFirstBaselineOffset="0">'
            f"{inset_xml}</TextFramePreference>"
            '<TextWrapPreference Inverse="false" TextWrapMode="None"/>'
            "</TextFrame>"
        )

    def rect(
        self,
        x: float,
        y: float,
        w: float,
        h: float,
        fill: str,
        *,
        stroke: str = "Swatch/None",
        weight: str = "0",
        radius: float = 0,
    ) -> str:
        rid = self.uid()
        corners = ""
        if radius:
            corners = (
                ' TopLeftCornerOption="RoundedCorner" TopRightCornerOption="RoundedCorner" '
                'BottomLeftCornerOption="RoundedCorner" BottomRightCornerOption="RoundedCorner" '
                f'TopLeftCornerRadius="{radius:.2f}" TopRightCornerRadius="{radius:.2f}" '
                f'BottomLeftCornerRadius="{radius:.2f}" BottomRightCornerRadius="{radius:.2f}"'
            )
        return (
            f'<Rectangle Self="{rid}" ContentType="Unassigned" '
            f'ItemTransform="{_item_transform(x, y)}" ItemLayer="{_LAYER_ID}" Visible="true" '
            f'FillColor="{fill}" StrokeColor="{stroke}" StrokeWeight="{weight}"{corners} '
            f'AppliedObjectStyle="{"ObjectStyle/NoFill" if fill == "Swatch/None" else "ObjectStyle/Filled"}" '
            'Locked="false">'
            f"{self._path(w, h)}"
            '<TextWrapPreference Inverse="false" TextWrapMode="None"/>'
            "</Rectangle>"
        )

    def image_frame(self, x: float, y: float, w: float, h: float, uri: str, img_w: float, img_h: float) -> str:
        rid, iid, lid = self.uid(), self.uid(), self.uid()
        scale = min(w / img_w, h / img_h) if img_w and img_h else 1.0
        dw, dh = img_w * scale, img_h * scale
        ox, oy = (w - dw) / 2, (h - dh) / 2
        escaped_uri = escape(uri, {'"': "&quot;"})
        return (
            f'<Rectangle Self="{rid}" ContentType="GraphicType" '
            f'ItemTransform="{_item_transform(x, y)}" ItemLayer="{_LAYER_ID}" Visible="true" '
            f'{_NO_FILL} Locked="false">'
            f"{self._path(w, h)}"
            '<FrameFittingOption FittingOnEmptyFrame="Proportional" FittingAlignment="CenterAnchor"/>'
            f'<Image Self="{iid}" ImageTypeName="$ID/Portable Network Graphics" '
            f'ItemTransform="{scale:.6f} 0 0 {scale:.6f} {ox:.4f} {oy:.4f}" Visible="true">'
            "<Properties>"
            "<Profile type='enumeration'>UseDocument</Profile>"
            f'<GraphicBounds Left="0" Top="0" Right="{img_w:.4f}" Bottom="{img_h:.4f}"/>'
            "</Properties>"
            f'<Link Self="{lid}" LinkResourceURI="{escaped_uri}" '
            'LinkResourceFormat="$ID/PNG" StoredState="Normal" LinkResourceModified="false" '
            'LinkObjectModified="false" ShowInUI="true" CanEmbed="true" CanUnembed="true" '
            'CanPackage="true" ImportPolicy="Unmanaged"/>'
            "</Image></Rectangle>"
        )

    def svg_frame(self, x: float, y: float, w: float, h: float, uri: str, svg_w: float, svg_h: float) -> str:
        rid, gid, lid = self.uid(), self.uid(), self.uid()
        scale = min(w / svg_w, h / svg_h) if svg_w and svg_h else 1.0
        escaped_uri = escape(uri, {'"': "&quot;"})
        return (
            f'<Rectangle Self="{rid}" ContentType="GraphicType" '
            f'ItemTransform="{_item_transform(x, y)}" ItemLayer="{_LAYER_ID}" Visible="true" '
            f'{_NO_FILL} Locked="false">'
            f"{self._path(w, h)}"
            '<FrameFittingOption FittingOnEmptyFrame="ContentToFrame" FittingAlignment="TopLeftAnchor"/>'
            f'<SVG Self="{gid}" ImageTypeName="$ID/Scalable Vector Graphics" '
            f'ItemTransform="{scale:.6f} 0 0 {scale:.6f} 0 0" Visible="true">'
            "<Properties>"
            "<Profile type='enumeration'>UseDocument</Profile>"
            f'<GraphicBounds Left="0" Top="0" Right="{svg_w:.4f}" Bottom="{svg_h:.4f}"/>'
            "</Properties>"
            f'<Link Self="{lid}" LinkResourceURI="{escaped_uri}" '
            'LinkResourceFormat="$ID/Scalable Vector Graphics" StoredState="Normal" '
            'LinkResourceModified="false" LinkObjectModified="false" ShowInUI="true" '
            'CanEmbed="true" CanUnembed="true" CanPackage="true" ImportPolicy="Unmanaged"/>'
            "</SVG></Rectangle>"
        )

    def pdf_page_frame(self, filename: str, page_number: int, pdf_w: float, pdf_h: float) -> str:
        """Full-bleed placed PDF page. Used only with --pdf-link."""
        rid, gid, lid = self.uid(), self.uid(), self.uid()
        scale = min(A4_W / pdf_w, A4_H / pdf_h) if pdf_w and pdf_h else 1.0
        dw, dh = pdf_w * scale, pdf_h * scale
        ox, oy = (A4_W - dw) / 2.0, (A4_H - dh) / 2.0
        uri = f"file:Links/{filename}"
        escaped_uri = escape(uri, {'"': "&quot;"})
        return (
            f'<Rectangle Self="{rid}" ContentType="GraphicType" '
            f'ItemTransform="{_item_transform(0, 0)}" ItemLayer="{_LAYER_ID}" Visible="true" '
            f'{_NO_FILL} Locked="false">'
            f"{self._path(A4_W, A4_H)}"
            '<FrameFittingOption FittingOnEmptyFrame="ContentToFrame" FittingAlignment="CenterAnchor"/>'
            f'<PDF Self="{gid}" GrayVectorPolicy="IgnoreAll" RGBVectorPolicy="IgnoreAll" '
            f'CMYKVectorPolicy="IgnoreAll" ItemTransform="{scale:.6f} 0 0 {scale:.6f} {ox:.4f} {oy:.4f}" '
            'Visible="true">'
            "<Properties>"
            "<Profile type='enumeration'>UseDocument</Profile>"
            f'<GraphicBounds Left="0" Top="0" Right="{pdf_w:.4f}" Bottom="{pdf_h:.4f}"/>'
            "</Properties>"
            f'<Link Self="{lid}" LinkResourceURI="{escaped_uri}" '
            'LinkResourceFormat="$ID/Adobe Portable Document Format (PDF)" StoredState="Normal" '
            'LinkResourceModified="false" LinkObjectModified="false" ShowInUI="true" '
            'CanEmbed="true" CanUnembed="true" CanPackage="true" ImportPolicy="Unmanaged"/>'
            f'<PDFAttribute PageNumber="{page_number}" PDFCrop="CropContentVisibleLayers" '
            'TransparentBackground="false"/>'
            "</PDF></Rectangle>"
        )

    def pdf_band_frame(
        self,
        filename: str,
        page_number: int,
        pdf_w: float,
        pdf_h: float,
        x: float,
        y: float,
        w: float,
        h: float,
    ) -> str:
        """Place one region of a WeasyPrint page at the same A4 coordinates."""
        rid, gid, lid = self.uid(), self.uid(), self.uid()
        uri = f"file:Links/{filename}"
        escaped_uri = escape(uri, {'"': "&quot;"})
        return (
            f'<Rectangle Self="{rid}" ContentType="GraphicType" '
            f'ItemTransform="{_item_transform(x, y)}" ItemLayer="{_LAYER_ID}" Visible="true" '
            f'{_NO_FILL} Locked="false">'
            f"{self._path(w, h)}"
            '<FrameFittingOption FittingOnEmptyFrame="None" FittingAlignment="TopLeftAnchor"/>'
            f'<PDF Self="{gid}" GrayVectorPolicy="IgnoreAll" RGBVectorPolicy="IgnoreAll" '
            f'CMYKVectorPolicy="IgnoreAll" ItemTransform="1 0 0 1 {-x:.4f} {-y:.4f}" Visible="true">'
            "<Properties>"
            "<Profile type='enumeration'>UseDocument</Profile>"
            f'<GraphicBounds Left="0" Top="0" Right="{pdf_w:.4f}" Bottom="{pdf_h:.4f}"/>'
            "</Properties>"
            f'<Link Self="{lid}" LinkResourceURI="{escaped_uri}" '
            'LinkResourceFormat="$ID/Adobe Portable Document Format (PDF)" StoredState="Normal" '
            'LinkResourceModified="false" LinkObjectModified="false" ShowInUI="true" '
            'CanEmbed="true" CanUnembed="true" CanPackage="true" ImportPolicy="Unmanaged"/>'
            f'<PDFAttribute PageNumber="{page_number}" PDFCrop="CropMedia" '
            'TransparentBackground="false"/>'
            "</PDF></Rectangle>"
        )

    def add_page(self, items: list[str]) -> None:
        self.page_count += 1
        sid, pid = self.uid(), self.uid()
        spread_ty = -(self.page_count - 1) * (A4_H + _SPREAD_GAP)
        self.spread_ids.append(sid)
        self.spreads.append(
            f'<Spread Self="{sid}" FlattenerOverride="Default" PageCount="1" BindingLocation="0" '
            f'ShowMasterItems="true" AllowPageShuffle="true" PageTransitionType="None" '
            f'ItemTransform="1 0 0 1 0 {spread_ty:.6f}">'
            '<FlattenerPreference LineArtAndTextResolution="300" GradientAndMeshResolution="150" '
            'ClipComplexRegions="false"/>'
            f'<Page Self="{pid}" AppliedMaster="{_MASTER_ID}" AppliedTrapPreset="n" Name="{self.page_count}" '
            f'GeometricBounds="0 0 {A4_H:.6f} {A4_W:.6f}" MasterPageTransform="1 0 0 1 0 0" '
            f'ItemTransform="1 0 0 1 0 {_PAGE_TY:.6f}">'
            '<MarginPreference ColumnCount="1" ColumnGutter="12" Top="0" Bottom="0" '
            'Left="0" Right="0" ColumnDirection="Horizontal"/>'
            "</Page>"
            f"{''.join(items)}</Spread>"
        )

    def _hyperlinks_xml(self) -> str:
        dests: list[str] = []
        links: list[str] = []
        for key, (hid, source_id, dest_id, url) in enumerate(self.hyperlinks, start=1):
            safe = escape(_xml_text(url), {'"': "&quot;"})
            dests.append(
                f'<HyperlinkURLDestination Self="{dest_id}" Name="{safe}" '
                f'DestinationUniqueKey="{key}" Hidden="false" DestinationURL="{safe}"/>'
            )
            links.append(
                f'<Hyperlink Self="{hid}" Name="{safe}" Source="{source_id}" Visible="true" '
                'Highlight="None" Width="Thin" BorderStyle="Solid" Hidden="false">'
                "<Properties><BorderColor type='enumeration'>Black</BorderColor>"
                f"<Destination type='object'>{dest_id}</Destination></Properties>"
                "</Hyperlink>"
            )
        return (
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<idPkg:Hyperlinks xmlns:idPkg="http://ns.adobe.com/AdobeInDesign/idml/1.0/packaging" '
            f'DOMVersion="16.0">{"".join(dests)}{"".join(links)}</idPkg:Hyperlinks>'
        )

    def package_bytes(self) -> bytes:
        story_list = " ".join(self.stories)
        spread_refs = "".join(f'<idPkg:Spread src="Spreads/Spread_{sid}.xml"/>' for sid in self.spread_ids)
        story_refs = "".join(f'<idPkg:Story src="Stories/Story_{sid}.xml"/>' for sid in self.stories)
        designmap = (
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
            '<?aid style="50" type="document" readerVersion="6.0" featureSet="257" product="16.0(0)" ?>\n'
            '<Document xmlns:idPkg="http://ns.adobe.com/AdobeInDesign/idml/1.0/packaging" '
            f'DOMVersion="16.0" Self="d" StoryList="{story_list}" ZeroPoint="0 0" '
            f'ActiveLayer="{_LAYER_ID}" CMYKProfile="$ID/" RGBProfile="$ID/" '
            'SolidColorIntent="UseColorSettings" AfterBlendingIntent="UseColorSettings">'
            '<idPkg:Graphic src="Resources/Graphic.xml"/>'
            '<idPkg:Fonts src="Resources/Fonts.xml"/>'
            '<idPkg:Styles src="Resources/Styles.xml"/>'
            '<idPkg:Preferences src="Resources/Preferences.xml"/>'
            + ('<idPkg:Hyperlinks src="Resources/Hyperlinks.xml"/>' if self.hyperlinks else '')
            + '<idPkg:Tags src="XML/Tags.xml"/>'
            f'<Layer Self="{_LAYER_ID}" Name="Layer 1" Visible="true" Locked="false" IgnoreWrap="false" '
            'ShowGuides="true" LockGuides="false" UI="true" Expendable="true" Printable="true"/>'
            f'<idPkg:MasterSpread src="MasterSpreads/MasterSpread_{_MASTER_ID}.xml"/>'
            f"{spread_refs}"
            '<idPkg:BackingStory src="XML/BackingStory.xml"/>'
            f"{story_refs}"
            "</Document>"
        )
        swatches = [
            '<Swatch Self="Swatch/None" Name="$ID/[None]" ColorEditable="false" '
            'ColorRemovable="false" Visible="false"/>',
        ]
        for name, (space, value) in COLORS.items():
            extra = ""
            if name == "Black":
                extra = ' ColorOverride="Specialblack"'
            elif name == "Paper":
                extra = ' ColorOverride="Specialpaper"'
            swatches.append(
                f'<Color Self="Color/{name}" Model="Process" Space="{space}" '
                f'ColorValue="{value}"{extra} Name="{name}"/>'
            )
        files = {
            "mimetype": "application/vnd.adobe.indesign-idml-package",
            "META-INF/container.xml": (
                '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
                '<container version="1.0" xmlns="urn:oasis:names:tc:opendocument:xmlns:container">'
                "<rootfiles><rootfile full-path='designmap.xml' "
                "media-type='application/vnd.adobe.indesign-idml-package'/></rootfiles></container>"
            ),
            "META-INF/metadata.xml": (
                '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
                '<x:xmpmeta xmlns:x="adobe:ns:meta/"><rdf:RDF xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#">'
                '<rdf:Description rdf:about="" xmlns:dc="http://purl.org/dc/elements/1.1/">'
                "<dc:format>application/x-indesign</dc:format></rdf:Description></rdf:RDF></x:xmpmeta>"
            ),
            "designmap.xml": designmap,
            "Resources/Graphic.xml": (
                '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
                '<idPkg:Graphic xmlns:idPkg="http://ns.adobe.com/AdobeInDesign/idml/1.0/packaging" DOMVersion="16.0">'
                f"{''.join(swatches)}</idPkg:Graphic>"
            ),
            "Resources/Fonts.xml": _fonts_xml(),
            "Resources/Styles.xml": _styles_xml(),
            "Resources/Preferences.xml": (
                '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
                '<idPkg:Preferences xmlns:idPkg="http://ns.adobe.com/AdobeInDesign/idml/1.0/packaging" DOMVersion="16.0">'
                f'<DocumentPreference PageHeight="{A4_H}" PageWidth="{A4_W}" PageOrientation="Portrait" '
                'FacingPages="false" PagesPerDocument="1" ColumnCount="1" ColumnGutter="12" '
                'PageBinding="LeftToRight" Intent="PrintIntent"/>'
                '<PageItemDefault FillColor="Swatch/None" FillTint="-1" StrokeColor="Swatch/None" '
                'StrokeTint="-1" StrokeWeight="0" AppliedTextObjectStyle="ObjectStyle/NoFill" '
                'AppliedGraphicObjectStyle="ObjectStyle/NoFill"/>'
                "</idPkg:Preferences>"
            ),
            **({"Resources/Hyperlinks.xml": self._hyperlinks_xml()} if self.hyperlinks else {}),
            f"MasterSpreads/MasterSpread_{_MASTER_ID}.xml": (
                '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
                '<idPkg:MasterSpread xmlns:idPkg="http://ns.adobe.com/AdobeInDesign/idml/1.0/packaging" DOMVersion="16.0">'
                f'<MasterSpread Self="{_MASTER_ID}" Name="A-Master" NamePrefix="A" BaseName="Master" '
                'ItemTransform="1 0 0 1 0 0" ShowMasterItems="true" PageCount="1" BindingLocation="0">'
                f'<Page Self="{_MASTER_PAGE_ID}" AppliedMaster="n" Name="A" '
                f'GeometricBounds="0 0 {A4_H:.6f} {A4_W:.6f}" '
                f'ItemTransform="1 0 0 1 0 {_PAGE_TY:.6f}">'
                '<MarginPreference ColumnCount="1" ColumnGutter="12" Top="0" Bottom="0" '
                'Left="0" Right="0"/></Page></MasterSpread></idPkg:MasterSpread>'
            ),
            "XML/BackingStory.xml": (
                '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
                '<idPkg:BackingStory xmlns:idPkg="http://ns.adobe.com/AdobeInDesign/idml/1.0/packaging" DOMVersion="16.0">'
                '<XmlStory Self="BackingStoryItem" AppliedTOCStyle="n" StoryTitle="$ID/">'
                '<StoryPreference FrameType="Unknown"/></XmlStory></idPkg:BackingStory>'
            ),
            "XML/Tags.xml": (
                '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
                '<idPkg:Tags xmlns:idPkg="http://ns.adobe.com/AdobeInDesign/idml/1.0/packaging" DOMVersion="16.0">'
                '<XMLTag Self="XMLTag/Root" Name="Root">'
                '<Properties><TagColor type="enumeration">LightBlue</TagColor></Properties>'
                "</XMLTag></idPkg:Tags>"
            ),
        }
        for sid, xml_body in self.stories.items():
            files[f"Stories/Story_{sid}.xml"] = (
                '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
                '<idPkg:Story xmlns:idPkg="http://ns.adobe.com/AdobeInDesign/idml/1.0/packaging" '
                f'DOMVersion="16.0">{xml_body}</idPkg:Story>'
            )
        for sid, xml_body in zip(self.spread_ids, self.spreads):
            files[f"Spreads/Spread_{sid}.xml"] = (
                '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
                '<idPkg:Spread xmlns:idPkg="http://ns.adobe.com/AdobeInDesign/idml/1.0/packaging" '
                f'DOMVersion="16.0">{xml_body}</idPkg:Spread>'
            )
        out = BytesIO()
        with zipfile.ZipFile(out, "w") as zf:
            zf.writestr("mimetype", files["mimetype"], compress_type=zipfile.ZIP_STORED)
            for name, data in files.items():
                if name != "mimetype":
                    zf.writestr(name, data, compress_type=zipfile.ZIP_DEFLATED)
        return out.getvalue()


def _fonts_xml() -> str:
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<idPkg:Fonts xmlns:idPkg="http://ns.adobe.com/AdobeInDesign/idml/1.0/packaging" DOMVersion="16.0">'
        '<FontFamily Self="ffMontserrat" Name="Montserrat">'
        '<Font Self="fMontReg" FontFamily="Montserrat" Name="Montserrat Regular" FullName="Montserrat Regular" '
        'FontStyleName="Regular" FontType="TrueType" WritingScript="0" PostScriptName="Montserrat-Regular"/>'
        '<Font Self="fMontBold" FontFamily="Montserrat" Name="Montserrat Bold" FullName="Montserrat Bold" '
        'FontStyleName="Bold" FontType="TrueType" WritingScript="0" PostScriptName="Montserrat-Bold"/>'
        "</FontFamily>"
        '<FontFamily Self="ffOpenSans" Name="Open Sans">'
        '<Font Self="fOsReg" FontFamily="Open Sans" Name="Open Sans Regular" FullName="Open Sans Regular" '
        'FontStyleName="Regular" FontType="TrueType" WritingScript="0" PostScriptName="OpenSans-Regular"/>'
        '<Font Self="fOsBold" FontFamily="Open Sans" Name="Open Sans Bold" FullName="Open Sans Bold" '
        'FontStyleName="Bold" FontType="TrueType" WritingScript="0" PostScriptName="OpenSans-Bold"/>'
        "</FontFamily>"
        '<FontFamily Self="ffArial" Name="Arial">'
        '<Font Self="fArialReg" FontFamily="Arial" Name="Arial Regular" FullName="Arial" '
        'FontStyleName="Regular" FontType="TrueType" WritingScript="0" PostScriptName="ArialMT"/>'
        '<Font Self="fArialBold" FontFamily="Arial" Name="Arial Bold" FullName="Arial Bold" '
        'FontStyleName="Bold" FontType="TrueType" WritingScript="0" PostScriptName="Arial-BoldMT"/>'
        '<Font Self="fArialItalic" FontFamily="Arial" Name="Arial Italic" FullName="Arial Italic" '
        'FontStyleName="Italic" FontType="TrueType" WritingScript="0" PostScriptName="Arial-ItalicMT"/>'
        "</FontFamily></idPkg:Fonts>"
    )


def _para_style(
    self_id: str,
    name: str,
    *,
    size: str,
    style: str,
    color: str,
    font: str,
    leading: str,
    space_before: str = "0",
    space_after: str = "8",
    align: str = "LeftAlign",
    extra: str = "",
    props_extra: str = "",
) -> str:
    return (
        f'<ParagraphStyle Self="ParagraphStyle/{self_id}" Name="{name}" '
        'BasedOn="ParagraphStyle/$ID/NormalParagraphStyle" '
        f'PointSize="{size}" FontStyle="{style}" FillColor="{color}" '
        f'Justification="{align}" SpaceBefore="{space_before}" SpaceAfter="{space_after}" '
        f'Hyphenation="false"{extra}>'
        f"<Properties><AppliedFont type='string'>{font}</AppliedFont>"
        f"<Leading type='unit'>{leading}</Leading>{props_extra}</Properties>"
        "</ParagraphStyle>"
    )


def _styles_xml() -> str:
    band = ' RuleBelow="true" RuleBelowLineWeight="2" RuleBelowColor="Color/BannerNavy" RuleBelowOffset="3"'
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<idPkg:Styles xmlns:idPkg="http://ns.adobe.com/AdobeInDesign/idml/1.0/packaging" DOMVersion="16.0">'
        '<RootCharacterStyleGroup Self="uCharacterStyleGroup">'
        '<CharacterStyle Self="CharacterStyle/$ID/[No character style]" Name="$ID/[No character style]"/>'
        "</RootCharacterStyleGroup>"
        '<RootParagraphStyleGroup Self="uParagraphStyleGroup">'
        '<ParagraphStyle Self="ParagraphStyle/$ID/NormalParagraphStyle" Name="$ID/NormalParagraphStyle"/>'
        + _para_style("QHeading", "Q Heading", size="20", style="Bold", color="Color/QRed", font="Montserrat", leading="24", space_before="4", space_after="12")
        + _para_style("SectionHead", "Section heading", size="15", style="Bold", color="Color/IFRCNavy", font="Montserrat", leading="18", space_before="16", space_after="6")
        + _para_style("TopicHead", "Topic heading", size="14", style="Bold", color="Color/BannerNavy", font="Montserrat", leading="17", space_before="12", space_after="6")
        + _para_style("BandHead", "Band heading", size="16", style="Bold", color="Color/BannerNavy", font="Montserrat", leading="20", space_before="14", space_after="10", extra=band)
        + _para_style("Subhead", "Subhead", size="10", style="Bold", color="Color/Black", font="Open Sans", leading="13.5", space_before="10", space_after="6")
        + _para_style(
            "Body",
            "Body",
            size="10",
            style="Regular",
            color="Color/Black",
            font="Open Sans",
            leading="13.5",
            space_before="0",
            space_after="8.5",
            align="LeftJustified",
        )
        + _para_style("AdditionalHead", "Additional information", size="9.5", style="Bold", color="Color/Black", font="Montserrat", leading="12", space_before="8", space_after="10")
        + _para_style("SourceItem", "Source item", size="9.5", style="Regular", color="Color/Black", font="Open Sans", leading="13", space_before="0", space_after="6", align="LeftAlign")
        + _para_style("ContactHead", "Contact heading", size="10", style="Bold", color="Color/QRed", font="Open Sans", leading="13", space_before="16", space_after="10")
        + _para_style("ContactName", "Contact name", size="9.5", style="Bold", color="Color/Black", font="Open Sans", leading="13", space_before="10", space_after="1")
        + _para_style("ContactDetail", "Contact detail", size="9.5", style="Regular", color="Color/Black", font="Open Sans", leading="13", space_before="0", space_after="1")
        + _para_style("Blank", "Blank line", size="10", style="Regular", color="Color/Black", font="Open Sans", leading="12", space_before="0", space_after="4")
        + "</RootParagraphStyleGroup>"
        '<RootTableStyleGroup Self="uTableStyleGroup">'
        '<TableStyle Self="TableStyle/$ID/[No Table Style]" Name="$ID/[No Table Style]"/>'
        '<TableStyle Self="TableStyle/$ID/[Basic Table]" Name="$ID/[Basic Table]"/>'
        "</RootTableStyleGroup>"
        '<RootCellStyleGroup Self="uCellStyleGroup">'
        '<CellStyle Self="CellStyle/$ID/[None]" Name="$ID/[None]"/>'
        "</RootCellStyleGroup>"
        '<RootObjectStyleGroup Self="uObjectStyleGroup">'
        '<ObjectStyle Self="ObjectStyle/$ID/[None]" Name="$ID/[None]" '
        'FillColor="Swatch/None" StrokeColor="Swatch/None" StrokeWeight="0" '
        'FillTint="-1" StrokeTint="-1" EnableFill="true" EnableStroke="true"/>'
        '<ObjectStyle Self="ObjectStyle/$ID/[Normal Text Frame]" Name="$ID/[Normal Text Frame]" '
        'FillColor="Swatch/None" StrokeColor="Swatch/None" StrokeWeight="0" '
        'FillTint="-1" StrokeTint="-1" EnableFill="true" EnableStroke="true"/>'
        '<ObjectStyle Self="ObjectStyle/NoFill" Name="No fill" '
        'FillColor="Swatch/None" StrokeColor="Swatch/None" StrokeWeight="0" '
        'FillTint="-1" StrokeTint="-1" EnableFill="true" EnableStroke="true"/>'
        '<ObjectStyle Self="ObjectStyle/Filled" Name="Filled" EnableFill="true" EnableStroke="true"/>'
        "</RootObjectStyleGroup></idPkg:Styles>"
    )


def _lines(page) -> list[dict]:
    rows: list[dict] = []
    for block in page.get_text("dict")["blocks"]:
        if block.get("type") != 0:
            continue
        for line in block.get("lines", []):
            text = "".join(span.get("text", "") for span in line.get("spans", [])).strip()
            if not text:
                continue
            x0, y0, x1, y1 = line["bbox"]
            size = line["spans"][0].get("size") if line.get("spans") else 11
            rows.append({"text": text, "x": x0, "y": y0, "x1": x1, "y1": y1, "size": float(size or 11)})
    rows.sort(key=lambda r: (r["y"], r["x"]))
    return rows


def _is_heading(text: str) -> bool:
    upper = text.upper()
    return any(upper.startswith(prefix) for prefix in HEADING_PREFIXES)


def _is_native_extra(text: str) -> bool:
    low = text.lower()
    if low.startswith("in swiss francs"):
        return True
    if text.startswith("MDR") and " / " in text:
        return True
    return False


def _save_clip(page, rect, path: Path) -> tuple[float, float]:
    import fitz

    matrix = fitz.Matrix(PNG_DPI / 72.0, PNG_DPI / 72.0)
    pix = page.get_pixmap(matrix=matrix, clip=rect, alpha=False)
    pix.save(str(path))
    return float(pix.width), float(pix.height)


def _rgba_png_bytes(doc, xref: int, smask: int) -> bytes | None:
    import fitz

    pix = fitz.Pixmap(doc, xref)
    mask = fitz.Pixmap(doc, smask)
    try:
        pix = fitz.Pixmap(pix, mask)
    except Exception:
        return None
    if pix.colorspace and pix.colorspace.n == 4:
        pix = fitz.Pixmap(fitz.csRGB, pix)
    return pix.tobytes("png")


def _masked_icon_pngs(doc) -> dict[int, bytes]:
    icons: dict[int, bytes] = {}
    for page in doc:
        for img in page.get_images(full=True):
            xref, smask = img[0], img[1]
            if not smask or xref in icons:
                continue
            png = _rgba_png_bytes(doc, xref, smask)
            if png:
                icons[xref] = png
    return icons


def _png_wh(png: bytes) -> tuple[int, int]:
    return int.from_bytes(png[16:20], "big"), int.from_bytes(png[20:24], "big")


def _fix_svg_icon_alpha(svg: str, icons: dict[int, bytes]) -> str:
    """MuPDF writes icon SMasks as black squares. Swap those images for RGBA PNGs."""
    import base64
    from collections import defaultdict, deque

    by_size: dict[tuple[int, int], deque[bytes]] = defaultdict(deque)
    for png in icons.values():
        by_size[_png_wh(png)].append(png)

    def repl(match: re.Match[str]) -> str:
        prefix, href = match.group(1), match.group(2)
        try:
            raw = base64.b64decode(href.split(",", 1)[-1])
        except Exception:
            return match.group(0)
        if len(raw) < 26 or raw[25] == 6:
            return match.group(0)
        width, height = _png_wh(raw)
        queue = by_size.get((width, height))
        if not queue:
            return match.group(0)
        png = queue[0]
        queue.rotate(-1)
        return prefix + "data:image/png;base64," + base64.b64encode(png).decode("ascii")

    return re.sub(
        r'(<image\b[^>]*?(?:xlink:)?href=")(data:image/png;base64,[^"]+)',
        repl,
        svg,
        flags=re.DOTALL,
    )


def _ensure_payload(payload: dict) -> dict:
    return payload


def _visual_dashboard_ids(payload: dict) -> list[str]:
    kind = (payload.get("meta") or {}).get("kind") or "report"
    if kind == "plan":
        return ["in_support", "reach", "financial", "network_funding", "support"]
    ids = ["in_support", "reach", "financial"]
    for emergency in payload.get("emergencies") or []:
        ids.append(f"emergency_{int(emergency['slot'])}")
    if payload.get("core_indicators"):
        ids.append("strategic_priorities")
    if payload.get("enabling_indicators"):
        ids.append("enabling_functions")
    ids.append("support")
    return ids


def _usable_icon_src(src: str) -> bool:
    raw = (src or "").strip()
    return raw.startswith(("data:", "file:")) or (raw.startswith("/") and Path(raw).is_file())


def _hydrate_reach_icons(payload: dict, pdf_doc) -> None:
    """Combined PDF has the catalog SPEF icons; isolated HTML often lost them."""
    import base64
    import fitz

    rows = payload.get("people_reached") or []
    if not rows or all(_usable_icon_src(str(row.get("icon_src") or "")) for row in rows):
        return
    for page in pdf_doc:
        heading = next((row for row in _lines(page) if row["text"].upper().startswith("PEOPLE REACHED") or row["text"].upper().startswith("PEOPLE TO BE REACHED")), None)
        if heading is None:
            continue
        bottom = FOOTER_TOP
        for row in _lines(page):
            if row["y"] > heading["y1"] + 8 and _is_heading(row["text"]):
                bottom = row["y"]
                break
        stolen: list[tuple[float, bytes]] = []
        for img in page.get_images(full=True):
            xref, smask = img[0], img[1]
            for rect in page.get_image_rects(xref):
                if rect.y0 < heading["y"] - 4 or rect.y1 > bottom + 4:
                    continue
                if rect.width < 12 or rect.width > 90 or rect.height < 12 or rect.height > 90:
                    continue
                png = _rgba_png_bytes(pdf_doc, xref, smask) if smask else fitz.Pixmap(pdf_doc, xref).tobytes("png")
                if png:
                    stolen.append((float(rect.x0), png))
        stolen.sort(key=lambda item: item[0])
        for row, (_x, png) in zip(rows, stolen):
            row["icon_src"] = "data:image/png;base64," + base64.b64encode(png).decode("ascii")
        return


def _section_htmls(payload: dict) -> list[tuple[str, str]]:
    from plugins.upr_visuals import render as R

    wrap = R._combined_section_wrap
    kind = (payload.get("meta") or {}).get("kind") or "report"
    sections = [
        ("in_support", wrap(R._in_support(payload))),
        ("reach", wrap(R._reach(payload))),
    ]
    if kind == "plan":
        sections += [
            ("financial", wrap(R._plan_funding(payload))),
            ("network_funding", wrap(R._network_funding(payload))),
            ("support", wrap(R._support(payload))),
        ]
        return sections
    sections.append(("financial", wrap(R._financial(payload))))
    heading = (
        "<h2 class='upr-block__title upr-block__title--center "
        "upr-combined-heading'>ONGOING EMERGENCY INDICATORS</h2>"
    )
    for index, emergency in enumerate(payload.get("emergencies") or []):
        block = R._emergency(payload, int(emergency["slot"]))
        name = f"emergency_{int(emergency['slot'])}"
        sections.append((name, wrap(heading + block if index == 0 else block)))
    if payload.get("core_indicators"):
        sections.append(("strategic_priorities", wrap(R._strategic_priorities(payload))))
    if payload.get("enabling_indicators"):
        sections.append(("enabling_functions", wrap(R._enabling_functions(payload))))
    sections.append(("support", wrap(R._support(payload))))
    return sections


def _tight_clip(page, *, full_width: bool = False):
    """Trim to ink (text/icons). Ignore tall empty section boxes WeasyPrint leaves behind."""
    import fitz
    from plugins.upr_visuals.raster import _is_page_backdrop

    clip = fitz.Rect()
    for block in page.get_text("blocks"):
        clip |= fitz.Rect(block[:4])
    for info in page.get_image_info():
        clip |= fitz.Rect(info["bbox"])
    if clip.is_empty:
        return page.rect
    limit = clip.y1 + 10.0
    try:
        drawings = page.get_drawings()
    except Exception:
        drawings = []
    for drawing in drawings:
        rect = drawing.get("rect")
        if not rect or _is_page_backdrop(drawing, page.rect):
            continue
        box = fitz.Rect(rect)
        if box.y0 > limit or box.y1 < clip.y0 - 4.0:
            continue
        box.y1 = min(box.y1, limit)
        clip |= box
    if full_width:
        clip.x0 = page.rect.x0
        clip.x1 = page.rect.x1
    else:
        clip.x0 = max(page.rect.x0, clip.x0 - 3.0)
        clip.x1 = min(page.rect.x1, clip.x1 + 3.0)
    clip.y0 = max(page.rect.y0, clip.y0 - 3.0)
    clip.y1 = min(page.rect.y1, clip.y1 + 3.0)
    return clip


def _write_isolated_svg(pdf_bytes: bytes, dest: Path, *, full_width: bool = False) -> list[tuple[str, float, float]]:
    """One complete visual → SVG. Keep A4 width; trim empty paper above/below only."""
    import fitz

    src = fitz.open(stream=pdf_bytes, filetype="pdf")
    icons = _masked_icon_pngs(src)
    exported: list[tuple[str, float, float]] = []
    try:
        for index, page in enumerate(src):
            clip = _tight_clip(page, full_width=full_width)
            tmp = fitz.open()
            try:
                new_page = tmp.new_page(width=float(clip.width), height=float(clip.height))
                new_page.show_pdf_page(new_page.rect, src, index, clip=clip)
                svg = _fix_svg_icon_alpha(new_page.get_svg_image(), icons)
            finally:
                tmp.close()
            path = dest if src.page_count == 1 else dest.with_name(f"{dest.stem}-{index + 1}{dest.suffix}")
            path.write_text(svg, encoding="utf-8")
            exported.append((path.name, float(clip.width), float(clip.height)))
    finally:
        src.close()
    return exported


def _svg_wh(path: Path) -> tuple[float, float]:
    head = path.read_text(encoding="utf-8", errors="replace")[:1500]
    match = re.search(r'width="([\d.]+)"[^>]*height="([\d.]+)"', head)
    if not match:
        return 0.0, 0.0
    return float(match.group(1)), float(match.group(2))


_FLOW_IDS = {"strategic_priorities", "enabling_functions", "support"}


def export_visual_svgs(payload: dict, links: Path) -> list[tuple[str, str, float, float]]:
    from plugins.upr_visuals.raster import render_pdf_bytes

    for stale in links.glob("visual-p*.svg"):
        stale.unlink()
    exported: list[tuple[str, str, float, float]] = []
    reuse = False
    standalone: list[tuple[str, str]] = []
    flow_html: list[str] = []
    for dashboard_id, section_html in _section_htmls(payload):
        if dashboard_id in _FLOW_IDS:
            flow_html.append(section_html)
        else:
            standalone.append((dashboard_id, section_html))

    for dashboard_id, section_html in standalone:
        dest = links / f"{dashboard_id}.svg"
        existing = [dest] if dest.is_file() else sorted(links.glob(f"{dashboard_id}-*.svg"))
        if reuse and existing:
            for path in existing:
                width, height = _svg_wh(path)
                if width and height:
                    exported.append((dashboard_id, path.name, width, height))
            continue
        extra = ""
        if dashboard_id == "reach":
            extra = (
                "<style>"
                ".upr-block--reach,.upr-combined-section > .upr-block--reach{"
                "margin-left:0;margin-right:0;width:100%;max-width:none;"
                "padding:1.15rem 10mm 1.35rem;}"
                "</style>"
            )
        html = extra + f'<div class="upr-dashboard upr-dashboard--combined">{section_html}</div>'
        pdf_bytes = render_pdf_bytes(html, dashboard_id="combined")
        for name, width, height in _write_isolated_svg(pdf_bytes, dest, full_width=dashboard_id == "reach"):
            exported.append((dashboard_id, name, width, height))

    if flow_html:
        for pattern in ("strategic_priorities*.svg", "enabling_functions*.svg", "support.svg", "indicators*.svg"):
            for path in links.glob(pattern):
                path.unlink()
        html = f'<div class="upr-dashboard upr-dashboard--combined">{"".join(flow_html)}</div>'
        pdf_bytes = render_pdf_bytes(html, dashboard_id="combined")
        for name, width, height in _write_isolated_svg(pdf_bytes, links / "indicators.svg"):
            exported.append(("indicators", name, width, height))
    return exported


def _heading_key(text: str) -> str:
    upper = text.upper()
    if upper.startswith("IN SUPPORT"):
        return "in_support"
    if upper.startswith("PEOPLE REACHED") or upper.startswith("PEOPLE TO BE"):
        return "reach"
    if upper.startswith("FINANCIAL"):
        return "financial"
    if upper.startswith("ONGOING EMERGENCY"):
        return "emergency_1"
    if upper.startswith("STRATEGIC"):
        return "strategic_priorities"
    if upper.startswith("ENABLING"):
        return "enabling_functions"
    if upper.startswith("IFRC NETWORK"):
        return "support"
    if upper.startswith("NETWORK FUNDING") or upper.startswith("FUNDING FROM"):
        return "network_funding"
    return ""


def _section_bands(pdf_doc) -> dict[str, tuple[int, float, float]]:
    """Page + [y0, y1) for each visual, from the combined WeasyPrint PDF."""
    heads: list[tuple[int, float, str]] = []
    for index, page in enumerate(pdf_doc):
        for row in _lines(page):
            if not _is_heading(row["text"]):
                continue
            key = _heading_key(row["text"])
            if key and key not in {item[2] for item in heads}:
                heads.append((index, float(row["y"]), key))
    bands: dict[str, tuple[int, float, float]] = {}
    for i, (page_i, y0, key) in enumerate(heads):
        if i + 1 < len(heads) and heads[i + 1][0] == page_i:
            y1 = heads[i + 1][1]
        elif page_i == 0:
            y1 = FOOTER_TOP - 4.0
        else:
            y1 = A4_H - FOLLOW_MARGIN
        if y1 > y0 + MIN_CROP:
            bands[key] = (page_i, y0, y1)
    return bands


def _measure_footer(page) -> dict[str, dict]:
    found: dict[str, dict] = {}
    for row in _lines(page):
        low = row["text"].lower()
        if low.startswith("appeal number"):
            found["appeal"] = row
        elif "information on data scope" in low:
            found["note"] = row
        elif low.startswith("international federation of red"):
            found["org"] = row
    return found


def _label(
    doc: Idml,
    text: str,
    *,
    x: float,
    y: float,
    w: float,
    h: float,
    size: str,
    color: str,
    style: str = "Bold",
    align: str = "CenterAlign",
    valign: str = "TopAlign",
    inset: float | tuple[float, float, float, float] = 0.0,
    fill: str = "Swatch/None",
    stroke: str = "Swatch/None",
    weight: str = "0",
    radius: float = 0,
) -> str:
    return doc.text_frame(
        x,
        y,
        w,
        h,
        doc.story([{"text": text, "style": style, "size": size, "color": color}], align=align),
        valign=valign,
        inset=inset,
        fill=fill,
        stroke=stroke,
        weight=weight,
        radius=radius,
    )


def build_cover_chrome(
    doc: Idml,
    meta: dict,
    logos: dict[str, tuple[str, float, float]],
    footer: dict[str, dict] | None = None,
) -> list[str]:
    from plugins.upr_visuals.formatters import appeal_number
    from plugins.upr_visuals.render import COVER_FOOTER_NOTE, COVER_FOOTER_ORG

    country = (meta.get("country_name") or "").strip().upper()
    subtitle = (meta.get("document_subtitle") or "").strip()
    date_text = (meta.get("header_date") or "").strip()
    prefix = (meta.get("header_prefix") or "IN SUPPORT OF").strip()
    ns = (meta.get("national_society") or "").strip()
    appeal = appeal_number(meta.get("iso2") or meta.get("appeal_iso2"))
    footer = footer or {}

    items = [
        doc.rect(0, 0, A4_W, HEADER_H, "Color/IFRCNavy"),
        doc.rect(111.0, 64.6, 314.6, 5.2, "Color/IFRCRed"),
        _label(doc, country, x=111.0, y=22.0, w=370.0, h=46.0, size="38", color="Color/Paper", align="LeftAlign"),
        _label(doc, subtitle, x=111.0, y=74.5, w=370.0, h=18.0, size="12", color="Color/Paper", style="Regular", align="LeftAlign"),
    ]
    ifrc = logos.get("ifrc")
    if ifrc:
        items.append(doc.image_frame(LOGO_PAD, LOGO_Y, LOGO, LOGO, ifrc[0], ifrc[1], ifrc[2]))
    ns_logo = logos.get("ns")
    ns_x = A4_W - LOGO_PAD - LOGO
    if ns_logo:
        items.append(doc.image_frame(ns_x, LOGO_Y, LOGO, LOGO, ns_logo[0], ns_logo[1], ns_logo[2]))
    if date_text:
        date_w = 130.0
        date_x = A4_W - LOGO_PAD - date_w
        date_y = LOGO_Y + LOGO + 3.0 if ns_logo else 93.5
        items.append(
            _label(
                doc,
                date_text,
                x=date_x,
                y=date_y,
                w=date_w,
                h=14.0,
                size="9",
                color="Color/Paper",
                style="Italic",
                align="RightAlign",
            )
        )

    pad_x = 22.7
    box_y = 788.0
    if appeal:
        appeal_text = f"Appeal number  {appeal}"
        appeal_w, appeal_h = 138.0, 15.5
        items.append(
            _label(
                doc,
                appeal_text,
                x=pad_x,
                y=box_y,
                w=appeal_w,
                h=appeal_h,
                size="8",
                color="Color/AppealPink",
                style="Regular",
                align="LeftAlign",
                valign="CenterAlign",
                inset=(0.0, 7.0, 0.0, 7.0),
                stroke="Color/IFRCRed",
                weight="0.75",
            )
        )
    note_text = f"*{COVER_FOOTER_NOTE}"
    note_w, note_h = 268.0, 15.5
    note_x = A4_W - pad_x - note_w
    items += [
        _label(
            doc,
            note_text,
            x=note_x,
            y=box_y,
            w=note_w,
            h=note_h,
            size="7",
            color="Color/Paper",
            style="Regular",
            align="CenterAlign",
            valign="CenterAlign",
            inset=(0.0, 10.0, 0.0, 10.0),
            fill="Color/IFRCRed",
            radius=note_h / 2.0,
        ),
        _label(
            doc,
            COVER_FOOTER_ORG,
            x=pad_x,
            y=814.0,
            w=A4_W - pad_x * 2,
            h=12.0,
            size="7",
            color="Color/IFRCMuted",
            style="Regular",
            valign="CenterAlign",
        ),
    ]
    _ = (prefix, ns)
    return items


def build_native_pages(doc: Idml, pdf_doc, payload: dict, links: Path, pdf_name: str = "") -> int:
    import fitz

    payload = _ensure_payload(payload)
    _hydrate_reach_icons(payload, pdf_doc)
    meta = payload.get("meta") or {}
    svgs = export_visual_svgs(payload, links)

    logos: dict[str, tuple[str, float, float]] = {}
    first = pdf_doc[0]
    for key, box in (
        ("ifrc", fitz.Rect(LOGO_PAD, LOGO_Y, LOGO_PAD + LOGO, LOGO_Y + LOGO)),
        ("ns", fitz.Rect(A4_W - LOGO_PAD - LOGO, LOGO_Y, A4_W - LOGO_PAD, LOGO_Y + LOGO)),
    ):
        path = links / f"logo-{key}.png"
        w, h = _save_clip(first, box, path)
        logos[key] = (f"file:Links/{path.name}", w, h)

    margin = FOLLOW_MARGIN
    content_w = A4_W - margin * 2

    def page_bottom(page_i: int) -> float:
        return (FOOTER_TOP - 8.0) if page_i == 0 else (A4_H - margin)

    items_by_page: dict[int, list[str]] = {}
    items_by_page[0] = build_cover_chrome(doc, meta, logos, _measure_footer(first))

    last_page, last_bottom = 0, HEADER_H + 6.0
    cover_ids = {"in_support", "reach", "financial"}
    for dashboard_id, name, svg_w, svg_h in svgs:
        if svg_w <= 0 or svg_h <= 0:
            continue
        bleed = dashboard_id == "reach"
        frame_w = A4_W if bleed else content_w
        frame_h = svg_h * (frame_w / svg_w)
        cover = dashboard_id in cover_ids
        if cover and last_page == 0:
            page_i, y = 0, last_bottom
        else:
            page_i, y = last_page, last_bottom
            if page_i == 0:
                page_i, y = 1, margin
        bottom = page_bottom(page_i)
        if y + frame_h > bottom + 1:
            if cover and page_i == 0 and not bleed:
                scale = max(0.35, (bottom - y) / frame_h)
                frame_w, frame_h = frame_w * scale, frame_h * scale
            elif not cover or page_i != 0:
                page_i += 1
                y = margin
                bottom = page_bottom(page_i)
                if y + frame_h > bottom + 1:
                    scale = (bottom - y) / frame_h
                    frame_w, frame_h = frame_w * scale, frame_h * scale
        frame_x = 0.0 if bleed else margin + (content_w - frame_w) / 2.0
        items_by_page.setdefault(page_i, [])
        if bleed:
            items_by_page[page_i].append(doc.rect(0, y, A4_W, frame_h, "Color/ReachGrey"))
        items_by_page[page_i].append(
            doc.svg_frame(frame_x, y, frame_w, frame_h, f"file:Links/{name}", svg_w, svg_h)
        )
        last_page, last_bottom = page_i, y + frame_h + 8.0

    for page_i in sorted(items_by_page):
        if items_by_page[page_i]:
            doc.add_page(items_by_page[page_i])
    return len(svgs)


NARRATIVE_X = 34.0
NARRATIVE_Y = 32.0
NARRATIVE_W = 529.9
NARRATIVE_H = 760.0
FOLIO_Y = 803.7
FOLIO_LABEL = "2025 IFRC network annual report"
_PARA_HEIGHT = {
    "QHeading": 40.0,
    "SectionHead": 40.0,
    "TopicHead": 35.0,
    "BandHead": 44.0,
    "Subhead": 29.5,
    "AdditionalHead": 30.0,
    "SourceItem": 19.0,
    "ContactHead": 39.0,
    "ContactName": 24.0,
    "ContactDetail": 14.0,
}

_BANDS = {
    "ongoing emergency response",
    "strategic priorities",
    "enabling local actors",
    "success stories",
}
_MAJOR_H2 = {"context", "key achievements"}
_SUBHEADS = {
    "progress by the national society against objectives",
    "ifrc network joint support",
    "short description of the emergency operational strategy",
    "emergency appeal name",
    "emergency appeal number",
    "people assisted",
}
_SKIP_EXACT = {
    "(table for data)",
}
_SKIP_COVER_RE = re.compile(
    r"^(ifrc network (annual report|unified plan).+|appeal code:.+)$",
    re.IGNORECASE,
)
_SKIP_PREFIX = ("<space", "(table")


def _para_hrefs(row: dict) -> list[str]:
    return [str(run.get("href") or "").strip() for run in (row.get("runs") or []) if str(run.get("href") or "").strip()]


def _para_is_bold(row: dict) -> bool:
    runs = [run for run in (row.get("runs") or []) if (run.get("text") or "").strip()]
    return bool(runs) and all(bool(run.get("bold")) for run in runs)


def _looks_like_link_line(text: str) -> bool:
    low = text.lower()
    return (
        "@" in text
        or "www." in low
        or low.startswith("http")
        or ".pdf" in low
        or low.startswith("t +")
        or low.startswith("t+")
    )


def _narrative_style(
    text: str,
    state: str,
    role: str = "",
    *,
    bullet: bool = False,
    has_href: bool = False,
    bold: bool = False,
) -> tuple[str | None, str]:
    raw = (text or "").strip()
    if not raw:
        return None, state
    low = raw.lower()
    if low.startswith("(box for additional"):
        return "AdditionalHead", "sources"
    if (
        low in _SKIP_EXACT
        or _SKIP_COVER_RE.match(raw)
        or any(low.startswith(p) for p in _SKIP_PREFIX)
        or role == "meta"
    ):
        return None, state
    if low == "additional information":
        return "AdditionalHead", "sources"
    if low == "contact information":
        return "ContactHead", "contact"
    if state == "sources":
        if low == "contact information":
            return "ContactHead", "contact"
        return "SourceItem", "sources"
    if state == "contact":
        if bold and not _looks_like_link_line(raw):
            return "ContactName", "contact"
        return "ContactDetail", "contact"
    if role == "body" and not low.startswith("q"):
        if low in _BANDS or low in _MAJOR_H2 or low in _SUBHEADS:
            pass
        else:
            return "Body", state
    if (low.startswith("q") and len(raw) < 120) or low.startswith("annex"):
        return "QHeading", "q"
    if low in _BANDS or (raw.isupper() and len(raw) > 14 and not low.startswith("mdr")):
        return "BandHead", f"band:{low}"
    if low in _MAJOR_H2:
        return "SectionHead", "major"
    if low in _SUBHEADS or (low.startswith("mdr") and len(raw) < 16):
        return "Subhead", state
    if role in {"h1", "h2"}:
        if state.startswith("band:") and any(key in state for key in ("strategic", "enabling", "success")):
            return "TopicHead", state
        if state == "major":
            return "Subhead", state
        return "TopicHead", state
    if (
        state.startswith("band:")
        and len(raw) < 70
        and not raw.endswith((".", ","))
        and not _looks_like_link_line(raw)
    ):
        return "TopicHead", state
    return "Body", state


def _table_cell_height(paras: list[dict]) -> float:
    if not paras:
        return 16.0
    lines = 0
    for para in paras:
        text = (para.get("text") or "").strip()
        lines += max(1, (len(text) + 48) // 49)
    return max(16.0, 12.0 * lines + 6.0)


def _parse_word_para(p_el, hrefs: dict[str, str], w_ns: str, r_ns: str) -> dict | None:
    ppr = p_el.find(f"{w_ns}pPr")
    bullet = ppr is not None and ppr.find(f"{w_ns}numPr") is not None
    runs: list[dict] = []
    for child in list(p_el):
        if child.tag == f"{w_ns}hyperlink":
            href = hrefs.get(child.get(f"{r_ns}id") or "", "")
            for r_el in child.iter(f"{w_ns}r"):
                text = "".join((t.text or "") for t in r_el.iter(f"{w_ns}t"))
                if not text:
                    continue
                rpr = r_el.find(f"{w_ns}rPr")
                bold = rpr is not None and rpr.find(f"{w_ns}b") is not None
                runs.append({"text": text, "href": href, "bold": bold})
        elif child.tag == f"{w_ns}r":
            text = "".join((t.text or "") for t in child.iter(f"{w_ns}t"))
            if not text:
                continue
            rpr = child.find(f"{w_ns}rPr")
            bold = rpr is not None and rpr.find(f"{w_ns}b") is not None
            runs.append({"text": text, "href": "", "bold": bold})
    text = "".join(run["text"] for run in runs).strip()
    if not text:
        return {"text": "", "runs": [], "bullet": False, "role": "empty"}
    return {"text": text, "runs": runs, "bullet": bullet, "role": ""}


def _parse_word_table(tbl, hrefs: dict[str, str], w_ns: str, r_ns: str) -> dict | None:
    rows: list[list[list[dict]]] = []
    for tr in tbl.findall(f"{w_ns}tr"):
        row: list[list[dict]] = []
        for tc in tr.findall(f"{w_ns}tc"):
            cell: list[dict] = []
            for p_el in tc.findall(f"{w_ns}p"):
                parsed = _parse_word_para(p_el, hrefs, w_ns, r_ns)
                if parsed and parsed.get("role") != "empty":
                    cell.append(parsed)
            row.append(cell)
        if any(row):
            rows.append(row)
    if not rows:
        return None
    return {"kind": "table", "rows": rows, "text": "", "runs": [], "bullet": False, "role": ""}


def _walk_word_blocks(el, hrefs: dict[str, str], w_ns: str, r_ns: str, out: list[dict]) -> None:
    if el.tag == f"{w_ns}tbl":
        table = _parse_word_table(el, hrefs, w_ns, r_ns)
        if table:
            out.append(table)
        return
    if el.tag == f"{w_ns}p":
        para = _parse_word_para(el, hrefs, w_ns, r_ns)
        if para:
            out.append(para)
        return
    for child in list(el):
        _walk_word_blocks(child, hrefs, w_ns, r_ns, out)


def load_word_paragraphs(docx_bytes: bytes) -> list[dict]:
    from xml.etree import ElementTree as ET

    w_ns = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
    r_ns = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}"
    blocks: list[dict] = []
    with zipfile.ZipFile(BytesIO(docx_bytes)) as zf:
        try:
            rels_root = ET.fromstring(zf.read("word/_rels/document.xml.rels"))
        except KeyError:
            hrefs = {}
        else:
            hrefs = {
                rel.get("Id"): rel.get("Target") or ""
                for rel in rels_root
                if "hyperlink" in (rel.get("Type") or "").lower()
            }
        root = ET.fromstring(zf.read("word/document.xml"))
        body = root.find(f"{w_ns}body")
        if body is not None:
            for child in list(body):
                _walk_word_blocks(child, hrefs, w_ns, r_ns, blocks)
    return blocks


def _is_leading_cover_line(text: str) -> bool:
    """Word cover chrome: country title, report line, appeal code — not a mismatch notice."""
    raw = (text or "").strip()
    if not raw:
        return False
    low = raw.lower()
    if _SKIP_COVER_RE.match(raw) or low in _SKIP_EXACT:
        return True
    if low in _BANDS or low in _MAJOR_H2 or low in _SUBHEADS:
        return False
    if (low.startswith("q") and len(raw) < 120) or low.startswith("annex"):
        return False
    if raw.endswith((".", "?", "!")) or len(raw) > 48:
        return False
    return True


def _is_cover_table(row: dict) -> bool:
    rows = row.get("rows") or []
    if len(rows) != 1 or len(rows[0]) != 1:
        return False
    text = " ".join((para.get("text") or "").strip() for para in (rows[0][0] or [])).strip()
    return _is_leading_cover_line(text)


def style_narrative_blocks(blocks: list[dict], *, country_name: str = "") -> list[dict]:
    styled: list[dict] = []
    state = ""
    country = (country_name or "").strip().lower()
    for row in blocks:
        if row.get("kind") == "table":
            if not styled and _is_cover_table(row):
                continue
            styled.append(row)
            continue
        if row.get("role") == "empty":
            if styled and styled[-1].get("style") != "Blank":
                styled.append({"style": "Blank", "text": "", "runs": [{"text": " ", "href": "", "bold": False}]})
            continue
        text = (row.get("text") or "").strip()
        if not styled and (_is_leading_cover_line(text) or (country and text.lower() == country)):
            continue
        if country and text.lower() == country:
            continue
        style, state = _narrative_style(
            text,
            state,
            row.get("role") or "",
            bullet=bool(row.get("bullet")),
            has_href=bool(_para_hrefs(row)),
            bold=_para_is_bold(row),
        )
        if not style:
            continue
        if style == "AdditionalHead":
            text = "ADDITIONAL INFORMATION"
            row = {"text": text, "runs": [{"text": text, "href": "", "bold": True}], "bullet": False}
        if style in {"QHeading", "BandHead"}:
            text = text.upper()
        styled.append(
            {
                "style": style,
                "text": text,
                "runs": row.get("runs") or [{"text": text, "href": "", "bold": False}],
            }
        )
    return styled


def folio_label(meta: dict) -> str:
    year = str((meta or {}).get("year") or "").strip()
    kind = str((meta or {}).get("kind") or "report")
    label = "unified plan" if kind == "plan" else "annual report"
    if year:
        return f"{year} IFRC network {label}"
    return f"IFRC network {label}"


# space_before, leading, space_after — same as paragraph styles in _styles_xml.
_FLOW_METRICS = {
    "QHeading": (4.0, 24.0, 12.0),
    "SectionHead": (16.0, 18.0, 6.0),
    "TopicHead": (12.0, 17.0, 6.0),
    "BandHead": (14.0, 20.0, 10.0),
    "Subhead": (10.0, 13.5, 6.0),
    "Body": (0.0, 13.5, 8.5),
    "AdditionalHead": (8.0, 12.0, 10.0),
    "SourceItem": (0.0, 13.0, 6.0),
    "ContactHead": (16.0, 13.0, 10.0),
    "ContactName": (10.0, 13.0, 1.0),
    "ContactDetail": (0.0, 13.0, 1.0),
    "Blank": (0.0, 12.0, 4.0),
}
# Open Sans 10pt on a 530pt measure is ~100 characters, not 85.
_BODY_CHARS_PER_LINE = 100


def _block_flow_height(para: dict) -> float:
    if para.get("kind") == "table":
        rows = para.get("rows") or []
        return 10.0 + sum(max((_table_cell_height(cell) for cell in row), default=16.0) for row in rows)
    style = para.get("style") or "Body"
    before, leading, after = _FLOW_METRICS.get(style, (0.0, 13.5, 8.5))
    text = para.get("text") or ""
    if style == "Body":
        lines = max(1, (len(text) + _BODY_CHARS_PER_LINE - 1) // _BODY_CHARS_PER_LINE)
    else:
        lines = max(1, (len(text) + 55) // 56)
    return before + leading * lines + after


def _narrative_page_count(styled: list[dict]) -> int:
    """Threaded frames for the story. Loose estimates left empty pages at the end."""
    total = sum(_block_flow_height(para) for para in styled)
    return max(1, int(total / NARRATIVE_H + 0.999))


def add_narrative_pages(doc: Idml, styled: list[dict], *, folio: str) -> int:
    if not styled:
        return 0

    story_id = doc.styled_story(styled)
    fids = [doc.uid() for _ in range(_narrative_page_count(styled))]
    for i, fid in enumerate(fids):
        prev = fids[i - 1] if i else "n"
        nxt = fids[i + 1] if i + 1 < len(fids) else "n"
        items = [
            doc.threaded_frame(NARRATIVE_X, NARRATIVE_Y, NARRATIVE_W, NARRATIVE_H, story_id, fid, previous=prev, nxt=nxt),
            doc.text_frame(
                NARRATIVE_X,
                FOLIO_Y,
                NARRATIVE_W,
                14.0,
                doc.story(
                    [
                        {
                            "text": f"{folio}    /    {doc.page_count + 1}",
                            "font": "Montserrat",
                            "style": "Regular",
                            "size": "8",
                            "color": "Color/Black",
                        }
                    ],
                    align="CenterAlign",
                ),
            ),
        ]
        doc.add_page(items)
    return len(styled)


def zip_indesign_package(idml_bytes: bytes, idml_name: str, links_dir: Path) -> bytes:
    out = BytesIO()
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr(idml_name, idml_bytes)
        if links_dir.is_dir():
            for path in sorted(links_dir.iterdir()):
                if path.is_file() and path.suffix.lower() in {".svg", ".png"}:
                    zf.write(path, arcname=f"Links/{path.name}")
    return out.getvalue()


def build_indesign_package(
    *,
    payload: dict,
    pdf_bytes: bytes,
    work_dir: Path,
    word_bytes: bytes | None = None,
) -> dict:
    import fitz
    from plugins.upr_visuals.data import filename_from_visual_title

    work_dir = Path(work_dir)
    links = work_dir / "Links"
    links.mkdir(parents=True, exist_ok=True)
    meta = payload.get("meta") or {}
    title = meta.get("document_title") or "UPR visuals"
    idml_name = filename_from_visual_title(title, "idml")

    pdf_doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    doc = Idml()
    try:
        visual_bands = build_native_pages(doc, pdf_doc, payload, links)
    finally:
        pdf_doc.close()

    styled: list[dict] = []
    if word_bytes:
        styled = style_narrative_blocks(
            load_word_paragraphs(word_bytes),
            country_name=str(meta.get("country_name") or ""),
        )
        add_narrative_pages(doc, styled, folio=folio_label(meta))

    idml_bytes = doc.package_bytes()
    (work_dir / idml_name).write_bytes(idml_bytes)
    return {
        "idml_bytes": idml_bytes,
        "idml_name": idml_name,
        "zip_bytes": zip_indesign_package(idml_bytes, idml_name, links),
        "pages": doc.page_count,
        "visual_bands": visual_bands,
        "narrative_paragraphs": len(styled),
        "title": title,
        "styled": styled,
    }
