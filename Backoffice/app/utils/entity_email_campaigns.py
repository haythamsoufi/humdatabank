"""
Entity-based email campaign utilities.

Functions for sending emails to entity contacts with To/CC distribution rules.
"""
from typing import List, Dict, Any, Optional, Tuple
from flask import current_app
from app import db
from app.models.core import User, UserEntityPermission
from app.utils.email_client import send_email
from app.utils.notification_emails import sanitize_for_email
from app.services.entity_service import EntityService
from app.utils.organization_helpers import is_org_email
from app.services.authorization_service import AuthorizationService


def get_entity_contacts(entity_type: str, entity_id: int) -> List[User]:
    """
    Get all users (contacts) with access to a specific entity.

    Args:
        entity_type: Entity type ('country', 'ns_branch', etc.)
        entity_id: Entity ID

    Returns:
        List of User objects with access to the entity
    """
    try:
        # Get all users with permissions for this entity
        permissions = UserEntityPermission.query.filter_by(
            entity_type=entity_type,
            entity_id=entity_id
        ).all()

        user_ids = [perm.user_id for perm in permissions]

        if not user_ids:
            return []

        # Get users with valid email addresses
        users = User.query.filter(
            User.id.in_(user_ids),
            User.email.isnot(None),
            User.email != '',
            User.active == True  # Only active users
        ).all()

        return users

    except Exception as e:
        current_app.logger.error(
            f"Error getting contacts for {entity_type} {entity_id}: {str(e)}",
            exc_info=True
        )
        return []


def categorize_contacts(users: List[User]) -> Dict[str, List[str]]:
    """
    Categorize users into different types based on email domain and role.

    Args:
        users: List of User objects

    Returns:
        Dict with keys: 'organization', 'non_organization', 'focal_point', 'admin', 'system_manager'
        Each value is a list of email addresses
    """
    categorized = {
        'organization': [],
        'non_organization': [],
        'focal_point': [],
        'admin': [],
        'system_manager': []
    }

    for user in users:
        if not user.email:
            continue

        email_lower = user.email.lower()

        # Categorize by email domain
        if is_org_email(user.email):
            categorized['organization'].append(user.email)
        else:
            categorized['non_organization'].append(user.email)

        # Categorize by role (RBAC-only)
        if AuthorizationService.is_system_manager(user):
            categorized['system_manager'].append(user.email)
        elif AuthorizationService.is_admin(user):
            categorized['admin'].append(user.email)
        elif AuthorizationService.has_role(user, "assignment_editor_submitter"):
            categorized['focal_point'].append(user.email)

    return categorized


def send_entity_email_campaign(
    entity_type: str,
    entity_id: int,
    subject: str,
    html_content: str,
    text_content: Optional[str] = None,
    distribution_rules: Optional[Dict[str, Any]] = None,
    sender: Optional[str] = None,
    reply_to: Optional[str] = None,
    importance: Optional[str] = None,
    attachments: Optional[List[Tuple[str, bytes, str]]] = None,
) -> bool:
    """
    Send an email to all contacts of an entity with To/CC distribution.

    Args:
        entity_type: Entity type ('country', 'ns_branch', etc.)
        entity_id: Entity ID
        subject: Email subject
        html_content: HTML email content
        text_content: Plain text email content (optional)
        distribution_rules: Dict with 'to' and 'cc' keys, each containing array of user types
                          Format: {'to': ['non_organization', 'focal_point'], 'cc': ['organization', 'admin']}
                          Default: {'to': ['non_organization'], 'cc': ['organization']}
        sender: Sender email (optional)
        reply_to: Reply-to email (optional)
        importance: Email importance ('high', 'normal', 'low')
        attachments: Optional list of (filename, content_bytes, content_type) to attach.

    Returns:
        True if email was sent successfully, False otherwise
    """
    try:
        # Get all contacts for this entity
        contacts = get_entity_contacts(entity_type, entity_id)

        if not contacts:
            entity_name = EntityService.get_entity_display_name(entity_type, entity_id)
            current_app.logger.warning(
                f"No contacts found for {entity_type} {entity_id} ({entity_name})"
            )
            return False

        # Categorize contacts
        categorized = categorize_contacts(contacts)

        # Default distribution rules: IFRC in CC, non-IFRC in To
        if not distribution_rules:
            distribution_rules = {'to': ['non_organization'], 'cc': ['organization']}

        # Build To and CC lists based on distribution rules
        # distribution_rules format: {'to': ['organization', 'focal_point'], 'cc': ['admin', 'system_manager']}
        to_recipients = []
        cc_recipients = []

        # Collect all emails for each field, using sets to avoid duplicates
        to_emails_set = set()
        cc_emails_set = set()

        # Get user types for To field
        to_types = distribution_rules.get('to', [])
        for user_type in to_types:
            if user_type in categorized:
                to_emails_set.update(categorized[user_type])

        # Get user types for CC field
        cc_types = distribution_rules.get('cc', [])
        for user_type in cc_types:
            if user_type in categorized:
                cc_emails_set.update(categorized[user_type])

        # Convert sets to lists
        to_recipients = list(to_emails_set)
        cc_recipients = list(cc_emails_set)

        # Remove emails from CC if they're also in To (To takes precedence)
        cc_recipients = [email for email in cc_recipients if email not in to_emails_set]

        # If no To recipients, move CC to To (email clients require at least one To recipient)
        if not to_recipients and cc_recipients:
            to_recipients = cc_recipients
            cc_recipients = []

        if not to_recipients and not cc_recipients:
            entity_name = EntityService.get_entity_display_name(entity_type, entity_id)
            current_app.logger.warning(
                f"No valid email addresses for {entity_type} {entity_id} ({entity_name})"
            )
            return False

        # Send email
        success = send_email(
            subject=subject,
            recipients=to_recipients,
            html=html_content,
            text=text_content,
            sender=sender,
            reply_to=reply_to,
            cc=cc_recipients if cc_recipients else None,
            importance=importance,
            attachments=attachments,
        )

        if success:
            entity_name = EntityService.get_entity_display_name(entity_type, entity_id)
            current_app.logger.info(
                f"Entity email sent to {entity_type} {entity_id} ({entity_name}): "
                f"To: {len(to_recipients)}, CC: {len(cc_recipients)}"
            )

        return success

    except Exception as e:
        entity_name = EntityService.get_entity_display_name(entity_type, entity_id) if 'entity_name' not in locals() else entity_name
        current_app.logger.error(
            f"Error sending entity email to {entity_type} {entity_id} ({entity_name}): {str(e)}",
            exc_info=True
        )
        return False


