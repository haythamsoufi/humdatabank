"""
Embed content model for managing external iframe embeds (Power BI, etc.)
served to the public website.
"""
import re
from urllib.parse import urlparse

from sqlalchemy import Column, Integer, String, Text, DateTime, Boolean
from ..extensions import db
from app.utils.datetime_helpers import utcnow

POWERBI_EMBED_DOMAINS = (
    'app.powerbi.com',
    'app.powerbigov.us',
    'msit.powerbi.com',
)

TABLEAU_EMBED_DOMAINS = (
    'public.tableau.com',
)

ALLOWED_EMBED_SCHEMES = ('https',)

PAGE_SLOTS = {
    'echo_partnership': 'ECHO Programmatic Partnership',
    'grbm': 'Global Route-based Migration',
    'phsm': 'Professional Health Services Mapping',
}

# Slugs stored in embed_content.category; labels are in the admin template / i18n.
EMBED_CATEGORY_SLUGS = frozenset({
    'global_initiative',
    'analysis',
    'tableau_program',
    'partnerships',
    'other',
})


def _domains_for_embed_type(embed_type):
    et = (embed_type or 'powerbi').strip().lower()
    if et == 'powerbi':
        return POWERBI_EMBED_DOMAINS
    if et == 'tableau':
        return TABLEAU_EMBED_DOMAINS
    if et == 'iframe':
        return POWERBI_EMBED_DOMAINS + TABLEAU_EMBED_DOMAINS
    return ()


_HTTPS_URL_RE = re.compile(r'https://[^\s"\'<>]+')

# Match width/height from:
#   HTML attributes:  width="600"  height='373.5'
#   jQuery css():     .css('width', '1050px')  .css("height","900px")
#   Inline CSS:       width: 1050px;  height:900px
_DIM_PATTERNS = [
    re.compile(r'''(?:\.css\(\s*['"](?:WIDTH_OR_HEIGHT)['"]\s*,\s*['"](\d+(?:\.\d+)?)px['"]\s*\))''', re.IGNORECASE),
    re.compile(r'(?:WIDTH_OR_HEIGHT)\s*[:=]\s*["\']?(\d+(?:\.\d+)?)(?:px)?', re.IGNORECASE),
]

def _find_dimension(text, dim_name):
    """Extract a numeric dimension (width or height) from various formats."""
    for pattern_template in _DIM_PATTERNS:
        pat = re.compile(pattern_template.pattern.replace('WIDTH_OR_HEIGHT', dim_name), pattern_template.flags)
        m = pat.search(text)
        if m:
            return float(m.group(1))
    return None

KNOWN_RATIOS = [
    (16, 9),
    (16, 10),
    (4, 3),
    (3, 2),
    (21, 9),
    (1, 1),
]


def _snap_ratio(w, h):
    """Return a clean 'W:H' string.  If close to a well-known ratio, snap to it."""
    if w <= 0 or h <= 0:
        return None
    actual = w / h
    for rw, rh in KNOWN_RATIOS:
        if abs(actual - rw / rh) < 0.04:
            return f'{rw}:{rh}'
    return f'{round(w)}:{round(h)}'


def _extract_from_snippet(text, embed_type):
    """Extract the first matching HTTPS URL and width/height from an HTML snippet.

    Returns ``(url_or_None, aspect_ratio_or_None)``.
    """
    allowed = _domains_for_embed_type(embed_type)
    url = None
    if allowed:
        for match in _HTTPS_URL_RE.finditer(text):
            candidate = match.group(0).rstrip('/')
            try:
                p = urlparse(candidate)
            except Exception:
                continue
            h = (p.hostname or '').lower()
            if any(h == d or h.endswith('.' + d) for d in allowed):
                url = candidate
                break

    aspect_ratio = None
    w = _find_dimension(text, 'width')
    h = _find_dimension(text, 'height')
    if w and h:
        try:
            aspect_ratio = _snap_ratio(w, h)
        except (ValueError, ZeroDivisionError):
            pass
    return url, aspect_ratio


