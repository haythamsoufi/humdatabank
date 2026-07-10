import os
import logging

# IMPORTANT: gevent monkey-patching must happen BEFORE importing the app (and any
# libraries that import `ssl` / networking modules like `urllib3` / `jwt`).
# Otherwise gevent will warn and can misbehave in edge cases.
#
# In this repo, gevent is kept as an *opt-in* server for debugging WebSockets on
# Windows (the Flask dev server and Waitress are not suitable for HTTP Upgrade).
# Production deployments should use Gunicorn (see entrypoint/Docker/Azure config).
def _should_use_gevent() -> bool:
    """Return True if this process should run using gevent."""
    # Explicit opt-in (env: true/false only)
    if str(os.environ.get("USE_GEVENT_DEV", "false")).strip().lower() == "true":
        return True
    if str(os.environ.get("USE_GEVENT", "false")).strip().lower() == "true":
        return True

    # Default: do NOT auto-enable gevent. Flask dev server should be the normal
    # development experience; gevent is only for explicit WS debugging sessions.
    return False


def _running_from_flask_cli() -> bool:
    """
    True when the process is started via `flask run` / Flask CLI.

    Why this matters:
    - Flask-Sock (via simple-websocket) uses a background *thread* for socket recv().
    - If we gevent-monkeypatch sockets in this process, that thread can crash with:
      `greenlet.error: Cannot switch to a different thread`.
    - Therefore, only apply gevent monkey-patching when we are actually going to run
      the gevent server (e.g., `python run.py`), not when Werkzeug will own the server.
    """
    return str(os.environ.get("FLASK_RUN_FROM_CLI", "")).strip().lower() == "true"


if _should_use_gevent() and not _running_from_flask_cli():
    try:
        from gevent import monkey

        # IMPORTANT:
        # Flask-Sock uses `simple-websocket`, which performs socket recv in a background
        # *thread* on some servers. If we monkey-patch stdlib sockets here, that thread
        # may call into gevent's hub and crash with:
        #   greenlet.error: Cannot switch to a different thread
        #
        # In this project we primarily use gevent as a WS-capable dev server on Windows.
        # The gevent server itself does not require stdlib socket monkey-patching to run.
        # So we intentionally do NOT patch socket/ssl/thread.
        monkey.patch_all(socket=False, ssl=False, thread=False)
    except Exception as e:
        logging.getLogger(__name__).debug("gevent monkey-patch failed: %s", e)
        # If gevent isn't available (or patching fails), continue unpatched.
        # The server-startup logic will fall back to non-gevent servers.
        pass
elif _should_use_gevent() and _running_from_flask_cli():
    # Avoid crashing WebSocket threads under Werkzeug/simple-websocket.
    logging.getLogger(__name__).warning(
        "USE_GEVENT* is enabled but you're running via Flask CLI (Werkzeug). "
        "Skipping gevent monkey-patching to avoid `greenlet.error: Cannot switch to a different thread`. "
        "If you need WebSockets on Windows, start the dev server with `python run.py` "
        "(and ensure `gevent-websocket` is installed)."
    )

from app import create_app

# Create the Flask app instance
# Use FLASK_CONFIG from environment (loaded via config) to select config;
# falls back to 'default' (DevelopmentConfig) inside create_app when unset
#
# Gettext catalogs: configure_babel() runs inside create_app *before* babel.init_app and
# points Babel at Backoffice/translations (absolute path). Docker/Azure may symlink
# /app/translations to a persistent share via entrypoint.sh; override locally with
# BACKOFFICE_TRANSLATIONS_DIR if needed.
app = create_app(os.getenv('FLASK_CONFIG'))

# Logging configuration is now handled centrally in app/__init__.py
# Custom Flask CLI commands are registered in app/cli.py via create_app.