def send_multiple_entity_email_campaigns(
    entity_selections: List[Dict[str, int]],
    subject: str,
    html_content: str,
    text_content: Optional[str] = None,
    distribution_rules: Optional[Dict[str, Any]] = None,
    sender: Optional[str] = None,
    reply_to: Optional[str] = None,
    importance: Optional[str] = None,
    static_attachments: Optional[List[Tuple[str, bytes, str]]] = None,
    assignment_pdf_assigned_form_id: Optional[int] = None,
    get_pdf_bytes_for_aes: Optional[Any] = None,
) -> Dict[str, Any]:
    """
    Send emails to multiple entities. One email per entity.

    Args:
        entity_selections: List of {'entity_type': str, 'entity_id': int}
        subject: Email subject
        html_content: HTML email content
        text_content: Plain text email content (optional)
        distribution_rules: Dict with 'to' and 'cc' keys, each containing array of user types
                          Format: {'to': ['non_organization', 'focal_point'], 'cc': ['organization', 'admin']}
        sender: Sender email (optional)
        reply_to: Reply-to email (optional)
        importance: Email importance
        static_attachments: Optional list of (filename, content_bytes, content_type) attached to every email.
        assignment_pdf_assigned_form_id: If set, attach the assignment PDF for each entity (one PDF per entity).
        get_pdf_bytes_for_aes: Callable(aes_id: int) -> (bytes, filename) to generate PDF; required if assignment_pdf_assigned_form_id is set.

    Returns:
        Dict with 'success_count', 'failure_count', 'results' (list of per-entity results)
    """
    results = []
    success_count = 0
    failure_count = 0
    attachments_base = list(static_attachments) if static_attachments else []

    for entity_selection in entity_selections:
        entity_type = entity_selection.get('entity_type')
        entity_id = entity_selection.get('entity_id')

        if not entity_type or not entity_id:
            current_app.logger.warning(
                f"Invalid entity selection: {entity_selection}"
            )
            failure_count += 1
            results.append({
                'entity_type': entity_type,
                'entity_id': entity_id,
                'success': False,
                'error': 'Invalid entity selection'
            })
            continue

        attachments = list(attachments_base)
        if assignment_pdf_assigned_form_id and get_pdf_bytes_for_aes:
            try:
                from app.models.assignments import AssignmentEntityStatus
                aes = AssignmentEntityStatus.query.filter_by(
                    assigned_form_id=assignment_pdf_assigned_form_id,
                    entity_type=entity_type,
                    entity_id=entity_id,
                ).first()
                if aes:
                    pdf_bytes, pdf_filename = get_pdf_bytes_for_aes(aes.id)
                    if pdf_bytes and pdf_filename:
                        attachments.append((pdf_filename, pdf_bytes, 'application/pdf'))
            except Exception as e:
                current_app.logger.warning(
                    f"Could not generate assignment PDF for entity {entity_type}:{entity_id}: {e}",
                    exc_info=True,
                )

        success = send_entity_email_campaign(
            entity_type=entity_type,
            entity_id=entity_id,
            subject=subject,
            html_content=html_content,
            text_content=text_content,
            distribution_rules=distribution_rules,
            sender=sender,
            reply_to=reply_to,
            importance=importance,
            attachments=attachments if attachments else None,
        )

        if success:
            success_count += 1
        else:
            failure_count += 1

        results.append({
            'entity_type': entity_type,
            'entity_id': entity_id,
            'success': success
        })

    return {
        'success_count': success_count,
        'failure_count': failure_count,
        'total': len(entity_selections),
        'results': results
    }
