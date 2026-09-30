# Security headers middleware for Flask
import os
import re
from urllib.parse import urlparse

from flask import current_app, request

from app.models.embed_content import POWERBI_EMBED_DOMAINS, TABLEAU_EMBED_DOMAINS

_STRICT_MODES = {"off", "report-only", "enforce"}

# Origins the app is known to load from (see templates/static JS). Path-scoped entries are used by the
# strict candidate policy so a whole public CDN (any npm/GitHub package) is not trusted for scripts.
_STRICT_SCRIPT_SOURCES = (
    "https://unpkg.com/swagger-ui-dist@5.9.0/",
    "https://unpkg.com/html2canvas@1.4.1/dist/",
    "https://cdn.jsdelivr.net/npm/html2canvas@1.4.1/dist/",
    "https://cdnjs.cloudflare.com/ajax/libs/html2canvas/1.4.1/",
    "https://www.gstatic.com/charts/",
)
_STRICT_IMG_SOURCES = (
    "https://api.mapbox.com",
    "https://tile.openstreetmap.org",
    "https://*.tile.openstreetmap.org",
    "https://www.gstatic.com",
)
_EXTRA_SOURCE_RE = re.compile(r"^(https://[A-Za-z0-9*.-]+(:\d+)?(/[A-Za-z0-9._~/@-]*)?|blob:|data:)$")

_PERMISSIONS_POLICY = (
    "geolocation=(self), "
    "microphone=(), "
    "camera=(), "
    "payment=(), "
    "usb=(), "
    "magnetometer=(), "
    "gyroscope=(), "
    "accelerometer=(), "
    "display-capture=(), "
    "midi=(), "
    "serial=(), "
    "hid=(), "
    "browsing-topics=(), "
    "fullscreen=(self), "
    "sync-xhr=()"
)


def _config_value(name):
    value = current_app.config.get(name)
    if value is None or value == "":
        value = os.environ.get(name, "")
    return str(value).strip()


def _csp_strict_mode():
    mode = _config_value("CSP_STRICT_MODE").lower()
    return mode if mode in _STRICT_MODES else "off"


def _csp_extra_sources(name):
    """Space/comma separated extra CSP sources from env/config; anything that is not an https origin is dropped."""
    raw = _config_value(name)
    tokens = [t for t in re.split(r"[\s,]+", raw) if t]
    return [t for t in tokens if _EXTRA_SOURCE_RE.match(t)]


def _apply_baseline_headers(response):
    """Headers that do not depend on the CSP variant (shared by the default and plugin-override paths)."""
    response.headers['X-Content-Type-Options'] = 'nosniff'
    response.headers['Referrer-Policy'] = 'strict-origin-when-cross-origin'
    response.headers['Permissions-Policy'] = _PERMISSIONS_POLICY
    response.headers['X-Permitted-Cross-Domain-Policies'] = 'none'
    # Keeps window.opener for popups this page opens (OAuth/print/map helpers) while isolating it from
    # cross-origin pages that open us.
    response.headers['Cross-Origin-Opener-Policy'] = 'same-origin-allow-popups'
    if request.is_secure:
        response.headers['Strict-Transport-Security'] = 'max-age=31536000; includeSubDomains; preload'
    response.headers.pop('Server', None)
    response.headers['X-App-Origin'] = '1'
    # Only HTML documents: static assets and JSON APIs are deliberately readable cross-origin
    # (Website, mobile web views, CDN) and are governed by CORS instead.
    if response.mimetype == 'text/html' and not request.path.startswith('/static/'):
        response.headers['Cross-Origin-Resource-Policy'] = 'same-origin'
    return response


