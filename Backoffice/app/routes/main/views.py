from flask import render_template, request, redirect, url_for, flash, session, current_app, send_file, send_from_directory
from flask_login import login_required, current_user
from app.models import db, Country, PublicSubmission, SubmittedDocument, FormSection, FormItem
from app.models.assignments import AssignmentEntityStatus
from io import BytesIO
import os
from flask_babel import _
from contextlib import suppress
from app.extensions import limiter
from app.services.app_settings_service import user_has_ai_beta_access

from app.routes.main import bp


@bp.route("/flags/<language>.svg")
@limiter.exempt
def language_flag_svg(language):
    """Serve a flag SVG for a language code from same-origin.

    Windows often renders regional-indicator flag emojis as letters (e.g., "JP").
    To make flags reliable, we serve a small SVG (Twemoji) via this endpoint so
    CSP img-src 'self' continues to work without allowing external image hosts.
    """
    from flask import make_response, send_from_directory
    from app.utils.language_flags import (
        normalize_language_code,
        language_to_country_flag_code,
    )

    lang = normalize_language_code(language or "") or "en"
    cc = language_to_country_flag_code(lang) or "un"

    # Flags MUST be served from local disk only.
    cache_dir = os.path.join(current_app.instance_path, "flag_cache")
    with suppress(Exception):
        os.makedirs(cache_dir, exist_ok=True)
    cache_path = os.path.join(cache_dir, f"{cc}.svg")

    is_development = current_app.config.get('DEBUG', False)

    # Serve cached flag if present
    with suppress(Exception):
        if os.path.exists(cache_path):
            resp = send_from_directory(cache_dir, f"{cc}.svg")
            resp.headers["Content-Type"] = "image/svg+xml; charset=utf-8"
            if is_development:
                resp.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
                resp.headers["Pragma"] = "no-cache"
                resp.headers["Expires"] = "0"
            else:
                resp.headers["Cache-Control"] = "public, max-age=31536000"
            return resp

    # Local placeholder (no network fetches here)
    static_dir = os.path.join(current_app.root_path, "static")
    resp = send_from_directory(os.path.join(static_dir, "images", "flags"), "placeholder.svg")
    resp.headers["Content-Type"] = "image/svg+xml; charset=utf-8"
    if is_development:
        resp.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
        resp.headers["Pragma"] = "no-cache"
        resp.headers["Expires"] = "0"
    else:
        resp.headers["Cache-Control"] = "public, max-age=31536000"
    return resp


# Language switching route
@bp.route('/language/<language>')
def set_language(language):
    """Set the language for the current session"""
    from app.utils.redirect_utils import is_safe_redirect_url
    from config import Config
    supported = list(current_app.config.get("SUPPORTED_LANGUAGES", Config.LANGUAGES) or [])
    lang_norm = str(language).lower().replace("-", "_")
    base = lang_norm.split("_")[0] if lang_norm else ""

    resolved = None
    if language in supported:
        resolved = str(language).lower()
    elif lang_norm in supported:
        resolved = lang_norm
    elif base and base in supported:
        resolved = base
    else:
        for s in supported:
            s_norm = str(s).lower().replace("-", "_")
            if s_norm == lang_norm or (s_norm.split("_")[0] == base and base):
                resolved = str(s).lower()
                break

    if resolved:
        session["language"] = resolved
        try:
            from flask_babel import refresh

            refresh()
        except Exception:
            pass
    # SECURITY: Validate referrer and use only its path+query (no scheme/host) to prevent open redirect
    referrer = request.referrer
    if referrer and is_safe_redirect_url(referrer):
        from urllib.parse import urlparse as _urlparse
        _p = _urlparse(referrer)
        _safe = _p.path + ('?' + _p.query if _p.query else '')
        return redirect(_safe or url_for('main.dashboard'))
    return redirect(url_for('main.dashboard'))

# Translation reload route (for development)
@bp.route('/reload-translations')
def reload_translations():
    """Manually reload translations (development only)"""
    from app.utils.redirect_utils import is_safe_redirect_url
    if current_app.config.get('DEBUG', False):
        from flask_babel import refresh
        try:
            from app.extensions import ensure_translation_mo_files

            td = current_app.config.get("BACKOFFICE_TRANSLATIONS_DIR")
            if td:
                ensure_translation_mo_files(current_app, td)
            refresh()
            flash(_("Translations reloaded successfully!"), "success")
        except Exception as e:
            flash(_("An error occurred. Please try again."), "danger")
    else:
        flash(_("Translation reloading is only available in development mode."), "warning")
    # SECURITY: Validate referrer and use only its path+query (no scheme/host) to prevent open redirect
    referrer = request.referrer
    if referrer and is_safe_redirect_url(referrer):
        from urllib.parse import urlparse as _urlparse
        _p = _urlparse(referrer)
        _safe = _p.path + ('?' + _p.query if _p.query else '')
        return redirect(_safe or url_for('main.dashboard'))
    return redirect(url_for('main.dashboard'))


