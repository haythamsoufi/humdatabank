"""Custom static file serving with cache headers.

Production note
---------------
When STATIC_CDN_URL is configured (Azure Blob Storage / CDN), static files are
served directly from the CDN — this Flask route is never called for those assets.
The route is kept for local development and as a safe fallback.

Cache strategy
--------------
All static files emitted by static_url() include a ?v=<ASSET_VERSION> cache-buster.
  • Versioned (?v=…)   → max-age=31536000, immutable (browser never re-validates)
  • Unversioned JS/CSS → max-age=0 + must-revalidate  (re-check on every load)
  • Unversioned other  → max-age=3600                 (1-hour heuristic)

The Cache-Control header is set as a raw string to avoid any Werkzeug cache_control
API quirks that can silently drop directives.  The header is also set unconditionally
after stripping any header the WSGI server might have pre-set, so middleware cannot
downgrade it.
"""

import os

_IMMUTABLE = 'max-age=31536000, public, immutable'
_REVALIDATE = 'max-age=0, public, must-revalidate'
_ONE_HOUR = 'max-age=3600, public, must-revalidate'

_CACHEABLE_EXTS = frozenset([
    '.css', '.js', '.woff', '.woff2', '.ttf', '.eot', '.svg',
    '.png', '.jpg', '.jpeg', '.gif', '.ico', '.webmanifest',
])


def register_static_route(app, static_folder_path):
    """Register the custom static file serving route with cache headers."""

    @app.route('/static/<path:filename>', endpoint='static')
    def send_static_file_with_cache(filename):
        from flask import request as req
        from flask import send_from_directory, current_app, abort

        file_path = os.path.join(static_folder_path, filename)
        if not os.path.exists(file_path) or not os.path.isfile(file_path):
            abort(404)

        response = send_from_directory(static_folder_path, filename)

        is_development = current_app.config.get('DEBUG', False)

        if response.status_code != 200:
            response._skip_cache_override = True
            return response

        # Always clear whatever the WSGI server may have set so our value wins.
        for hdr in ('Cache-Control', 'Pragma', 'Expires'):
            response.headers.remove(hdr)

        path_lower = filename.lower()

        if is_development:
            # No caching in dev so code changes are immediately visible.
            response.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
            response.headers['Pragma'] = 'no-cache'
            response.headers['Expires'] = '0'
        elif any(path_lower.endswith(ext) for ext in _CACHEABLE_EXTS):
            query_string = req.query_string.decode('utf-8', errors='ignore')
            if 'v=' in query_string:
                # Content-addressed: safe to cache forever in the browser.
                response.headers['Cache-Control'] = _IMMUTABLE
            elif path_lower.endswith(('.js', '.css')):
                response.headers['Cache-Control'] = _REVALIDATE
            else:
                response.headers['Cache-Control'] = _ONE_HOUR

            # Required so proxies/CDNs keep separate cached copies per encoding
            # (important when Flask-Compress returns Brotli to some clients).
            response.headers['Vary'] = 'Accept-Encoding'
        else:
            response.headers['Cache-Control'] = _ONE_HOUR

        # Signal to add_security_headers that it must not touch Cache-Control.
        response._skip_cache_override = True

        return response