def add_security_headers(response):
    """Add comprehensive security headers to all responses.

    Note: Static files have their own cache headers set by the custom static route.
    This function preserves those cache headers and doesn't override them.
    """
    # Skip cache header modification for static files that have custom cache headers
    # Static files are handled by the custom route in app/__init__.py
    if hasattr(response, '_skip_cache_override') and response._skip_cache_override:
        # Don't modify cache headers for static files
        pass
    elif request.endpoint == 'static' or request.path.startswith('/static/'):
        # Don't modify cache headers for static files
        pass
    else:
        # For non-static files, ensure no-cache if not already set
        # This prevents caching of dynamic content
        if 'Cache-Control' not in response.headers:
            response.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'

    # Quarto-generated HTML reports (extension output) are self-contained files with inline
    # scripts, data: script blobs, and data: stylesheets — incompatible with the app CSP.
    # They are served at authenticated routes so a report-specific relaxed policy is safe.
    endpoint = getattr(request, 'endpoint', None)
    csp_override = None
    try:
        plugin_manager = getattr(current_app, 'plugin_manager', None)
        if plugin_manager is not None:
            csp_override = plugin_manager.get_csp_override(endpoint, request.path)
    except Exception as e:
        current_app.logger.debug("Extension CSP override lookup failed: %s", e)

    if csp_override is not None:
        response.headers['X-Frame-Options'] = 'SAMEORIGIN'
        _apply_baseline_headers(response)
        response.headers['Content-Security-Policy'] = csp_override.policy
        return response

    # Prevent clickjacking
    response.headers['X-Frame-Options'] = 'DENY'

    # Legacy XSS auditors introduced their own vulnerabilities; CSP is the control, so disable them.
    response.headers['X-XSS-Protection'] = '0'

    _apply_baseline_headers(response)

    from app.utils.csp_nonce import get_csp_nonce
    try:
        csp_nonce = get_csp_nonce()
        nonce_directive = f"'nonce-{csp_nonce}'"
    except Exception as e:
        current_app.logger.debug("CSP nonce generation failed: %s", e)
        nonce_directive = ""

    strict_mode = _csp_strict_mode()
    # Responses serving user uploads set their own lockdown CSP (storage_service.harden_upload_response).
    if 'Content-Security-Policy' not in response.headers:
        response.headers['Content-Security-Policy'] = build_csp_policy(nonce_directive, strict=strict_mode == 'enforce')
    if strict_mode == 'report-only':
        response.headers['Content-Security-Policy-Report-Only'] = build_csp_policy(nonce_directive, strict=True)

    return response