@bp.route("/chat", methods=["GET"], defaults={"conversation_id": None})
@bp.route("/chat/<uuid:conversation_id>", methods=["GET"])
@login_required
def chat_immersive(conversation_id=None):
    """Full-page immersive chat view (ChatGPT-style). Requires chatbot enabled.
    URL /chat for new chat, /chat/<uuid> to open a specific conversation."""
    if not current_app.config.get("CHATBOT_ENABLED", True):
        flash(_("Chat is not available."), "warning")
        return redirect(url_for("main.dashboard"))
    if not getattr(current_user, "chatbot_enabled", True):
        flash(_("Chat is disabled for your account."), "warning")
        return redirect(url_for("main.dashboard"))
    if not user_has_ai_beta_access(current_user):
        flash(_("AI is currently in beta and available only to selected users."), "warning")
        return redirect(url_for("main.dashboard"))
    try:
        from app.services.app_settings_service import get_chatbot_org_only, is_organization_email
        if get_chatbot_org_only() and not is_organization_email(getattr(current_user, "email", "")):
            flash(_("Chat is only available to organization users."), "warning")
            return redirect(url_for("main.dashboard"))
    except Exception:
        pass
    websocket_enabled = bool(current_app.config.get("WEBSOCKET_ENABLED", True))
    try:
        from app.services.app_settings_service import get_chatbot_name
        chatbot_name = get_chatbot_name(default="")
    except Exception as e:
        current_app.logger.debug("get_chatbot_name failed: %s", e)
        chatbot_name = ""
    return render_template(
        "core/chat_immersive.html",
        title=(chatbot_name if chatbot_name else _("AI Assistant")),
        initial_conversation_id=str(conversation_id) if conversation_id else None,
        websocket_enabled=websocket_enabled,
    )


