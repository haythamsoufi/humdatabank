from flask import current_app, url_for
from app.services.email.rendering import render_admin_email_template
from app.services.email.client import send_email
from app.services.email.delivery import log_email_attempt, mark_email_sent, mark_email_failed
from app.utils.datetime_helpers import utcnow
from app.utils.organization_helpers import (
    get_org_name, get_org_short_name, get_org_copyright_year
)
from app.services.app_settings_service import get_email_template
import logging
from contextlib import suppress
from markupsafe import escape

def normalize_sector_data(sector_data, is_sector=True):
    """
    Normalize sector/subsector data for comparison.
    Handles both old string format and new JSON format.
    Converts IDs to names for proper comparison.
    Returns a normalized string for comparison.
    """
    if sector_data is None:
        return None

    if isinstance(sector_data, dict):
        # New JSON format with primary/secondary/tertiary
        parts = []

        # Helper function to convert ID to name if needed
        def convert_id_to_name(value, is_sector=True):
            if isinstance(value, str):
                return value.strip()
            elif isinstance(value, int):
                # Try to convert ID to name
                try:
                    from flask import current_app
                    from app.models import Sector, SubSector

                    if is_sector:
                        sector = Sector.query.get(value)
                        return sector.name if sector else str(value)
                    else:
                        subsector = SubSector.query.get(value)
                        return subsector.name if subsector else str(value)
                except Exception as e:
                    current_app.logger.debug("sector/subsector name lookup failed: %s", e)
                    return str(value)
            else:
                return str(value)

        if sector_data.get('primary'):
            parts.append(convert_id_to_name(sector_data['primary'], is_sector))
        if sector_data.get('secondary'):
            parts.append(convert_id_to_name(sector_data['secondary'], is_sector))
        if sector_data.get('tertiary'):
            parts.append(convert_id_to_name(sector_data['tertiary'], is_sector))

        result = ' | '.join(parts) if parts else None
        return result
    else:
        # Old string format - handle both string and integer values
        if isinstance(sector_data, str):
            result = sector_data.strip() if sector_data else None
        else:
            result = str(sector_data) if sector_data else None

        return result