def build_csp_policy(nonce_directive, *, strict):
    """
    Build the page Content-Security-Policy.

    ``strict=False`` is the enforced default: nonce-based scripts, broad-but-enumerated CDN hosts and
    ``img-src https:`` (admin-authored content and map tiles may reference arbitrary HTTPS images).
    ``strict=True`` is the candidate policy (``CSP_STRICT_MODE=report-only|enforce``): path-scoped script
    CDNs, no ``code.jquery.com`` (unused) and an enumerated ``img-src`` instead of ``https:``.
    ``style-src 'unsafe-inline'`` stays in both because libraries and templates still set inline styles
    (some ``<style>`` tags carry no nonce and several libraries create ``<style>`` elements at runtime).
    """
    # CSP hashes added for external library inline scripts that can't use nonces
    # (generated by jQuery, Select2, Chart.js, etc.). When a nonce is present browsers ignore 'unsafe-inline'.
    script_hashes = (
        "'sha256-F2OZJCLKXjn5GkgDK82TQCGt3VAD7pAvv2GegMmBmmA=' "  # External library inline script 1
        "'sha256-C0POBvuIg2WsFkKXuy5NW4X27PXkxKrkaQL0AjxA/B8=' "  # External library inline script 2
        "'sha256-eRf/6o7h063u1aRHq9JazzrFoegwHCJN/dFqqZg7oF0=' "  # External library inline script 3
        "'sha256-4go2tWGJE+CNuqNpl48Yv+bO4uu+BQJh1MJF3yTjhl8=' "  # External library inline script 4
        "'sha256-Y/4W14eTM3Az3L4dOeJ6tK2FFZ+wZxp7ssM38MBKM2g=' "  # External library inline script 5
        "'sha256-dt/ya86/s8LgFk2v8XZkKpeGcfwvFHR3ivK+gBEVm64=' "  # External library inline script 6
        "'sha256-9plDW+xe6iwb+kc2Ab2H1JEg2Z7f2/5tGt6Ovl5ojFE=' "  # Plugin settings inline script 1
        "'sha256-ewJJ2tQuYLmjU/myxACs+VuEoGqmyJwcCEYdr+AuMac=' "  # Plugin settings inline script 2
        "'sha256-iNLi1rYoOeNI8CEXwy6NnxglbQ3BjdJZbgZHvuY89wA=' "  # Plugin settings inline script 3
        "'sha256-xG5vOuTJfko1kfw3c6cQOiOXhaZxr2Yhc5uF1ybVo+c=' "  # Plugin settings inline script 4
        "'sha256-ofVqu4ZzAuGbayuRZeenPtqaKeG7wyBnn5XRT9+Pyew='"   # Plugin settings inline script 5
    )
    # Allow ES module scripts/styles from the static CDN (Azure Blob / CDN) when configured.
    static_cdn = (current_app.config.get('STATIC_CDN_URL') or '').strip().rstrip('/')
    cdn_origin = ''
    if static_cdn:
        parsed = urlparse(static_cdn)
        if parsed.scheme and parsed.netloc:
            cdn_origin = f"{parsed.scheme}://{parsed.netloc}"

    if strict:
        external_scripts = " ".join(_STRICT_SCRIPT_SOURCES)
    else:
        external_scripts = (
            "https://cdnjs.cloudflare.com https://code.jquery.com https://cdn.jsdelivr.net "
            "https://unpkg.com https://www.gstatic.com"
        )
    script_src = f"'self' {nonce_directive} {script_hashes} {cdn_origin} {external_scripts}".strip()
    style_src = f"'self' 'unsafe-inline' {cdn_origin} https://cdnjs.cloudflare.com https://cdn.jsdelivr.net https://fonts.googleapis.com https://unpkg.com https://www.gstatic.com".strip()

    # Iframe embeds (Power BI, Tableau Public) - keep in sync with embed_content allowlists
    _frame_hosts = " ".join(
        f"https://{d}" for d in (*POWERBI_EMBED_DOMAINS, *TABLEAU_EMBED_DOMAINS)
    )
    frame_src = f"'self' {_frame_hosts}".strip()

    extra_img = " ".join(_csp_extra_sources("CSP_IMG_SRC_EXTRA"))
    if strict:
        img_src = f"'self' data: blob: {cdn_origin} {' '.join(_STRICT_IMG_SOURCES)} {extra_img}"
    else:
        img_src = f"'self' data: blob: https: {extra_img}"
    extra_connect = " ".join(_csp_extra_sources("CSP_CONNECT_SRC_EXTRA"))
    connect_src = (
        f"'self' {cdn_origin} https://unpkg.com https://www.gstatic.com https://cdn.jsdelivr.net "
        f"https://cdnjs.cloudflare.com https://nominatim.openstreetmap.org https://ipapi.co "
        f"https://api.mapbox.com {extra_connect}"
    )

    directives = [
        "default-src 'self'",
        f"script-src {script_src}",
        f"style-src {style_src}",
        f"img-src {img_src}",
        f"font-src 'self' data: {cdn_origin} https://cdnjs.cloudflare.com https://fonts.gstatic.com",
        f"connect-src {connect_src}",
        f"frame-src {frame_src}",
        "object-src 'none'",
        "frame-ancestors 'none'",
        "base-uri 'self'",
        "form-action 'self'",
    ]
    if request.is_secure:
        directives.append("upgrade-insecure-requests")
    return "; ".join(" ".join(d.split()) for d in directives)


def init_security_headers(app):
    """Initialize security headers middleware."""
    app.after_request(add_security_headers)
