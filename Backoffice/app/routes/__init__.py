"""Blueprint registration for the Flask application."""

import time


def register_all_blueprints(app, csrf, startup_start, static_folder_path=None):
    """
    Import and register all application blueprints.

    Returns elapsed seconds for blueprint operations (for startup timing logs).
    """
    blueprint_start = time.time()
    app.logger.debug(
        "Starting blueprint imports (elapsed: %.3fs)", blueprint_start - startup_start
    )

    bp_import_start = time.time()
    from app.routes import auth as auth_bp
    from app.routes import main as main_bp
    from app.routes import help_docs as help_docs_bp
    from app.routes import forms as forms_bp
    from app.routes import forms_api as forms_api_bp
    from app.routes import plugins as plugins_api_bp
    from app.routes import public as public_bp
    from app.routes import notifications as notifications_bp
    from app.routes.api import register_api_blueprints, api_bp
    from app.routes.ai import ai_bp
    from app.routes.ai_documents import ai_docs_bp
    from app.routes import excel as excel_bp
    from app.routes.ai_ws import register_ai_ws
    from app.swagger.routes import swagger_bp

    bp_import_time = time.time() - bp_import_start
    if bp_import_time > 0.5:
        app.logger.debug("Blueprint imports took %.3fs", bp_import_time)

    bp_reg_start = time.time()
    app.register_blueprint(auth_bp.bp)
    app.register_blueprint(main_bp.bp)
    app.register_blueprint(help_docs_bp.bp)
    app.register_blueprint(forms_bp.bp)
    app.register_blueprint(forms_api_bp.bp)
    app.register_blueprint(plugins_api_bp.bp)
    app.register_blueprint(public_bp.bp)
    app.register_blueprint(notifications_bp.bp)
    register_api_blueprints(app)

    from app.routes.api.mobile import mobile_bp
    app.register_blueprint(mobile_bp)
    csrf.exempt(mobile_bp)

    app.register_blueprint(swagger_bp)
    app.register_blueprint(ai_bp)
    app.register_blueprint(ai_docs_bp)
    app.register_blueprint(excel_bp.bp)

    try:
        csrf.exempt(ai_bp)
        app.logger.debug("AI v2 blueprint registered and CSRF exempted")
    except Exception as e:
        app.logger.warning("Could not exempt AI v2 blueprint from CSRF: %s", e)

    try:
        register_ai_ws(app)
        app.logger.debug("AI WebSocket endpoint registered")
    except Exception as e:
        app.logger.warning("AI WebSocket endpoint not available: %s", e)

    try:
        from app.routes.notifications_ws import register_notifications_ws
        if register_notifications_ws(app):
            app.logger.debug("Notifications WebSocket endpoint registered")
    except Exception as e:
        app.logger.warning("Notifications WebSocket endpoint not available: %s", e)

    bp_reg_time = time.time() - bp_reg_start
    if bp_reg_time > 0.5:
        app.logger.debug("Blueprint registration took %.3fs", bp_reg_time)

    admin_bp_start = time.time()
    from app.routes.admin import register_admin_blueprints
    register_admin_blueprints(app)
    admin_bp_time = time.time() - admin_bp_start
    if admin_bp_time > 0.5:
        app.logger.debug(
            "Admin blueprints import/registration took %.3fs", admin_bp_time
        )

    from app.startup_tasks import audit_admin_route_guards
    audit_admin_route_guards(app)

    blueprint_time = time.time() - blueprint_start
    if blueprint_time > 1.0:
        app.logger.debug("Total blueprint operations took %.3fs", blueprint_time)

    return blueprint_time