def create_comparison_table(suggestion, original_indicator):
    """Create HTML table comparing original vs suggested values"""
    fields = [
        ('Indicator Name', 'name', 'indicator_name'),  # (display_name, original_field, suggested_field)
        ('Definition', 'definition', 'definition'),
        ('Type', 'type', 'type'),
        ('Unit', 'unit', 'unit'),
        ('Sector', 'sector', 'sector'),
        ('Sub-sector', 'sub_sector', 'sub_sector'),
        ('Emergency Context', 'emergency', 'emergency'),
        ('Related Programs', 'related_programs', 'related_programs')
    ]

    table_rows = []
    for field_name, original_field, suggested_field in fields:
        # Get original value from the indicator
        original_value = getattr(original_indicator, original_field, None) if original_indicator else None
        suggested_value = getattr(suggestion, suggested_field, None)

        # Format display values
        if original_field == 'emergency':
            original_display = 'Yes' if original_value else 'No' if original_value is not None else 'Not provided'
            suggested_display = 'Yes' if suggested_value else 'No'
        elif original_field == 'sector':
            # Format sector display - show empty if no original data
            if original_indicator and original_indicator.sector:
                # Use normalize_sector_data to convert IDs to names for display
                normalized_original = normalize_sector_data(original_indicator.sector, is_sector=True)
                if normalized_original:
                    # Format the normalized data for display
                    if isinstance(original_indicator.sector, dict):
                        original_parts = []
                        if original_indicator.sector.get('primary'):
                            # Convert ID to name for display
                            primary_name = normalize_sector_data({'primary': original_indicator.sector['primary']}, is_sector=True)
                            original_parts.append(f"Primary: {primary_name}")
                        if original_indicator.sector.get('secondary'):
                            # Convert ID to name for display
                            secondary_name = normalize_sector_data({'primary': original_indicator.sector['secondary']}, is_sector=True)
                            original_parts.append(f"Secondary: {secondary_name}")
                        if original_indicator.sector.get('tertiary'):
                            # Convert ID to name for display
                            tertiary_name = normalize_sector_data({'primary': original_indicator.sector['tertiary']}, is_sector=True)
                            original_parts.append(f"Tertiary: {tertiary_name}")
                        original_display = ' | '.join(original_parts) if original_parts else ''
                    else:
                        original_display = normalized_original
                else:
                    original_display = ''
            else:
                original_display = ''

            # Format suggested sector - handle both old string format and new JSON format
            if suggestion.sector:
                if isinstance(suggestion.sector, dict):
                    # New JSON format with primary/secondary/tertiary
                    sector_parts = []
                    if suggestion.sector.get('primary'):
                        sector_parts.append(f"Primary: {suggestion.sector['primary']}")
                    if suggestion.sector.get('secondary'):
                        sector_parts.append(f"Secondary: {suggestion.sector['secondary']}")
                    if suggestion.sector.get('tertiary'):
                        sector_parts.append(f"Tertiary: {suggestion.sector['tertiary']}")
                    suggested_display = ' | '.join(sector_parts) if sector_parts else ''
                else:
                    # Old string format
                    suggested_display = str(suggestion.sector)
            else:
                suggested_display = ''
        elif original_field == 'sub_sector':
            # Format sub-sector display - show empty if no original data
            if original_indicator and original_indicator.sub_sector:
                # Use normalize_sector_data to convert IDs to names for display
                normalized_original = normalize_sector_data(original_indicator.sub_sector, is_sector=False)
                if normalized_original:
                    # Format the normalized data for display
                    if isinstance(original_indicator.sub_sector, dict):
                        original_parts = []
                        if original_indicator.sub_sector.get('primary'):
                            # Convert ID to name for display
                            primary_name = normalize_sector_data({'primary': original_indicator.sub_sector['primary']}, is_sector=False)
                            original_parts.append(f"Primary: {primary_name}")
                        if original_indicator.sub_sector.get('secondary'):
                            # Convert ID to name for display
                            secondary_name = normalize_sector_data({'primary': original_indicator.sub_sector['secondary']}, is_sector=False)
                            original_parts.append(f"Secondary: {secondary_name}")
                        if original_indicator.sub_sector.get('tertiary'):
                            # Convert ID to name for display
                            tertiary_name = normalize_sector_data({'primary': original_indicator.sub_sector['tertiary']}, is_sector=False)
                            original_parts.append(f"Tertiary: {tertiary_name}")
                        original_display = ' | '.join(original_parts) if original_parts else ''
                    else:
                        original_display = normalized_original
                else:
                    original_display = ''
            else:
                original_display = ''

            # Format suggested subsector - handle both old string format and new JSON format
            if suggestion.sub_sector:
                if isinstance(suggestion.sub_sector, dict):
                    # New JSON format with primary/secondary/tertiary
                    subsector_parts = []
                    if suggestion.sub_sector.get('primary'):
                        subsector_parts.append(f"Primary: {suggestion.sub_sector['primary']}")
                    if suggestion.sub_sector.get('secondary'):
                        subsector_parts.append(f"Secondary: {suggestion.sub_sector['secondary']}")
                    if suggestion.sub_sector.get('tertiary'):
                        subsector_parts.append(f"Tertiary: {suggestion.sub_sector['tertiary']}")
                    suggested_display = ' | '.join(subsector_parts) if subsector_parts else ''
                else:
                    # Old string format
                    suggested_display = str(suggestion.sub_sector)
            else:
                suggested_display = ''
        else:
            # Format regular values - show empty if no original data
            original_display = str(original_value) if original_value is not None else ''
            suggested_display = str(suggested_value) if suggested_value is not None else ''

        # Determine if value changed
        # For comparison, we need to handle the special cases properly
        if original_field == 'emergency':
            original_compare = original_value
            suggested_compare = suggested_value
        elif original_field == 'sector':
            # Normalize sector data for comparison
            original_compare = normalize_sector_data(original_indicator.sector if original_indicator else None, is_sector=True)
            suggested_compare = normalize_sector_data(suggestion.sector, is_sector=True)
        elif original_field == 'sub_sector':
            # Normalize subsector data for comparison
            original_compare = normalize_sector_data(original_indicator.sub_sector if original_indicator else None, is_sector=False)
            suggested_compare = normalize_sector_data(suggestion.sub_sector, is_sector=False)
        else:
            original_compare = original_value
            suggested_compare = suggested_value

        # Determine if value changed
        # Treat None and empty string as equivalent for empty values
        original_is_empty = original_compare is None or original_compare == ""
        suggested_is_empty = suggested_compare is None or suggested_compare == ""

        if original_is_empty and suggested_is_empty:
            is_changed = False
        elif original_is_empty or suggested_is_empty:
            is_changed = True
        else:
            is_changed = original_compare != suggested_compare



        # Apply styling
        original_class = 'unchanged' if not is_changed else 'changed'
        suggested_class = 'unchanged' if not is_changed else 'changed'

        safe_field_name = escape(field_name)
        safe_original_display = escape(original_display) if original_display else ''
        safe_suggested_display = escape(suggested_display) if suggested_display else ''

        table_rows.append(f"""
            <tr>
                <td><strong>{safe_field_name}</strong></td>
                <td class="{original_class}">{safe_original_display}</td>
                <td class="{suggested_class}">{safe_suggested_display}</td>
            </tr>
        """)

    return f"""
        <table class="comparison-table">
            <thead>
                <tr>
                    <th>Field</th>
                    <th>Original Value</th>
                    <th>Suggested Value</th>
                </tr>
            </thead>
            <tbody>
                {''.join(table_rows)}
            </tbody>
        </table>
        <p><em>Highlighted rows show the changes you suggested.</em></p>
    """