@bp.route("/download_submission_pdf/<int:submission_id>")
@login_required
def download_submission_pdf(submission_id):
    """Generate and serve a PDF of the public submission using the exact HTML template."""
    submission = PublicSubmission.query.get_or_404(submission_id)

    from app.services.authorization_service import AuthorizationService
    if not AuthorizationService.is_admin(current_user):
        if not any(
            perm.entity_type == "country" and perm.entity_id == submission.country_id
            for perm in getattr(current_user, "entity_permissions", [])
        ):
            from flask import abort
            abort(403)

    # Create a dummy field class for form rendering
    class DummyField:
        def __init__(self, data, label=""):
            self.data = data
            self.label = label

    class DummyForm:
        def __init__(self, submission):
            self.name = DummyField(submission.submitter_name, "Name")
            self.email = DummyField(submission.submitter_email, "Email")
            self.csrf_token = DummyField("")

    class DummyCountryForm:
        def __init__(self, country):
            self.country_id = DummyField(country, "Country")

    # Create dummy forms to match template structure
    form = DummyForm(submission)
    country_form = DummyCountryForm(submission.country)

    # Organize data entries by section (unified FormItem model)
    organized_data = {}
    for entry in submission.data_entries:
        form_item = getattr(entry, 'form_item', None)
        if not form_item:
            continue
        section = FormSection.query.get(form_item.section_id)
        if not section:
            continue
        if section.id not in organized_data:
            organized_data[section.id] = {
                'section': section,
                'entries': []
            }
        entry_type = 'indicator' if form_item.item_type == 'indicator' else ('question' if form_item.item_type == 'question' else form_item.item_type)
        organized_data[section.id]['entries'].append({
            'type': entry_type,
            'item': form_item,
            'value': entry.value
        })

    # Sort sections by their order
    organized_sections = sorted(
        organized_data.values(),
        key=lambda x: x['section'].order if x['section'].order is not None else float('inf')
    )

    # Organize documents by section (use SubmittedDocument.form_item)
    organized_documents = {}
    for doc in submission.submitted_documents:
        form_item = getattr(doc, 'form_item', None)
        if not form_item or not form_item.form_section:
            continue
        section = form_item.form_section
        if section.id not in organized_documents:
            organized_documents[section.id] = {
                'section': section,
                'documents': []
            }
        organized_documents[section.id]['documents'].append(doc)

    # Sort document sections by their order
    organized_doc_sections = sorted(
        organized_documents.values(),
        key=lambda x: x['section'].order if x['section'].order is not None else float('inf')
    )

    # Generate HTML using the exact template
    html_content = render_template(
        'public_form.html',
        title=f"Submission Details - {submission.country.name}",
        form=form,
        country_form=country_form,
        sections=organized_sections,
        document_sections=organized_doc_sections,
        submission=submission,
        is_pdf=True  # Flag to modify template behavior for PDF
    )

    # Create PDF from HTML
    pdf_buffer = BytesIO()

    try:
        from weasyprint import HTML, CSS  # type: ignore
    except Exception as e:
        current_app.logger.error(f"WeasyPrint not available: {e}")
        return current_app.response_class(
            response="PDF generation is not available on this deployment.",
            status=503,
            mimetype='text/plain'
        )

    static_dir = os.path.join(current_app.root_path, 'static')

    pdf_css = CSS(string='''
        @page {
            margin: 2.5cm 2cm;
            size: letter;
            @bottom-right {
                content: "Page " counter(page);
                font-size: 9pt;
                color: #6b7280;
                padding: 1cm 0;
            }
            @top-center {
                content: string(title);
                font-size: 9pt;
                color: #6b7280;
                padding: 1cm 0;
            }
        }

        /* Set string value for running header */
        h1 { string-set: title content(); }

        /* Base styles */
        body {
            font-family: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            background-color: white !important;
            color: #111827;
            line-height: 1.5;
        }

        /* Container */
        .container {
            width: 100% !important;
            max-width: none !important;
            margin: 0 !important;
            padding: 0 !important;
        }

        /* Form sections */
        .form-section {
            background-color: white;
            border: 1px solid #e5e7eb;
            border-radius: 8px;
            padding: 2rem;
            margin-bottom: 2rem;
            page-break-inside: avoid;
        }

        /* Section titles */
        .form-section-title {
            font-size: 1.5rem;
            font-weight: bold;
            color: #2c3e50;
            margin-bottom: 1.5rem;
            border-bottom: 2px solid #e0e0e0;
            padding-bottom: 0.5rem;
        }

        /* Labels */
        .form-item-label {
            font-weight: 600;
            color: #34495e;
            margin-bottom: 0.5rem;
            display: block;
        }

        /* Input fields */
        .form-item-input {
            border: 1px solid #dcdcdc;
            border-radius: 4px;
            padding: 0.75rem 1rem;
            font-size: 1rem;
            color: #333;
            width: 100%;
            background-color: #f9fafb;
        }

        /* Help text */
        .form-item-help {
            font-size: 0.875rem;
            color: #7f8c8d;
            margin-top: 0.5rem;
        }

        /* Form groups */
        .form-group {
            margin-bottom: 1rem;
        }

        /* Hide elements not needed in PDF */
        .no-print, button, .section-nav, input[type="submit"] {
            display: none !important;
        }

        /* Force background colors and borders to show in PDF */
        * {
            -webkit-print-color-adjust: exact !important;
            print-color-adjust: exact !important;
        }

        /* Add page breaks before major sections */
        .form-section {
            page-break-before: auto;
            page-break-after: auto;
        }

        /* Ensure proper spacing */
        .space-y-4 > * + * {
            margin-top: 1rem;
        }
        .space-y-6 > * + * {
            margin-top: 1.5rem;
        }

        /* Section description */
        .section-description {
            color: #555;
            margin-bottom: 1rem;
            line-height: 1.5;
        }
    ''')

    HTML(string=html_content, base_url=static_dir).write_pdf(
        pdf_buffer,
        stylesheets=[pdf_css],
        optimize_size=('fonts', 'images')
    )

    pdf_buffer.seek(0)
    return send_file(
        pdf_buffer,
        download_name=f'submission_{submission_id}_{submission.submitted_at.strftime("%Y%m%d")}.pdf',
        as_attachment=True,
        mimetype='application/pdf'
    )


@bp.route('/sw.js')
@limiter.exempt
def service_worker():
    """Serve the service worker from the app root for proper scope.

    Injects ASSET_VERSION into the service worker file to keep cache versioning in sync.
    """
    try:
        static_dir = os.path.join(current_app.root_path, 'static')
        sw_path = os.path.join(static_dir, 'js', 'sw.js')
        if not os.path.exists(sw_path):
            current_app.logger.error(f"Service worker file not found: {sw_path}")
            return "", 404

        with open(sw_path, 'r', encoding='utf-8') as f:
            sw_content = f.read()

        cache_version = str(current_app.config.get('ASSET_VERSION') or 'v1')

        sw_content = sw_content.replace("'ASSET_VERSION_PLACEHOLDER'", f"'{cache_version}'")

        response = current_app.response_class(
            sw_content,
            mimetype='application/javascript'
        )
        response.headers['Cache-Control'] = 'public, max-age=0, must-revalidate'
        return response
    except Exception as e:
        current_app.logger.error(f"Error serving service worker: {e}")
        return "", 404