def validate_embed_url(url, embed_type='powerbi'):
    """Validate that an embed URL is HTTPS and on an allowlisted host.

    Accepts a plain URL **or** an HTML embed snippet (e.g. an ``<iframe>``
    tag or a Tableau ``<div>`` / ``<param>`` block).  The first matching
    HTTPS URL on an allowed domain is extracted automatically, and
    ``width`` / ``height`` attributes are converted to an aspect ratio.

    Returns ``(is_valid, url_or_error, aspect_ratio_or_None)``.
    """
    if not url or not isinstance(url, str):
        return False, "Embed URL is required", None
    url = url.strip()
    extracted_ratio = None

    if '<' in url:
        extracted_url, extracted_ratio = _extract_from_snippet(url, embed_type)
        if extracted_url:
            url = extracted_url
        else:
            allowed = _domains_for_embed_type(embed_type)
            allowed_txt = ', '.join(allowed) if allowed else '(none)'
            return False, (
                "Could not find an allowed URL in the pasted HTML snippet. "
                f"Paste just the URL, or an embed snippet containing an HTTPS "
                f"link to: {allowed_txt}"
            ), None

    if not url.lower().startswith(('https://', 'http://')):
        url = 'https://' + url
    try:
        parsed = urlparse(url)
    except Exception:
        return False, "Invalid URL format", None
    if parsed.scheme not in ALLOWED_EMBED_SCHEMES:
        return False, f"URL must use HTTPS (got {parsed.scheme!r})", None
    hostname = (parsed.hostname or '').lower()
    if not hostname:
        return False, "URL must include a hostname", None
    allowed = _domains_for_embed_type(embed_type)
    if not allowed:
        return False, "Invalid embed type", None
    if not any(hostname == d or hostname.endswith('.' + d) for d in allowed):
        allowed_txt = ', '.join(allowed)
        return False, f"Domain {hostname!r} is not allowed for this embed type ({allowed_txt})", None
    return True, url, extracted_ratio


_ASPECT_RATIO_RE = re.compile(r'^\d{1,5}:\d{1,5}$')


def validate_aspect_ratio(value):
    """Return a cleaned aspect-ratio string ('W:H') or None."""
    if not value or not isinstance(value, str):
        return None
    value = value.strip()
    if not value:
        return None
    if _ASPECT_RATIO_RE.match(value):
        return value
    return None


def validate_embed_category(category):
    """Return (is_valid, normalized_slug_or_None, error_message)."""
    if not category or not isinstance(category, str):
        return False, None, "Category is required"
    slug = category.strip().lower()[:100]
    if slug not in EMBED_CATEGORY_SLUGS:
        return False, None, "Invalid category"
    return True, slug, None


class EmbedContent(db.Model):
    __tablename__ = 'embed_content'

    id = Column(Integer, primary_key=True)
    title = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    category = Column(String(100), nullable=False, default='global_initiative')
    embed_url = Column(Text, nullable=False)
    embed_type = Column(String(50), nullable=False, default='powerbi')
    aspect_ratio = Column(String(20), nullable=True)
    page_slot = Column(String(50), nullable=True)
    is_active = Column(Boolean, nullable=False, default=True)
    sort_order = Column(Integer, nullable=False, default=0)
    created_at = Column(DateTime, default=utcnow)
    updated_at = Column(DateTime, default=utcnow, onupdate=utcnow)

    __table_args__ = (
        db.Index('ix_embed_content_category', 'category'),
        db.Index('ix_embed_content_active', 'is_active'),
        db.Index('ix_embed_content_sort', 'sort_order'),
    )

    def __repr__(self):
        return f'<EmbedContent {self.title} ({self.category})>'

    def to_dict(self):
        return {
            'id': self.id,
            'title': self.title,
            'description': self.description,
            'category': self.category,
            'embed_url': self.embed_url,
            'embed_type': self.embed_type,
            'aspect_ratio': self.aspect_ratio,
            'page_slot': self.page_slot,
            'is_active': self.is_active,
            'sort_order': self.sort_order,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None,
        }