def create_new_indicator_details(suggestion):
    """Create HTML list for new indicator details"""
    fields = [
        ('Indicator Name', suggestion.indicator_name),
        ('Definition', suggestion.definition),
        ('Type', suggestion.type),
        ('Unit', suggestion.unit),
        ('Emergency Context', 'Yes' if suggestion.emergency else 'No'),
        ('Related Programs', suggestion.related_programs)
    ]

    list_items = []
    for field_name, value in fields:
        if value is not None:
            display_value = str(value)
        else:
            display_value = 'Not provided'
        list_items.append(
            f'<li><strong>{escape(field_name)}:</strong> {escape(display_value)}</li>'
        )

    # Handle sector and subsector separately for better formatting
    if suggestion.sector:
        if isinstance(suggestion.sector, dict):
            sector_parts = []
            if suggestion.sector.get('primary'):
                sector_parts.append(f"Primary: {suggestion.sector['primary']}")
            if suggestion.sector.get('secondary'):
                sector_parts.append(f"Secondary: {suggestion.sector['secondary']}")
            if suggestion.sector.get('tertiary'):
                sector_parts.append(f"Tertiary: {suggestion.sector['tertiary']}")
            sector_display = ' | '.join(sector_parts) if sector_parts else 'Not provided'
        else:
            sector_display = str(suggestion.sector)
        list_items.append(f'<li><strong>Sector:</strong> {escape(sector_display)}</li>')
    else:
        list_items.append('<li><strong>Sector:</strong> Not provided</li>')

    if suggestion.sub_sector:
        if isinstance(suggestion.sub_sector, dict):
            subsector_parts = []
            if suggestion.sub_sector.get('primary'):
                subsector_parts.append(f"Primary: {suggestion.sub_sector['primary']}")
            if suggestion.sub_sector.get('secondary'):
                subsector_parts.append(f"Secondary: {suggestion.sub_sector['secondary']}")
            if suggestion.sub_sector.get('tertiary'):
                subsector_parts.append(f"Tertiary: {suggestion.sub_sector['tertiary']}")
            subsector_display = ' | '.join(subsector_parts) if subsector_parts else 'Not provided'
        else:
            subsector_display = str(suggestion.sub_sector)
        list_items.append(f'<li><strong>Sub-sector:</strong> {escape(subsector_display)}</li>')
    else:
        list_items.append('<li><strong>Sub-sector:</strong> Not provided</li>')

    return f"""
        <ul class="new-indicator-list">
            {''.join(list_items)}
        </ul>
    """

