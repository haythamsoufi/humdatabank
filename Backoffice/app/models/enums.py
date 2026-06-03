"""
Enums and constants used across the application models.

Status enum convention (PostgreSQL + Python ``.value``):
- lowercase snake_case storage (e.g. ``pending``, ``in_progress``, ``requires_revision``)
- Title Case only in UI via ``status_display_label()`` / ``localize_status()``
"""
import enum


# Human-readable labels for workflow status values (UI / forms).
STATUS_DISPLAY_LABELS: dict[str, str] = {
    'pending': 'Pending',
    'in_progress': 'In Progress',
    'submitted': 'Submitted',
    'approved': 'Approved',
    'requires_revision': 'Requires Revision',
    'rejected': 'Rejected',
    'reviewed': 'Under Review',
    'implemented': 'Implemented',
    'closed': 'Closed',
}


def status_display_label(value: str | enum.Enum | None) -> str:
    """Return a Title Case label for a canonical snake_case status value."""
    if value is None:
        return ''
    if hasattr(value, 'value'):
        value = value.value
    key = str(value).strip().casefold().replace(' ', '_')
    legacy = {
        'pendingreview': 'pending',
        'underreview': 'reviewed',
        'inprogress': 'in_progress',
        'requiresrevision': 'requires_revision',
    }
    key = legacy.get(key, key)
    return STATUS_DISPLAY_LABELS.get(key, str(value).replace('_', ' ').title())


def _normalize_str_enum(
    enum_cls,
    raw: str | None,
    *,
    legacy_map: dict[str, enum.Enum] | None = None,
    default=None,
):
    default_member = default or next(iter(enum_cls))
    s = (raw or '').strip()
    if not s:
        return default_member
    low = s.casefold()
    if legacy_map and low in legacy_map:
        return legacy_map[low]
    for member in enum_cls:
        if member.value.casefold() == low:
            return member
        if member.name.casefold() == low:
            return member
    return default_member


class PublicSubmissionStatus(str, enum.Enum):
    pending = 'pending'
    approved = 'approved'
    rejected = 'rejected'

    @classmethod
    def normalize(cls, raw: str | None) -> 'PublicSubmissionStatus':
        return _normalize_str_enum(cls, raw, default=cls.pending)


class AssignmentEntityStatusValue(str, enum.Enum):
    """Canonical workflow statuses for ``assignment_entity_status.status`` (PostgreSQL enum)."""

    pending = 'pending'
    in_progress = 'in_progress'
    submitted = 'submitted'
    approved = 'approved'
    requires_revision = 'requires_revision'

    @classmethod
    def choices(cls) -> list[tuple[str, str]]:
        return [(member.value, status_display_label(member.value)) for member in cls]

    @classmethod
    def values(cls) -> tuple[str, ...]:
        return tuple(member.value for member in cls)

    @classmethod
    def normalize(cls, raw: str | None) -> 'AssignmentEntityStatusValue':
        return _normalize_str_enum(
            cls,
            raw,
            legacy_map={
                'assigned': cls.pending,
                'completed': cls.approved,
                'in progress': cls.in_progress,
                'requires revision': cls.requires_revision,
            },
            default=cls.pending,
        )


class DocumentStatusValue(str, enum.Enum):
    pending = 'pending'
    approved = 'approved'
    rejected = 'rejected'

    @classmethod
    def choices(cls) -> list[tuple[str, str]]:
        return [(member.value, status_display_label(member.value)) for member in cls]

    @classmethod
    def values(cls) -> tuple[str, ...]:
        return tuple(member.value for member in cls)

    @classmethod
    def normalize(cls, raw: str | None) -> 'DocumentStatusValue':
        return _normalize_str_enum(cls, raw, default=cls.pending)


class DocumentStatus:
    """Backward-compatible constants for ``SubmittedDocument.status``."""

    PENDING = DocumentStatusValue.pending.value
    APPROVED = DocumentStatusValue.approved.value
    REJECTED = DocumentStatusValue.rejected.value
    ALL = (PENDING, APPROVED, REJECTED)

    @classmethod
    def normalize(cls, raw: str | None) -> str:
        return DocumentStatusValue.normalize(raw).value


class CountryAccessRequestStatusValue(str, enum.Enum):
    pending = 'pending'
    approved = 'approved'
    rejected = 'rejected'

    @classmethod
    def values(cls) -> tuple[str, ...]:
        return tuple(member.value for member in cls)

    @classmethod
    def normalize(cls, raw: str | None) -> 'CountryAccessRequestStatusValue':
        return _normalize_str_enum(cls, raw)


class CountryAccessRequestStatus:
    """Backward-compatible constants for ``country_access_request.status``."""

    PENDING = CountryAccessRequestStatusValue.pending.value
    APPROVED = CountryAccessRequestStatusValue.approved.value
    REJECTED = CountryAccessRequestStatusValue.rejected.value


class FormTemplateVersionStatusValue(str, enum.Enum):
    draft = 'draft'
    published = 'published'
    archived = 'archived'

    @classmethod
    def values(cls) -> tuple[str, ...]:
        return tuple(member.value for member in cls)

    @classmethod
    def normalize(cls, raw: str | None) -> 'FormTemplateVersionStatusValue':
        return _normalize_str_enum(cls, raw)


class IndicatorSuggestionStatusValue(str, enum.Enum):
    pending = 'pending'
    reviewed = 'reviewed'
    approved = 'approved'
    rejected = 'rejected'
    implemented = 'implemented'

    @classmethod
    def values(cls) -> tuple[str, ...]:
        return tuple(member.value for member in cls)

    @classmethod
    def normalize(cls, raw: str | None) -> 'IndicatorSuggestionStatusValue':
        return _normalize_str_enum(
            cls,
            raw,
            legacy_map={
                'pending review': cls.pending,
            },
            default=cls.pending,
        )


