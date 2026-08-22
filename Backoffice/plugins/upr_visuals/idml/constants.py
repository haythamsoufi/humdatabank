"""Shared measurements, brand colors, and narrative style runs for IDML export."""

from __future__ import annotations

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
_NO_CHAR_STYLE = 'AppliedCharacterStyle="CharacterStyle/$ID/[No character style]"'
_HYPERLINK_UNDERLINE_ATTRS = (
    ' Underline="true" UnderlineColor="Color/QRed" '
    'UnderlineOffset="1" UnderlineWeight="0.75"'
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

_COVER_LAYOUT = {
    "rule_x": 111.0,
    "rule_y": 64.6,
    "rule_w": 314.6,
    "rule_h": 5.2,
    "title_x": 111.0,
    "title_y": 22.0,
    "title_w": 370.0,
    "title_h": 46.0,
    "subtitle_y": 74.5,
    "subtitle_h": 18.0,
    "date_w": 130.0,
    "date_h": 14.0,
    "date_y_no_logo": 93.5,
    "pad_x": 22.7,
    "box_y": 788.0,
    "appeal_w": 138.0,
    "appeal_h": 15.5,
    "note_w": 268.0,
    "note_h": 15.5,
    "org_y": 814.0,
    "org_h": 12.0,
}

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