def send_suggestion_confirmation_email(suggestion):
    """
    Send a confirmation email to the submitter of an indicator suggestion.

    Args:
        suggestion: IndicatorSuggestion instance
    """
    try:
        # Get email template from database or use default
        default_template = """
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="utf-8">
            <title>Indicator Suggestion Confirmation</title>
            <style>
                body { font-family: Arial, sans-serif; line-height: 1.6; color: #333; }
                .container { max-width: 600px; margin: 0 auto; padding: 20px; }
                .header { background-color: #d32f2f; color: white; padding: 20px; text-align: center; }
                .content { padding: 20px; background-color: #f9f9f9; }
                .footer { padding: 20px; text-align: center; font-size: 12px; color: #666; }
                .highlight { background-color: #fff3cd; padding: 15px; border-left: 4px solid #ffc107; margin: 15px 0; }
                .details { background-color: white; padding: 15px; margin: 15px 0; border-radius: 5px; }
                .comparison-table { width: 100%; border-collapse: collapse; margin: 15px 0; }
                .comparison-table th, .comparison-table td {
                    border: 1px solid #ddd; padding: 8px; text-align: left;
                }
                .comparison-table th { background-color: #f5f5f5; font-weight: bold; }
                .unchanged { color: #666; font-style: italic; }
                .changed { background-color: #fff3cd; font-weight: bold; }
                .new-indicator-list { list-style: none; padding: 0; }
                .new-indicator-list li {
                    padding: 8px 0; border-bottom: 1px solid #eee;
                }
                .new-indicator-list li:last-child { border-bottom: none; }
                .new-indicator-list strong { color: #1976d2; }
            </style>
        </head>
        <body>
            <div class="container">
                <div class="header">
                    <h1>{{ org_name }}</h1>
                    <h2>Indicator Suggestion Confirmation</h2>
                </div>

                <div class="content">
                    <p>Dear {{ submitter_name }},</p>

                    <p>Thank you for submitting your indicator suggestion to {{ org_name }}. We have received your submission and it is currently under review.</p>

                    <div class="highlight">
                        <strong>Submission Details:</strong><br>
                        <strong>Type:</strong> {{ suggestion_type_display }}<br>
                        <strong>Indicator Name:</strong> {{ indicator_name }}<br>
                        <strong>Submitted:</strong> {{ submitted_date }}
                    </div>

                    <div class="details">
                        <h3>Suggestion Details:</h3>
                        {{ suggestion_details | safe }}
                    </div>

                    <div class="details">
                        <h3>What happens next?</h3>
                        <ul>
                            <li>Our team will review your suggestion within 5-7 business days</li>
                            <li>If approved, the indicator will be added to our database</li>
                            <li>If we need additional information, we'll contact you at this email address</li>
                            <li>You'll receive a final notification once the review is complete</li>
                        </ul>
                    </div>

                    <p>If you have any questions about your submission, please don't hesitate to contact us.</p>

                    <p>Best regards,<br>
                    The {{ org_name }} Team</p>
                </div>

                <div class="footer">
                    <p>This is an automated message. Please do not reply to this email.</p>
                    <p>© {{ copyright_year }} {{ org_name }}. All rights reserved.</p>
                </div>
            </div>
        </body>
        </html>
        """

        # Load template from database with fallback to default
        html_template = get_email_template('email_template_suggestion_confirmation', default_template)

        # Prepare email content
        subject = f"Indicator Suggestion Confirmation - {suggestion.indicator_name}"

        # Format the suggestion type for display
        suggestion_type_display = suggestion.suggestion_type_display

        # Format the submission date
        submitted_date = suggestion.submitted_at.strftime("%B %d, %Y at %I:%M %p")

        # Determine if this is a correction or new indicator
        is_correction = suggestion.suggestion_type in ['correction', 'improvement']

        if is_correction:
            # Get the original indicator data for comparison using the relationship
            original_indicator = suggestion.indicator

            # Create comparison table content
            suggestion_details = create_comparison_table(suggestion, original_indicator)
        else:
            # Create simple list for new indicators
            suggestion_details = create_new_indicator_details(suggestion)

        # Get organization branding
        org_name = get_org_name()
        copyright_year = get_org_copyright_year()

        # Render the HTML template
        html_content = render_admin_email_template(
            html_template,
            submitter_name=suggestion.submitter_name,
            suggestion_type_display=suggestion_type_display,
            indicator_name=suggestion.indicator_name,
            submitted_date=submitted_date,
            suggestion_details=suggestion_details,
            org_name=org_name,
            copyright_year=copyright_year,
        )

        # Send the email (replyable address)
        team_email = current_app.config.get('TEAM_EMAIL') or current_app.config['MAIL_DEFAULT_SENDER']
        send_email(
            subject=subject,
            recipients=[suggestion.submitter_email],
            html=html_content,
            sender=current_app.config['MAIL_DEFAULT_SENDER'],
            bcc=[team_email] if team_email else None,
        )

        current_app.logger.info(f"Confirmation email sent to {suggestion.submitter_email} for suggestion ID {suggestion.id}")
        return True

    except Exception as e:
        current_app.logger.error(f"Failed to send confirmation email to {suggestion.submitter_email}: {str(e)}")
        return False