# === National Society Structure Management Routes ===
@bp.route("/ns_structure", methods=["GET"])
@login_required
def manage_ns_hierarchy():
    """Manage National Society hierarchy (branches, sub-branches, local units)"""
    from app.models import NSBranch, NSSubBranch, NSLocalUnit
    from flask import abort
    from app.services.authorization_service import AuthorizationService

    is_sys_mgr = AuthorizationService.is_system_manager(current_user)
    is_org_admin = AuthorizationService.has_rbac_permission(current_user, 'admin.organization.manage') or AuthorizationService.has_rbac_permission(current_user, 'admin.countries.view')
    is_focal_point = AuthorizationService.has_role(current_user, 'assignment_editor_submitter')

    # Allow org admins/system managers, and focal points scoped to their countries
    if not (is_sys_mgr or is_org_admin or is_focal_point):
        abort(403)

    # Filter data based on user scope
    if is_focal_point and not (is_sys_mgr or is_org_admin):
        # Get focal point's countries
        user_countries = list(current_user.countries.all()) if hasattr(current_user, 'countries') else []
        if not user_countries:
            branches = []
            subbranches = []
            local_units = []
            countries = []
        else:
            country_ids = [country.id for country in user_countries]
            branches = NSBranch.query.filter(NSBranch.country_id.in_(country_ids)).order_by(NSBranch.display_order, NSBranch.name).all()
            subbranches = NSSubBranch.query.join(NSBranch).filter(NSBranch.country_id.in_(country_ids)).order_by(NSSubBranch.display_order, NSSubBranch.name).all()
            local_units = NSLocalUnit.query.join(NSBranch).filter(NSBranch.country_id.in_(country_ids)).order_by(NSLocalUnit.display_order, NSLocalUnit.name).all()

            if len(user_countries) > 1:
                countries = user_countries
            else:
                countries = []
    else:
        branches = NSBranch.query.order_by(NSBranch.display_order, NSBranch.name).all()
        subbranches = NSSubBranch.query.order_by(NSSubBranch.display_order, NSSubBranch.name).all()
        local_units = NSLocalUnit.query.order_by(NSLocalUnit.display_order, NSLocalUnit.name).all()

        countries = db.session.query(Country).join(NSBranch).distinct().order_by(Country.name).all()

    return render_template("core/ns_structure.html",
                         branches=branches,
                         subbranches=subbranches,
                         local_units=local_units,
                         countries=countries,
                         title="NS Structure")

@bp.route('/manifest.webmanifest')
def manifest():
    """Serve dynamic web app manifest with organization branding"""
    from app.services.app_settings_service import (
        get_organization_name,
        get_organization_short_name,
        get_organization_logo_path,
        get_organization_favicon_path,
        organization_visual_asset_href,
    )
    from flask import jsonify

    org_name = get_organization_name()
    org_short_name = get_organization_short_name() or org_name[:15]

    icon_raw = (
        get_organization_logo_path(default="").strip()
        or get_organization_favicon_path(default="").strip()
        or "IFRC_logo_square.svg"
    )
    icon_src = organization_visual_asset_href(icon_raw, default="IFRC_logo_square.svg")

    icon_path_lower = icon_raw.lower()
    if icon_path_lower.endswith(".svg"):
        icon_type = "image/svg+xml"
        icon_sizes = "any"
    elif icon_path_lower.endswith(".png"):
        icon_type = "image/png"
        icon_sizes = "192x192"
    elif icon_path_lower.endswith((".jpg", ".jpeg")):
        icon_type = "image/jpeg"
        icon_sizes = "192x192"
    else:
        icon_type = "image/svg+xml"
        icon_sizes = "any"

    manifest_data = {
        "name": org_name,
        "short_name": org_short_name,
        "start_url": "/",
        "display": "standalone",
        "background_color": "#ffffff",
        "theme_color": "#ba0c2f",
        "icons": [
            {
                "src": icon_src,
                "sizes": icon_sizes,
                "type": icon_type,
            }
        ],
    }

    return jsonify(manifest_data), 200, {"Content-Type": "application/manifest+json"}