if __name__ == '__main__':
    def _find_available_port(host: str, start_port: int, max_tries: int = 20) -> int:
        """
        Find an available TCP port by attempting to bind.

        This avoids WinError 10013/10048 cases on Windows where some ports (notably 5000)
        may be excluded/reserved by the OS or another process.
        """
        try:
            import socket
        except Exception as e:
            logging.getLogger(__name__).debug("socket import failed: %s", e)
            return start_port

        for p in range(int(start_port), int(start_port) + int(max_tries)):
            try:
                s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                try:
                    s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                except Exception as e:
                    logging.getLogger(__name__).debug("setsockopt SO_REUSEADDR failed: %s", e)
                s.bind((host, p))
                return p
            except OSError:
                continue
            finally:
                try:
                    s.close()
                except Exception as e:
                    logging.getLogger(__name__).debug("socket close failed: %s", e)
        return start_port

    def _parse_bool_env(value: str | None, default: bool = False) -> bool:
        """Parse env as boolean. Only 'true' and 'false' accepted (case-insensitive)."""
        if value is None or str(value).strip() == "":
            return default
        normalized = value.strip().lower()
        if normalized == "true":
            return True
        if normalized == "false":
            return False
        return default

    # Prefer Flask CLI for development:
    #   python -m flask --app run --debug run
    # This __main__ block remains as a convenient fallback (`python run.py`).
    host = os.environ.get("FLASK_RUN_HOST") or "127.0.0.1"
    port_env = os.environ.get("PORT") or os.environ.get("FLASK_RUN_PORT")
    default_port = 5000
    port = int(port_env) if port_env else int(default_port)

    if not port_env:
        port = _find_available_port(host, port)

    debug_env = os.environ.get("FLASK_DEBUG")
    if debug_env is not None:
        debug = _parse_bool_env(debug_env, default=False)
    else:
        # Only enable debug when FLASK_CONFIG is *explicitly* set to a development
        # value. An absent or empty FLASK_CONFIG must NOT silently enable the
        # Werkzeug interactive debugger (which allows arbitrary code execution).
        debug = os.environ.get("FLASK_CONFIG", "").lower() in ("development",)

    threaded = _parse_bool_env(os.environ.get("FLASK_THREADED"), default=True)

    def _use_dev_reloader(enabled_debug: bool) -> bool:
        """Whether to enable Werkzeug's stat reloader in the Flask dev server."""
        if not enabled_debug:
            return False
        env = os.environ.get("FLASK_USE_RELOADER")
        if env is not None:
            return _parse_bool_env(env, default=False)
        # Windows: off by default — long-running subprocess builds (P&B report) can
        # trigger spurious reloads even with exclude_patterns.
        return os.name != "nt"

    use_reloader = _use_dev_reloader(debug)

    if os.environ.get("FLASK_CONFIG", "").lower() == "production":
        app.logger.warning("FLASK_CONFIG=production but running via `python run.py`.")
        app.logger.warning("For production/Azure, prefer Gunicorn (see `config/gunicorn.conf.py` and `entrypoint.sh`).")

    # Explicit opt-in for gevent (useful for WebSocket debugging on Windows).
    if _should_use_gevent():
        try:
            from gevent import pywsgi
            try:
                # Provides WebSocket upgrade support for Flask-Sock under gevent.
                # Without this handler, Flask-Sock may fall back to simple-websocket threads.
                from geventwebsocket.handler import WebSocketHandler  # type: ignore
            except Exception as e:
                logging.getLogger(__name__).debug("gevent-websocket WebSocketHandler import failed: %s", e)
                WebSocketHandler = None  # type: ignore

            app.logger.info(f"Starting gevent WSGI server on {host}:{port}")
            app.logger.info("Note: gevent mode does not enable Flask auto-reload.")
            if WebSocketHandler is None:
                app.logger.warning(
                    "gevent-websocket is not installed; WebSocket upgrades may not work correctly under gevent. "
                    "Install with: pip install gevent-websocket"
                )
                server = pywsgi.WSGIServer((host, port), app, log=app.logger)
            else:
                server = pywsgi.WSGIServer(
                    (host, port),
                    app,
                    handler_class=WebSocketHandler,
                    log=app.logger,
                )
            try:
                server.serve_forever()
            except KeyboardInterrupt:
                app.logger.info("Received Ctrl+C, shutting down gevent server...")
                try:
                    server.stop(timeout=1)
                except Exception as stop_e:
                    logging.getLogger(__name__).debug("gevent server stop failed: %s", stop_e)
        except Exception as e:
            app.logger.error(f"Failed to start gevent server: {e}")
            app.logger.warning("Falling back to Flask development server.")

    # Default: Flask development server (development ergonomics + reloader).
    #
    # On Windows the stat reloader can trigger false-positive reloads because:
    #   1. Python writes __pycache__/*.pyc files on first import after a reload.
    #      On some Windows FS configurations this can bump the mtime of the
    #      parent directory, which in turn looks like a watched .py file changed.
    #   2. The instance/logs/ directory lives inside the project tree; any log
    #      write during startup can appear as a file-system change.
    #
    # We pass exclude_patterns to the reloader to skip these noisy paths.
    use_stat_reloader = os.name == "nt"
    if debug and not use_reloader:
        app.logger.info(
            "Flask auto-reloader disabled (set FLASK_USE_RELOADER=true to enable). "
            "Recommended on Windows while running P&B report builds."
        )
    app.logger.debug(
        f"Starting Flask dev server on {host}:{port} "
        f"(debug={debug}, threaded={threaded}, use_reloader={use_reloader})"
    )

    # Paths to exclude from the stat/watchdog reloader so they don't trigger
    # spurious restarts (relative glob patterns understood by Werkzeug reloader).
    _exclude_patterns = [
        "**/__pycache__/**",
        "**/*.pyc",
        "**/instance/**",
        "**/.pytest_cache/**",
        "**/.coverage",
        "**/*.log",
        # P&B report build writes heavily here; exclude to avoid dev-server reload mid-build.
        "**/Visuals tool/report/**",
        "**/Visuals tool/Figures/**",
        "**/Visuals tool/**",
    ]

    # Werkzeug's _stat_ignore_scan only covers sys.prefix / sys.base_prefix.
    # On Windows with a system Python install, user site-packages lives under
    # %APPDATA%\Python\... which is a *different* path prefix and therefore IS
    # scanned and watched.  Packages like playwright write .pyc files on first
    # import; on Windows NTFS that updates the parent directory mtime, which
    # causes the reloader to detect a change and restart Flask mid-build.
    # Add it explicitly so the pattern-based exclusion covers it even when the
    # reloader is opt-in enabled via FLASK_USE_RELOADER=true.
    try:
        import site as _site
        _user_site = _site.getusersitepackages()
        if _user_site and os.path.isdir(_user_site):
            # forward-slash form matches on all platforms via fnmatch
            _exclude_patterns.append(_user_site.replace("\\", "/") + "/**")
    except Exception:
        pass

    if use_stat_reloader:
        app.run(
            debug=debug,
            host=host,
            port=port,
            use_reloader=use_reloader,
            reloader_type="stat",
            threaded=threaded,
            exclude_patterns=_exclude_patterns,
        )
    else:
        app.run(
            debug=debug,
            host=host,
            port=port,
            use_reloader=use_reloader,
            threaded=threaded,
            exclude_patterns=_exclude_patterns,
        )