class IndicatorSuggestionTypeValue(str, enum.Enum):
    correction = 'correction'
    improvement = 'improvement'
    new_indicator = 'new_indicator'
    other = 'other'

    @classmethod
    def values(cls) -> tuple[str, ...]:
        return tuple(member.value for member in cls)

    @classmethod
    def normalize(cls, raw: str | None) -> 'IndicatorSuggestionTypeValue':
        return _normalize_str_enum(cls, raw)


class NotificationCampaignStatusValue(str, enum.Enum):
    draft = 'draft'
    scheduled = 'scheduled'
    sent = 'sent'
    failed = 'failed'
    cancelled = 'cancelled'

    @classmethod
    def values(cls) -> tuple[str, ...]:
        return tuple(member.value for member in cls)

    @classmethod
    def normalize(cls, raw: str | None) -> 'NotificationCampaignStatusValue':
        return _normalize_str_enum(cls, raw)


class EmailDeliveryStatusValue(str, enum.Enum):
    pending = 'pending'
    sent = 'sent'
    failed = 'failed'
    retrying = 'retrying'

    @classmethod
    def values(cls) -> tuple[str, ...]:
        return tuple(member.value for member in cls)

    @classmethod
    def normalize(cls, raw: str | None) -> 'EmailDeliveryStatusValue':
        return _normalize_str_enum(cls, raw)


class AIJobStatusValue(str, enum.Enum):
    queued = 'queued'
    running = 'running'
    completed = 'completed'
    failed = 'failed'
    cancel_requested = 'cancel_requested'
    cancelled = 'cancelled'

    @classmethod
    def values(cls) -> tuple[str, ...]:
        return tuple(member.value for member in cls)

    @classmethod
    def normalize(cls, raw: str | None) -> 'AIJobStatusValue':
        return _normalize_str_enum(cls, raw)


class AIJobItemStatusValue(str, enum.Enum):
    queued = 'queued'
    downloading = 'downloading'
    processing = 'processing'
    completed = 'completed'
    failed = 'failed'
    cancelled = 'cancelled'

    @classmethod
    def values(cls) -> tuple[str, ...]:
        return tuple(member.value for member in cls)

    @classmethod
    def normalize(cls, raw: str | None) -> 'AIJobItemStatusValue':
        return _normalize_str_enum(cls, raw)


class AIDocumentProcessingStatusValue(str, enum.Enum):
    pending = 'pending'
    processing = 'processing'
    completed = 'completed'
    failed = 'failed'

    @classmethod
    def values(cls) -> tuple[str, ...]:
        return tuple(member.value for member in cls)

    @classmethod
    def normalize(cls, raw: str | None) -> 'AIDocumentProcessingStatusValue':
        return _normalize_str_enum(cls, raw)


class AIReasoningTraceStatusValue(str, enum.Enum):
    completed = 'completed'
    timeout = 'timeout'
    error = 'error'
    cost_limit_exceeded = 'cost_limit_exceeded'
    max_iterations_exceeded = 'max_iterations_exceeded'

    @classmethod
    def values(cls) -> tuple[str, ...]:
        return tuple(member.value for member in cls)

    @classmethod
    def normalize(cls, raw: str | None) -> 'AIReasoningTraceStatusValue':
        return _normalize_str_enum(cls, raw)


class AITraceReviewStatusValue(str, enum.Enum):
    pending = 'pending'
    in_review = 'in_review'
    completed = 'completed'
    dismissed = 'dismissed'

    @classmethod
    def values(cls) -> tuple[str, ...]:
        return tuple(member.value for member in cls)

    @classmethod
    def normalize(cls, raw: str | None) -> 'AITraceReviewStatusValue':
        return _normalize_str_enum(cls, raw)


class AITraceReviewVerdictValue(str, enum.Enum):
    correct = 'correct'
    partially_correct = 'partially_correct'
    incorrect = 'incorrect'
    needs_improvement = 'needs_improvement'

    @classmethod
    def values(cls) -> tuple[str, ...]:
        return tuple(member.value for member in cls)

    @classmethod
    def normalize(cls, raw: str | None | enum.Enum) -> 'AITraceReviewVerdictValue | None':
        if raw is None or raw == '':
            return None
        if isinstance(raw, AITraceReviewVerdictValue):
            return raw
        return _normalize_str_enum(cls, str(raw))


class AIFormDataValidationStatusValue(str, enum.Enum):
    completed = 'completed'
    failed = 'failed'
    pending = 'pending'

    @classmethod
    def values(cls) -> tuple[str, ...]:
        return tuple(member.value for member in cls)

    @classmethod
    def normalize(cls, raw: str | None) -> 'AIFormDataValidationStatusValue':
        return _normalize_str_enum(cls, raw)


class AIFormDataValidationVerdictValue(str, enum.Enum):
    good = 'good'
    discrepancy = 'discrepancy'
    uncertain = 'uncertain'

    @classmethod
    def values(cls) -> tuple[str, ...]:
        return tuple(member.value for member in cls)

    @classmethod
    def normalize(cls, raw: str | None | enum.Enum) -> 'AIFormDataValidationVerdictValue | None':
        if raw is None or raw == '':
            return None
        if isinstance(raw, AIFormDataValidationVerdictValue):
            return raw
        return _normalize_str_enum(cls, str(raw))


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
