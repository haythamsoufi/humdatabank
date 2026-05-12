"""Custom static file serving with cache headers."""

import os

CACHE_MAX_AGE_ONE_HOUR = 3600


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

        if response.status_code == 200 and not is_development:
            response.headers.pop('Cache-Control', None)
            response.headers.pop('Pragma', None)
            response.headers.pop('Expires', None)

            path_lower = filename.lower()
            static_extensions = ['.css', '.js', '.woff', '.woff2', '.ttf', '.eot', '.svg',
                                 '.png', '.jpg', '.jpeg', '.gif', '.ico', '.webmanifest']

            if any(path_lower.endswith(ext) for ext in static_extensions):
                query_string = req.query_string.decode('utf-8', errors='ignore')
                if 'v=' in query_string:
                    response.cache_control.max_age = 31536000  # 1 year
                    response.cache_control.public = True
                    response.cache_control.immutable = True
                else:
                    if path_lower.endswith(('.js', '.css')):
                        response.cache_control.max_age = 0
                        response.cache_control.public = True
                        response.cache_control.must_revalidate = True
                    else:
                        response.cache_control.max_age = CACHE_MAX_AGE_ONE_HOUR
                        response.cache_control.public = True
                        response.cache_control.must_revalidate = True
        elif response.status_code == 200 and is_development:
            response.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
            response.headers['Pragma'] = 'no-cache'
            response.headers['Expires'] = '0'

        response._skip_cache_override = True

        return response