def send_admin_notification_email(suggestion):
    """
    Send a notification email to administrators about a new suggestion.

    Args:
        suggestion: IndicatorSuggestion instance
    """
    try:
        # Get admin emails from configuration or database
        admin_emails = current_app.config.get('ADMIN_EMAILS', [])
        if not admin_emails:
            current_app.logger.warning("No admin emails configured for notification")
            return False

        # Get email template from database or use default
        default_template = """
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="utf-8">
            <title>New Indicator Suggestion</title>
            <style>
                body { font-family: Arial, sans-serif; line-height: 1.6; color: #333; }
                .container { max-width: 600px; margin: 0 auto; padding: 20px; }
                .header { background-color: #1976d2; color: white; padding: 20px; text-align: center; }
                .content { padding: 20px; background-color: #f9f9f9; }
                .footer { padding: 20px; text-align: center; font-size: 12px; color: #666; }
                .highlight { background-color: #e3f2fd; padding: 15px; border-left: 4px solid #2196f3; margin: 15px 0; }
                .details { background-color: white; padding: 15px; margin: 15px 0; border-radius: 5px; }
                .comparison-table { width: 100%; border-collapse: collapse; margin: 15px 0; }
                .comparison-table th, .comparison-table td {
                    border: 1px solid #ddd; padding: 8px; text-align: left;
                }
                .comparison-table th { background-color: #f5f5f5; font-weight: bold; }
                .unchanged { color: #666; font-style: italic; }
                .changed { background-color: #fff3cd; font-weight: bold; }
                .new-indicator-list { list-style: none; padding: 0; }
                .new-indicator-list li {
                    padding: 8px 0; border-bottom: 1px solid #eee;
                }
                .new-indicator-list li:last-child { border-bottom: none; }
                .new-indicator-list strong { color: #1976d2; }
            </style>
        </head>
        <body>
            <div class="container">
                <div class="header">
                    <h1>{{ org_name }}</h1>
                    <h2>New Indicator Suggestion</h2>
                </div>

                <div class="content">
                    <p>A new indicator suggestion has been submitted and requires review.</p>

                    <div class="highlight">
                        <strong>Submission Details:</strong><br>
                        <strong>Submitter:</strong> {{ submitter_name }} ({{ submitter_email }})<br>
                        <strong>Type:</strong> {{ suggestion_type_display }}<br>
                        <strong>Indicator Name:</strong> {{ indicator_name }}<br>
                        <strong>Submitted:</strong> {{ submitted_date }}
                    </div>

                    <div class="details">
                        <h3>Suggestion Details:</h3>
                        {{ suggestion_details | safe }}

                        <p><strong>Reason:</strong> {{ reason }}</p>
                        {% if additional_notes %}
                        <p><strong>Additional Notes:</strong> {{ additional_notes }}</p>
                        {% endif %}
                    </div>

                    <p><a href="{{ admin_url }}" style="background-color: #1976d2; color: white; padding: 10px 20px; text-decoration: none; border-radius: 5px;">Review Suggestion</a></p>
                </div>

                <div class="footer">
                    <p>© {{ copyright_year }} {{ org_name }}. All rights reserved.</p>
                </div>
            </div>
        </body>
        </html>
        """

        # Load template from database with fallback to default
        html_template = get_email_template('email_template_admin_notification', default_template)

        # Prepare email content
        subject = f"New Indicator Suggestion: {suggestion.indicator_name}"

        # Format the suggestion type for display
        suggestion_type_display = suggestion.suggestion_type_display

        # Format the submission date
        submitted_date = suggestion.submitted_at.strftime("%B %d, %Y at %I:%M %p")

        # Admin URL (you'll need to adjust this based on your admin URL structure)
        admin_url = f"{current_app.config.get('BASE_URL', 'http://localhost:5000')}/admin/indicator-suggestions/{suggestion.id}"

        # Get organization branding
        org_name = get_org_name()
        copyright_year = get_org_copyright_year()

        # Determine if this is a correction or new indicator
        is_correction = suggestion.suggestion_type in ['correction', 'improvement']

        if is_correction:
            # Get the original indicator data for comparison using the relationship
            original_indicator = suggestion.indicator

            # Create comparison table content
            suggestion_details = create_comparison_table(suggestion, original_indicator)
        else:
            # Create simple list for new indicators
            suggestion_details = create_new_indicator_details(suggestion)

        # Render the HTML template
        html_content = render_admin_email_template(
            html_template,
            submitter_name=suggestion.submitter_name,
            submitter_email=suggestion.submitter_email,
            suggestion_type_display=suggestion_type_display,
            indicator_name=suggestion.indicator_name,
            submitted_date=submitted_date,
            suggestion_details=suggestion_details,
            reason=suggestion.reason,
            additional_notes=suggestion.additional_notes or '',
            admin_url=admin_url,
            org_name=org_name,
            copyright_year=copyright_year,
        )

        # Send the email to admins (replyable address)
        team_email = current_app.config.get('TEAM_EMAIL') or current_app.config['MAIL_DEFAULT_SENDER']
        send_email(
            subject=subject,
            recipients=admin_emails,
            html=html_content,
            sender=current_app.config['MAIL_DEFAULT_SENDER'],
            bcc=[team_email] if team_email else None,
        )

        current_app.logger.info(f"Admin notification email sent for suggestion ID {suggestion.id}")
        return True

    except Exception as e:
        current_app.logger.error(f"Failed to send admin notification email for suggestion ID {suggestion.id}: {str(e)}")
        return False


