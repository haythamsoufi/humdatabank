"""IDML document object: stories, frames, package zip."""

from __future__ import annotations

import zipfile
from io import BytesIO
from xml.sax.saxutils import escape

from plugins.upr_visuals.idml.word_reader import safe_export_href
from plugins.upr_visuals.idml.constants import (
    A4_H,
    A4_W,
    COLORS,
    NARRATIVE_W,
    _HYPERLINK_UNDERLINE_ATTRS,
    _LAYER_ID,
    _MASTER_ID,
    _MASTER_PAGE_ID,
    _NO_CHAR_STYLE,
    _NO_FILL,
    _PAGE_TY,
    _SPREAD_GAP,
    _STYLE_RUNS,
)


def _item_transform(x: float, y: float) -> str:
    return f"1 0 0 1 {x:.6f} {_PAGE_TY + y:.6f}"


def _xml_text(value: str) -> str:
    return "".join(ch for ch in (value or "") if ch == "\t" or ch == "\n" or ord(ch) >= 32)


def _applied_font_xml(font: str) -> str:
    return f"<Properties><AppliedFont type='string'>{escape(_xml_text(font))}</AppliedFont></Properties>"


def _corner_xml(radius: float) -> str:
    if not radius:
        return ""
    return (
        ' TopLeftCornerOption="RoundedCorner" TopRightCornerOption="RoundedCorner" '
        'BottomLeftCornerOption="RoundedCorner" BottomRightCornerOption="RoundedCorner" '
        f'TopLeftCornerRadius="{radius:.2f}" TopRightCornerRadius="{radius:.2f}" '
        f'BottomLeftCornerRadius="{radius:.2f}" BottomRightCornerRadius="{radius:.2f}"'
    )


