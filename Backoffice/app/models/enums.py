"""
Enums and constants used across the application models.
"""
import enum


class PublicSubmissionStatus(enum.Enum):
    pending = 'Pending'
    approved = 'Approved'
    rejected = 'Rejected'


class QuestionType(enum.Enum):
    text = 'text'
    textarea = 'textarea'
    number = 'number'
    percentage = 'percentage'
    yesno = 'yesno'
    single_choice = 'single_choice'
    multiple_choice = 'multiple_choice'
    date = 'date'
    datetime = 'datetime'
    blank = 'blank'


class SectionType(enum.Enum):
    standard = 'Standard'
    dynamic_indicators = 'Dynamic Indicators'
    repeat = 'Repeat'


class FormItemType(enum.Enum):
    indicator = 'indicator'
    question = 'question'
    document_field = 'document_field'


class EntityType(str, enum.Enum):
    """Types of organizational entities that can be assigned users and templates."""
    country = 'country'
    national_society = 'national_society'
    ns_branch = 'ns_branch'
    ns_subbranch = 'ns_subbranch'
    ns_localunit = 'ns_localunit'
    division = 'division'
    department = 'department'
    regional_office = 'regional_office'
    cluster_office = 'cluster_office'


class DocumentStatus:
    """Canonical status values for ``SubmittedDocument.status``."""
    PENDING = 'Pending'
    APPROVED = 'Approved'
    REJECTED = 'Rejected'

    ALL = (PENDING, APPROVED, REJECTED)

    @classmethod
    def normalize(cls, raw: str | None) -> str:
        """Normalize a raw status string to the canonical title-case value."""
        s = (raw or '').strip()
        low = s.casefold()
        if low == 'approved':
            return cls.APPROVED
        if low == 'rejected':
            return cls.REJECTED
        if low == 'pending':
            return cls.PENDING
        return s or cls.PENDING


class NotificationType(enum.Enum):
    assignment_created = 'assignment_created'
    assignment_submitted = 'assignment_submitted'
    assignment_approved = 'assignment_approved'
    assignment_reopened = 'assignment_reopened'
    public_submission_received = 'public_submission_received'
    form_updated = 'form_updated'
    document_uploaded = 'document_uploaded'
    user_added_to_country = 'user_added_to_country'
    template_updated = 'template_updated'
    self_report_created = 'self_report_created'
    deadline_reminder = 'deadline_reminder'
    admin_message = 'admin_message'  # Custom admin push notifications
    access_request_received = 'access_request_received'  # Country access request received