def _security_alert_fallback_html_body(context):
    """Minimal HTML when template render or sanitisation yields an empty body."""
    from markupsafe import escape
    from app.utils.datetime_helpers import ensure_utc

    ts = context.get("timestamp")
    if ts is not None and hasattr(ts, "strftime"):
        try:
            dt = ensure_utc(ts)
            ts_display = dt.strftime("%Y-%m-%d %H:%M:%S UTC") if dt else str(ts)
        except Exception:
            ts_display = str(ts)
    else:
        ts_display = "N/A"

    event_type = escape(str(context.get("event_type") or "unknown"))
    severity = escape(str(context.get("severity") or "medium"))
    desc = escape(str(context.get("description") or "No description provided"))
    admin_url = escape(str(context.get("admin_url") or ""))
    org = escape(str(context.get("org_name") or ""))

    parts = [
        "<!DOCTYPE html><html><body style=\"font-family:Arial,sans-serif;line-height:1.5;\">",
        "<h1>Security alert</h1>",
        f"<p><strong>Event:</strong> {event_type}</p>",
        f"<p><strong>Severity:</strong> {severity}</p>",
        f"<p><strong>Time:</strong> {escape(ts_display)}</p>",
        f"<p><strong>Description:</strong> {desc}</p>",
    ]
    ip = context.get("ip_address")
    if ip:
        parts.append(f"<p><strong>IP address:</strong> {escape(str(ip))}</p>")
    if context.get("user_email"):
        parts.append(
            f"<p><strong>User:</strong> {escape(str(context['user_email']))} "
            f"(ID {escape(str(context.get('user_id', '')))})</p>"
        )
    elif context.get("user_id") is not None:
        parts.append(f"<p><strong>User ID:</strong> {escape(str(context['user_id']))}</p>")
    if admin_url:
        parts.append(f"<p><a href=\"{admin_url}\">Open security dashboard</a></p>")
    if org:
        parts.append(f"<p style=\"color:#666;font-size:12px;\">{org}</p>")
    parts.append("</body></html>")
    return "".join(parts)