def _table_cell_height(paras: list[dict]) -> float:
    if not paras:
        return 16.0
    lines = 0
    for para in paras:
        text = (para.get("text") or "").strip()
        lines += max(1, (len(text) + 48) // 49)
    return max(16.0, 12.0 * lines + 6.0)


def _rtl_font(font: str, *, arabic_font: bool) -> str:
    """Tajawal for Arabic-script stories. Visual KPI digits stay in the raster PNG."""
    from plugins.upr_visuals.typography import ARABIC_FAMILY

    if not arabic_font:
        return font
    return ARABIC_FAMILY


def _flip_align(align: str, *, rtl: bool) -> str:
    if not rtl:
        return align
    mapping = {
        "LeftAlign": "RightAlign",
        "RightAlign": "LeftAlign",
        "LeftJustified": "RightJustified",
        "RightJustified": "LeftJustified",
    }
    return mapping.get(align, align)


class Idml:
    def __init__(self, *, rtl: bool = False, arabic_font: bool | None = None) -> None:
        self._n = 0x1000
        self.rtl = bool(rtl)
        self.arabic_font = False if arabic_font is None else bool(arabic_font)
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
            font = _rtl_font(run.get("font", "Arial"), arabic_font=self.arabic_font)
            style = run.get("style", "Regular")
            size = run.get("size", "11")
            color = run.get("color", "Color/Black")
            text = run.get("text", "")
            content = escape(_xml_text(text)).replace("\n", "</Content><Br/><Content>")
            ranges.append(
                "<CharacterStyleRange "
                f'{_NO_CHAR_STYLE} '
                f'FillColor="{color}" PointSize="{size}" FontStyle="{style}">'
                f"{_applied_font_xml(font)}"
                f"<Content>{content}</Content></CharacterStyleRange>"
            )
        body = (
            f'<Story Self="{sid}" AppliedTOCStyle="n" TrackChanges="false" StoryTitle="$ID/">'
            '<StoryPreference OpticalMarginAlignment="false" OpticalMarginSize="12" '
            'FrameType="TextFrameType"/>'
            f'<ParagraphStyleRange AppliedParagraphStyle="ParagraphStyle/$ID/NormalParagraphStyle" '
            f'Justification="{_flip_align(align, rtl=self.rtl)}">'
            f"{''.join(ranges)}</ParagraphStyleRange></Story>"
        )
        self.stories[sid] = body
        return sid

    def _hyperlink_source(self, url: str, inner_xml: str) -> str:
        url = safe_export_href(url)
        if not url:
            return inner_xml
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
                href = safe_export_href(run.get("href"))
                font_style = "Bold" if run.get("bold") and style_name != "AdditionalHead" else base["style"]
                if style_name == "ContactName":
                    font_style = "Bold"
                color = base["color"]
                extra = ""
                inner = f"<Content>{escape(_xml_text(text)).replace(chr(10), ' ')}</Content>"
                if href:
                    inner = self._hyperlink_source(href, inner)
                    color = "Color/QRed"
                    extra = _HYPERLINK_UNDERLINE_ATTRS
                parts.append(
                    "<CharacterStyleRange "
                    f'{_NO_CHAR_STYLE} '
                    f'FillColor="{color}" PointSize="{base["size"]}" FontStyle="{font_style}"{extra}>'
                    f"{_applied_font_xml(_rtl_font(base['font'], arabic_font=self.arabic_font))}"
                    f"{inner}</CharacterStyleRange>"
                )
            if not parts:
                parts.append(
                    "<CharacterStyleRange "
                    f'{_NO_CHAR_STYLE} '
                    f'FillColor="{base["color"]}" PointSize="{base["size"]}" FontStyle="{base["style"]}">'
                    f"{_applied_font_xml(_rtl_font(base['font'], arabic_font=self.arabic_font))}"
                    "<Content> </Content></CharacterStyleRange>"
                )
            parts.append(
                "<CharacterStyleRange "
                f'{_NO_CHAR_STYLE}>'
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
            f'TableDirection="{"RightToLeftDirection" if self.rtl else "LeftToRightDirection"}">'
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
                href = safe_export_href(run.get("href"))
                style = "Bold" if force_bold or run.get("bold") else font_style
                color = "Color/QRed" if href and not force_bold else text_color
                inner = f"<Content>{escape(_xml_text(text)).replace(chr(10), ' ')}</Content>"
                extra = ""
                if href:
                    inner = self._hyperlink_source(href, inner)
                    extra = _HYPERLINK_UNDERLINE_ATTRS
                    if not force_bold:
                        color = "Color/QRed"
                parts.append(
                    "<CharacterStyleRange "
                    f'{_NO_CHAR_STYLE} '
                    f'FillColor="{color}" PointSize="9" FontStyle="{style}"{extra}>'
                    f"{_applied_font_xml(_rtl_font('Open Sans', arabic_font=self.arabic_font))}"
                    f"{inner}</CharacterStyleRange>"
                )
            if not parts:
                parts.append(
                    f'<CharacterStyleRange {_NO_CHAR_STYLE}>'
                    "<Content> </Content></CharacterStyleRange>"
                )
            chunks.append(
                f'<ParagraphStyleRange AppliedParagraphStyle="ParagraphStyle/Body" '
                f'Justification="{_flip_align("LeftAlign", rtl=self.rtl)}" SpaceBefore="0" SpaceAfter="2">'
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
        fill_attr = (
            f'FillColor="{fill}" StrokeColor="{stroke}" StrokeWeight="{weight}" '
            f'FillTint="-1" StrokeTint="-1" '
            f'AppliedObjectStyle="{"ObjectStyle/NoFill" if fill == "Swatch/None" else "ObjectStyle/Filled"}"'
        )
        return (
            f'<TextFrame Self="{fid}" ParentStory="{story_id}" NextTextFrame="n" PreviousTextFrame="n" '
            f'ContentType="TextType" ItemTransform="{_item_transform(x, y)}" '
            f'ItemLayer="{_LAYER_ID}" Visible="true" {fill_attr}{_corner_xml(radius)} Locked="false">'
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
        return (
            f'<Rectangle Self="{rid}" ContentType="Unassigned" '
            f'ItemTransform="{_item_transform(x, y)}" ItemLayer="{_LAYER_ID}" Visible="true" '
            f'FillColor="{fill}" StrokeColor="{stroke}" StrokeWeight="{weight}"{_corner_xml(radius)} '
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
            "Resources/Styles.xml": _styles_xml(rtl=self.rtl, arabic_font=self.arabic_font),
            "Resources/Preferences.xml": (
                '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
                '<idPkg:Preferences xmlns:idPkg="http://ns.adobe.com/AdobeInDesign/idml/1.0/packaging" DOMVersion="16.0">'
                f'<DocumentPreference PageHeight="{A4_H}" PageWidth="{A4_W}" PageOrientation="Portrait" '
                'FacingPages="false" PagesPerDocument="1" ColumnCount="1" ColumnGutter="12" '
                f'PageBinding="{"RightToLeft" if self.rtl else "LeftToRight"}" Intent="PrintIntent"/>'
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
        "</FontFamily>"
        '<FontFamily Self="ffTajawal" Name="Tajawal">'
        '<Font Self="fTajReg" FontFamily="Tajawal" Name="Tajawal Regular" FullName="Tajawal Regular" '
        'FontStyleName="Regular" FontType="TrueType" WritingScript="1" PostScriptName="Tajawal-Regular"/>'
        '<Font Self="fTajBold" FontFamily="Tajawal" Name="Tajawal Bold" FullName="Tajawal Bold" '
        'FontStyleName="Bold" FontType="TrueType" WritingScript="1" PostScriptName="Tajawal-Bold"/>'
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


def _styles_xml(*, rtl: bool = False, arabic_font: bool = False) -> str:
    band = ' RuleBelow="true" RuleBelowLineWeight="2" RuleBelowColor="Color/BannerNavy" RuleBelowOffset="3"'
    start = "RightAlign" if rtl else "LeftAlign"
    justified = "RightJustified" if rtl else "LeftJustified"
    from plugins.upr_visuals.typography import idml_applied_font

    heading = idml_applied_font(arabic_font=arabic_font, heading=True)
    body = idml_applied_font(arabic_font=arabic_font, heading=False)
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<idPkg:Styles xmlns:idPkg="http://ns.adobe.com/AdobeInDesign/idml/1.0/packaging" DOMVersion="16.0">'
        '<RootCharacterStyleGroup Self="uCharacterStyleGroup">'
        '<CharacterStyle Self="CharacterStyle/$ID/[No character style]" Name="$ID/[No character style]"/>'
        "</RootCharacterStyleGroup>"
        '<RootParagraphStyleGroup Self="uParagraphStyleGroup">'
        '<ParagraphStyle Self="ParagraphStyle/$ID/NormalParagraphStyle" Name="$ID/NormalParagraphStyle"/>'
        + _para_style("QHeading", "Q Heading", size="20", style="Bold", color="Color/QRed", font=heading, leading="24", space_before="4", space_after="12", align=start)
        + _para_style("SectionHead", "Section heading", size="15", style="Bold", color="Color/IFRCNavy", font=heading, leading="18", space_before="16", space_after="6", align=start)
        + _para_style("TopicHead", "Topic heading", size="14", style="Bold", color="Color/BannerNavy", font=heading, leading="17", space_before="12", space_after="6", align=start)
        + _para_style("BandHead", "Band heading", size="16", style="Bold", color="Color/BannerNavy", font=heading, leading="20", space_before="14", space_after="10", extra=band, align=start)
        + _para_style("Subhead", "Subhead", size="10", style="Bold", color="Color/Black", font=body, leading="13.5", space_before="10", space_after="6", align=start)
        + _para_style(
            "Body",
            "Body",
            size="10",
            style="Regular",
            color="Color/Black",
            font=body,
            leading="13.5",
            space_before="0",
            space_after="8.5",
            align=justified,
        )
        + _para_style("AdditionalHead", "Additional information", size="9.5", style="Bold", color="Color/Black", font=heading, leading="12", space_before="8", space_after="10", align=start)
        + _para_style("SourceItem", "Source item", size="9.5", style="Regular", color="Color/Black", font=body, leading="13", space_before="0", space_after="6", align=start)
        + _para_style("ContactHead", "Contact heading", size="10", style="Bold", color="Color/QRed", font=body, leading="13", space_before="16", space_after="10", align=start)
        + _para_style("ContactName", "Contact name", size="9.5", style="Bold", color="Color/Black", font=body, leading="13", space_before="10", space_after="1", align=start)
        + _para_style("ContactDetail", "Contact detail", size="9.5", style="Regular", color="Color/Black", font=body, leading="13", space_before="0", space_after="1", align=start)
        + _para_style("Blank", "Blank line", size="10", style="Regular", color="Color/Black", font=body, leading="12", space_before="0", space_after="4", align=start)
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