def send_security_alert(subject=None, event_type=None, severity=None, description=None,
                       ip_address=None, user_id=None, timestamp=None, recipients=None, **kwargs):
    """
    Send security alert email to administrators.

    Args:
        subject: Email subject (auto-generated if not provided)
        event_type: Type of security event
        severity: Severity level (low, medium, high, critical)
        description: Event description
        ip_address: IP address associated with the event
        user_id: User ID associated with the event (if applicable)
        timestamp: Event timestamp
        recipients: Optional list of email addresses to send to (overrides ADMIN_EMAILS config)
        **kwargs: Additional context data
    """
    try:
        # Get admin emails - use provided recipients or fall back to config
        admin_emails = recipients if recipients else current_app.config.get('ADMIN_EMAILS', [])
        if not admin_emails:
            current_app.logger.warning("No admin emails configured for security alerts (neither recipients parameter nor ADMIN_EMAILS config)")
            return False

        # Get user email if user_id provided
        user_email = None
        if user_id:
            try:
                from app.models import User
                user = User.query.get(user_id)
                user_email = user.email if user else None
            except Exception as e:
                # Optional enrichment only; do not break alert sending.
                current_app.logger.debug("Security alert: failed to resolve user email for user_id=%s: %s", user_id, e, exc_info=True)

        # Generate subject if not provided
        if not subject:
            severity_str = severity.upper() if severity else "ALERT"
            event_str = event_type.replace('_', ' ').title() if event_type else "Security Event"
            subject = f"Security Alert [{severity_str}]: {event_str}"

        # Get email template from database or use default
        default_template = """
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="utf-8">
            <title>Security Alert</title>
            <style>
                body { font-family: Arial, sans-serif; line-height: 1.6; color: #333; }
                .container { max-width: 700px; margin: 0 auto; padding: 20px; }
                .header { background-color: #d32f2f; color: white; padding: 20px; text-align: center; }
                .header.medium { background-color: #f57c00; }
                .header.high { background-color: #d32f2f; }
                .header.critical { background-color: #c62828; }
                .content { padding: 20px; background-color: #f9f9f9; }
                .footer { padding: 20px; text-align: center; font-size: 12px; color: #666; }
                .alert-box {
                    background-color: #fff3cd;
                    border-left: 4px solid #ffc107;
                    padding: 15px;
                    margin: 15px 0;
                }
                .alert-box.high {
                    background-color: #f8d7da;
                    border-left-color: #dc3545;
                }
                .alert-box.critical {
                    background-color: #f5c6cb;
                    border-left-color: #c62828;
                }
                .details { background-color: white; padding: 15px; margin: 15px 0; border-radius: 5px; }
                .details-table { width: 100%; border-collapse: collapse; }
                .details-table td {
                    padding: 8px;
                    border-bottom: 1px solid #eee;
                }
                .details-table td:first-child {
                    font-weight: bold;
                    width: 30%;
                    color: #666;
                }
                .action-button {
                    display: inline-block;
                    background-color: #1976d2;
                    color: white;
                    padding: 10px 20px;
                    text-decoration: none;
                    border-radius: 5px;
                    margin: 10px 0;
                }
            </style>
        </head>
        <body>
            <div class="container">
                <div class="header {{ severity|lower }}">
                    <h1>⚠️ Security Alert</h1>
                    <h2>{{ event_type|replace('_', ' ')|title }}</h2>
                </div>

                <div class="content">
                    <div class="alert-box {{ severity|lower }}">
                        <strong>Severity:</strong> {{ severity|upper }}<br>
                        <strong>Time:</strong> {{ timestamp|datetimeformat if timestamp else 'N/A' }}
                    </div>

                    <div class="details">
                        <h3>Event Details</h3>
                        <table class="details-table">
                            <tr>
                                <td>Event Type:</td>
                                <td>{{ event_type|replace('_', ' ')|title if event_type else 'N/A' }}</td>
                            </tr>
                            <tr>
                                <td>Description:</td>
                                <td>{{ description or 'No description provided' }}</td>
                            </tr>
                            {% if ip_address %}
                            <tr>
                                <td>IP Address:</td>
                                <td>{{ ip_address }}</td>
                            </tr>
                            {% endif %}
                            {% if user_email %}
                            <tr>
                                <td>User:</td>
                                <td>{{ user_email }} (ID: {{ user_id }})</td>
                            </tr>
                            {% elif user_id %}
                            <tr>
                                <td>User ID:</td>
                                <td>{{ user_id }}</td>
                            </tr>
                            {% endif %}
                            {% if timestamp %}
                            <tr>
                                <td>Timestamp:</td>
                                <td>{{ timestamp }}</td>
                            </tr>
                            {% endif %}
                        </table>
                    </div>

                    <p><a href="{{ admin_url }}" class="action-button">View Security Dashboard</a></p>

                    <p style="color: #666; font-size: 12px; margin-top: 20px;">
                        This is an automated security alert. Please review the security dashboard for more details.
                    </p>
                </div>

                <div class="footer">
                    <p>© {{ copyright_year }} {{ org_name }}. All rights reserved.</p>
                    <p>This is an automated security monitoring alert.</p>
                </div>
            </div>
        </body>
        </html>
        """

        # Load template from database with fallback to default
        html_template = get_email_template('email_template_security_alert', default_template)

        # Prepare template context
        base_url = current_app.config.get('BASE_URL', 'http://localhost:5000')
        admin_url = f"{base_url}/admin/security/dashboard"

        # Get organization branding
        org_name = get_org_name()
        copyright_year = get_org_copyright_year()

        # Convert timestamp to datetime object if it's a string
        # The template expects a datetime object for datetimeformat filter
        timestamp_dt = None
        if timestamp:
            if isinstance(timestamp, str):
                try:
                    from datetime import datetime
                    # Try parsing ISO format timestamp
                    timestamp_dt = datetime.fromisoformat(timestamp.replace('Z', '+00:00'))
                except (ValueError, AttributeError):
                    # If parsing fails, use current time
                    timestamp_dt = utcnow()
            else:
                # Already a datetime object
                timestamp_dt = timestamp
        else:
            timestamp_dt = utcnow()

        context = {
            'event_type': event_type or 'Unknown Event',
            'severity': severity or 'medium',
            'description': description or 'No description provided',
            'ip_address': ip_address,
            'user_id': user_id,
            'org_name': org_name,
            'copyright_year': copyright_year,
            'user_email': user_email,
            'timestamp': timestamp_dt,
            'admin_url': admin_url,
        }

        # Render email content
        html_content = render_admin_email_template(html_template, **context)

        if not (html_content or "").strip():
            current_app.logger.warning(
                "Security alert template produced empty HTML; sending minimal fallback body."
            )
            html_content = _security_alert_fallback_html_body(context)

        # Send email
        team_email = current_app.config.get('TEAM_EMAIL') or current_app.config.get('MAIL_DEFAULT_SENDER')
        success = send_email(
            subject=subject,
            recipients=admin_emails,
            html=html_content,
            sender=current_app.config.get('MAIL_DEFAULT_SENDER'),
            bcc=[team_email] if team_email else None,
        )

        if success:
            current_app.logger.info(f"Security alert email sent to {len(admin_emails)} administrator(s) for event: {event_type}")
        else:
            current_app.logger.error(f"Failed to send security alert email for event: {event_type} to recipients: {admin_emails}")

        return success

    except Exception as e:
        current_app.logger.error(f"Error sending security alert email: {str(e)}", exc_info=True)
        return False


def send_welcome_email(user):
    """
    Send a welcome email to a newly registered user.
    Explains the system and how to request access to entities.

    Note: Welcome emails are sent regardless of user preferences since they are
    one-time onboarding emails that users need to receive when they first register.

    Args:
        user: User instance
    """
    try:
        if not user or not user.email:
            current_app.logger.warning("Cannot send welcome email: user or email is missing")
            return False

        # Note: Welcome emails are intentionally sent regardless of notification preferences
        # because they are essential onboarding communications that users need to receive
        # when they first register. Users can disable future emails via their preferences.

        base_url = current_app.config.get('BASE_URL', 'http://localhost:5000')
        dashboard_url = f"{base_url}/"
        notifications_url = f"{base_url}/notifications"
        org_name = get_org_name()
        copyright_year = get_org_copyright_year()

        # Get email template from database or use default
        default_template = """
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="utf-8">
            <title>Welcome to {{ org_name }}</title>
            <style>
                body { font-family: Arial, sans-serif; line-height: 1.6; color: #333; }
                .container { max-width: 600px; margin: 0 auto; padding: 20px; }
                .header { background-color: #dc2626; color: white; padding: 30px; text-align: center; }
                .content { padding: 30px; background-color: #f9fafb; }
                .section { background-color: white; padding: 20px; margin: 20px 0; border-radius: 5px; border-left: 4px solid #2563eb; }
                .section h3 { margin-top: 0; color: #111827; }
                .section p { margin: 10px 0; color: #4b5563; }
                .button { display: inline-block; padding: 12px 24px; background-color: #2563eb; color: white; text-decoration: none; border-radius: 5px; margin: 10px 0; }
                .button:hover { background-color: #1d4ed8; }
                .footer { text-align: center; padding: 20px; color: #6b7280; font-size: 12px; }
                .highlight { background-color: #eff6ff; padding: 15px; border-left: 4px solid #2563eb; margin: 15px 0; }
                ul { margin: 10px 0; padding-left: 20px; }
                li { margin: 5px 0; color: #4b5563; }
            </style>
        </head>
        <body>
            <div class="container">
                <div class="header">
                    <h1>Welcome to {{ org_name }}!</h1>
                </div>

                <div class="content">
                    <p>Hello {{ user_name }},</p>

                    <p>Welcome to {{ org_name }}! We're excited to have you on board.</p>

                    <div class="section">
                        <h3>Getting Started</h3>
                        <p>Your account has been successfully created. To get started:</p>
                        <ul>
                            <li>Log in to access your dashboard</li>
                            <li>Explore the system and familiarize yourself with the interface</li>
                            <li>Request access to countries, National Societies, or other entities you need to work with</li>
                        </ul>
                        <a href="{{ dashboard_url }}" class="button">Go to Dashboard</a>
                    </div>

                    <div class="section">
                        <h3>Requesting Access to Entities</h3>
                        <p>To work with specific countries, National Societies, or other entities, you'll need to request access:</p>
                        <ol>
                            <li>Go to your dashboard</li>
                            <li>Select the entity (country, National Society, etc.) you want to access</li>
                            <li>Click "Request Access" if you don't have permission yet</li>
                            <li>An administrator will review your request and notify you when it's approved</li>
                        </ol>
                        <div class="highlight">
                            <strong>Note:</strong> You'll receive an email notification when your access request is approved.
                        </div>
                    </div>

                    <div class="section">
                        <h3>Notification Preferences</h3>
                        <p>You can customize how you receive notifications:</p>
                        <ul>
                            <li>Choose between instant, daily, or weekly email digests</li>
                            <li>Enable or disable specific notification types</li>
                            <li>Configure push notifications for mobile devices</li>
                        </ul>
                        <a href="{{ notifications_url }}" class="button">Manage Notifications</a>
                    </div>

                    <div class="section">
                        <h3>Need Help?</h3>
                        <p>If you have any questions or need assistance, please don't hesitate to contact your system administrator or support team.</p>
                    </div>

                    <p>We look forward to working with you!</p>

                    <p>Best regards,<br>
                    {{ org_name }} Team</p>
                </div>

                <div class="footer">
                    <p>© {{ copyright_year }} {{ org_name }}. All rights reserved.</p>
                    <p>This is an automated welcome email.</p>
                </div>
            </div>
        </body>
        </html>
        """

        # Load template from database with fallback to default
        html_template = get_email_template('email_template_welcome', default_template)

        # Prepare context
        user_name = user.name if user.name else user.email.split('@')[0]
        context = {
            'user_name': user_name,
            'dashboard_url': dashboard_url,
            'notifications_url': notifications_url,
            'org_name': org_name,
            'copyright_year': copyright_year
        }

        # Render email content
        html_content = render_admin_email_template(html_template, **context)

        # Log email attempt
        log = log_email_attempt(None, user.id, user.email, f"Welcome to {org_name}")

        # Send email
        try:
            success = send_email(
                subject=f"Welcome to {org_name}",
                recipients=[user.email],
                html=html_content,
                sender=current_app.config.get('MAIL_NOREPLY_SENDER', current_app.config.get('MAIL_DEFAULT_SENDER'))
            )

            if success:
                mark_email_sent(log.id)
                current_app.logger.info(f"Welcome email sent to {user.email}")
            else:
                mark_email_failed(log.id, "Email send returned False", retry=True)
                current_app.logger.error(f"Failed to send welcome email to {user.email}")

            return success

        except Exception as e:
            mark_email_failed(log.id, str(e), retry=True)
            current_app.logger.error(f"Error sending welcome email to {user.email}: {str(e)}")
            return False

    except Exception as e:
        current_app.logger.error(f"Error in send_welcome_email: {str(e)}", exc_info=True)
        return False
