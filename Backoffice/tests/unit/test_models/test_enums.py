"""
Unit tests for enums.py to achieve 100% code coverage.

Covers all enum classes, status_display_label, _normalize_str_enum,
and all .normalize(), .values(), .choices() class methods.
"""
import pytest
import enum

from app.models.enums import (
    STATUS_DISPLAY_LABELS,
    status_display_label,
    _normalize_str_enum,
    PublicSubmissionStatus,
    AssignmentEntityStatusValue,
    DocumentStatusValue,
    DocumentStatus,
    CountryAccessRequestStatusValue,
    CountryAccessRequestStatus,
    FormTemplateVersionStatusValue,
    IndicatorSuggestionStatusValue,
    IndicatorSuggestionTypeValue,
    NotificationCampaignStatusValue,
    EmailDeliveryStatusValue,
    AIJobStatusValue,
    AIJobItemStatusValue,
    AIDocumentProcessingStatusValue,
    AIReasoningTraceStatusValue,
    AITraceReviewStatusValue,
    AITraceReviewVerdictValue,
    AIFormDataValidationStatusValue,
    AIFormDataValidationVerdictValue,
    QuestionType,
    SectionType,
    FormItemType,
    EntityType,
    NotificationType,
)


@pytest.mark.unit
class TestStatusDisplayLabel:
    """Tests for status_display_label function."""

    def test_none_returns_empty_string(self):
        """None input returns empty string."""
        assert status_display_label(None) == ''

    def test_known_status_pending(self):
        """'pending' returns 'Pending'."""
        assert status_display_label('pending') == 'Pending'

    def test_known_status_in_progress(self):
        """'in_progress' returns 'In Progress'."""
        assert status_display_label('in_progress') == 'In Progress'

    def test_known_status_submitted(self):
        """'submitted' returns 'Submitted'."""
        assert status_display_label('submitted') == 'Submitted'

    def test_known_status_approved(self):
        """'approved' returns 'Approved'."""
        assert status_display_label('approved') == 'Approved'

    def test_known_status_requires_revision(self):
        """'requires_revision' returns 'Requires Revision'."""
        assert status_display_label('requires_revision') == 'Requires Revision'

    def test_known_status_sent_for_review(self):
        """'sent_for_review' returns 'Sent for Review'."""
        assert status_display_label('sent_for_review') == 'Sent for Review'

    def test_known_status_rejected(self):
        """'rejected' returns 'Rejected'."""
        assert status_display_label('rejected') == 'Rejected'

    def test_known_status_reviewed(self):
        """'reviewed' returns 'Under Review'."""
        assert status_display_label('reviewed') == 'Under Review'

    def test_known_status_implemented(self):
        """'implemented' returns 'Implemented'."""
        assert status_display_label('implemented') == 'Implemented'

    def test_known_status_closed(self):
        """'closed' returns 'Closed'."""
        assert status_display_label('closed') == 'Closed'

    def test_legacy_pendingReview(self):
        """'pendingReview' (legacy) maps to 'Pending'."""
        assert status_display_label('pendingReview') == 'Pending'

    def test_legacy_underReview(self):
        """'underReview' (legacy) maps to 'Under Review'."""
        assert status_display_label('underReview') == 'Under Review'

    def test_legacy_inprogress(self):
        """'inprogress' (legacy) maps to 'In Progress'."""
        assert status_display_label('inprogress') == 'In Progress'

    def test_legacy_requiresrevision(self):
        """'requiresrevision' (legacy) maps to 'Requires Revision'."""
        assert status_display_label('requiresrevision') == 'Requires Revision'

    def test_unknown_status_title_cased(self):
        """Unknown status is title-cased."""
        result = status_display_label('some_custom_status')
        assert result == 'Some Custom Status'

    def test_enum_member_uses_value(self):
        """Enum member with .value attribute uses its value."""
        result = status_display_label(AssignmentEntityStatusValue.in_progress)
        assert result == 'In Progress'

    def test_uppercase_input_normalized(self):
        """Input is case-folded before lookup."""
        assert status_display_label('PENDING') == 'Pending'


@pytest.mark.unit
class TestNormalizeStrEnum:
    """Tests for _normalize_str_enum function."""

    def test_empty_string_returns_default(self):
        """Empty string returns the default member."""
        result = _normalize_str_enum(PublicSubmissionStatus, '')
        assert result == PublicSubmissionStatus.pending

    def test_none_returns_default(self):
        """None returns the default member."""
        result = _normalize_str_enum(PublicSubmissionStatus, None)
        assert result == PublicSubmissionStatus.pending

    def test_exact_match_by_value(self):
        """Exact value match returns the member."""
        result = _normalize_str_enum(PublicSubmissionStatus, 'approved')
        assert result == PublicSubmissionStatus.approved

    def test_case_insensitive_match(self):
        """Case-insensitive value match works."""
        result = _normalize_str_enum(PublicSubmissionStatus, 'APPROVED')
        assert result == PublicSubmissionStatus.approved

    def test_match_by_name(self):
        """Match by enum name works."""
        result = _normalize_str_enum(PublicSubmissionStatus, 'rejected')
        assert result == PublicSubmissionStatus.rejected

    def test_legacy_map_hit(self):
        """Legacy map entry is used when key matches."""
        legacy = {'old_status': AssignmentEntityStatusValue.pending}
        result = _normalize_str_enum(
            AssignmentEntityStatusValue, 'old_status', legacy_map=legacy
        )
        assert result == AssignmentEntityStatusValue.pending

    def test_unrecognized_returns_default(self):
        """Unrecognized value returns default member."""
        result = _normalize_str_enum(PublicSubmissionStatus, 'unknown_value')
        assert result == PublicSubmissionStatus.pending

    def test_explicit_default_member(self):
        """Explicit default parameter is used."""
        result = _normalize_str_enum(
            PublicSubmissionStatus, 'unknown', default=PublicSubmissionStatus.rejected
        )
        assert result == PublicSubmissionStatus.rejected


@pytest.mark.unit
class TestPublicSubmissionStatus:
    """Tests for PublicSubmissionStatus enum."""

    def test_values(self):
        """Enum has expected values."""
        assert PublicSubmissionStatus.pending.value == 'pending'
        assert PublicSubmissionStatus.approved.value == 'approved'
        assert PublicSubmissionStatus.rejected.value == 'rejected'

    def test_normalize_valid(self):
        """normalize returns correct member for valid input."""
        assert PublicSubmissionStatus.normalize('approved') == PublicSubmissionStatus.approved

    def test_normalize_none(self):
        """normalize returns default for None."""
        assert PublicSubmissionStatus.normalize(None) == PublicSubmissionStatus.pending


@pytest.mark.unit
class TestAssignmentEntityStatusValue:
    """Tests for AssignmentEntityStatusValue enum."""

    def test_all_values(self):
        """values() returns all enum values."""
        vals = AssignmentEntityStatusValue.values()
        assert 'pending' in vals
        assert 'in_progress' in vals
        assert 'submitted' in vals
        assert 'approved' in vals
        assert 'requires_revision' in vals
        assert 'sent_for_review' in vals

    def test_choices_order(self):
        """choices() preserves workflow order."""
        choices = AssignmentEntityStatusValue.choices()
        values = [c[0] for c in choices]
        assert values.index('pending') < values.index('submitted')

    def test_choices_labels(self):
        """choices() returns (value, label) tuples."""
        for val, label in AssignmentEntityStatusValue.choices():
            assert isinstance(val, str)
            assert isinstance(label, str)
            assert len(label) > 0

    def test_normalize_valid(self):
        """normalize returns correct member for valid input."""
        result = AssignmentEntityStatusValue.normalize('submitted')
        assert result == AssignmentEntityStatusValue.submitted

    def test_normalize_legacy_assigned(self):
        """normalize maps legacy 'assigned' to pending."""
        result = AssignmentEntityStatusValue.normalize('assigned')
        assert result == AssignmentEntityStatusValue.pending

    def test_normalize_legacy_completed(self):
        """normalize maps legacy 'completed' to approved."""
        result = AssignmentEntityStatusValue.normalize('completed')
        assert result == AssignmentEntityStatusValue.approved

    def test_normalize_legacy_in_progress_with_space(self):
        """normalize maps 'in progress' (with space) to in_progress."""
        result = AssignmentEntityStatusValue.normalize('in progress')
        assert result == AssignmentEntityStatusValue.in_progress

    def test_normalize_legacy_requires_revision_with_space(self):
        """normalize maps 'requires revision' to requires_revision."""
        result = AssignmentEntityStatusValue.normalize('requires revision')
        assert result == AssignmentEntityStatusValue.requires_revision

    def test_normalize_legacy_send_for_review(self):
        """normalize maps 'send for review' to sent_for_review."""
        result = AssignmentEntityStatusValue.normalize('send for review')
        assert result == AssignmentEntityStatusValue.sent_for_review

    def test_normalize_none(self):
        """normalize None returns pending."""
        assert AssignmentEntityStatusValue.normalize(None) == AssignmentEntityStatusValue.pending

    def test_choices_includes_extra_members(self):
        """choices() includes members not in workflow order list."""
        # All members should appear in choices
        choice_values = [c[0] for c in AssignmentEntityStatusValue.choices()]
        for member in AssignmentEntityStatusValue:
            assert member.value in choice_values


@pytest.mark.unit
class TestDocumentStatusValue:
    """Tests for DocumentStatusValue enum."""

    def test_values(self):
        """values() returns all values."""
        vals = DocumentStatusValue.values()
        assert 'pending' in vals
        assert 'approved' in vals
        assert 'rejected' in vals

    def test_choices(self):
        """choices() returns list of (value, label) tuples."""
        choices = DocumentStatusValue.choices()
        assert len(choices) == 3
        for val, label in choices:
            assert isinstance(val, str)
            assert isinstance(label, str)

    def test_normalize(self):
        """normalize returns correct member."""
        assert DocumentStatusValue.normalize('approved') == DocumentStatusValue.approved

    def test_normalize_none(self):
        """normalize None returns pending."""
        assert DocumentStatusValue.normalize(None) == DocumentStatusValue.pending


@pytest.mark.unit
class TestDocumentStatus:
    """Tests for DocumentStatus backward-compat class."""

    def test_constants(self):
        """Constants match DocumentStatusValue."""
        assert DocumentStatus.PENDING == 'pending'
        assert DocumentStatus.APPROVED == 'approved'
        assert DocumentStatus.REJECTED == 'rejected'

    def test_all_constant(self):
        """ALL contains all three status strings."""
        assert len(DocumentStatus.ALL) == 3

    def test_normalize(self):
        """normalize returns string value."""
        result = DocumentStatus.normalize('approved')
        assert result == 'approved'


@pytest.mark.unit
class TestCountryAccessRequestStatusValue:
    """Tests for CountryAccessRequestStatusValue enum."""

    def test_values(self):
        """values() returns all values."""
        vals = CountryAccessRequestStatusValue.values()
        assert 'pending' in vals
        assert 'approved' in vals
        assert 'rejected' in vals

    def test_normalize(self):
        """normalize returns correct member."""
        result = CountryAccessRequestStatusValue.normalize('approved')
        assert result == CountryAccessRequestStatusValue.approved


@pytest.mark.unit
class TestCountryAccessRequestStatus:
    """Tests for CountryAccessRequestStatus backward-compat class."""

    def test_constants(self):
        assert CountryAccessRequestStatus.PENDING == 'pending'
        assert CountryAccessRequestStatus.APPROVED == 'approved'
        assert CountryAccessRequestStatus.REJECTED == 'rejected'


@pytest.mark.unit
class TestFormTemplateVersionStatusValue:
    """Tests for FormTemplateVersionStatusValue enum."""

    def test_values(self):
        vals = FormTemplateVersionStatusValue.values()
        assert 'draft' in vals
        assert 'published' in vals
        assert 'archived' in vals

    def test_normalize(self):
        result = FormTemplateVersionStatusValue.normalize('published')
        assert result == FormTemplateVersionStatusValue.published


@pytest.mark.unit
class TestIndicatorSuggestionStatusValue:
    """Tests for IndicatorSuggestionStatusValue enum."""

    def test_values(self):
        vals = IndicatorSuggestionStatusValue.values()
        assert 'pending' in vals
        assert 'reviewed' in vals
        assert 'approved' in vals
        assert 'rejected' in vals
        assert 'implemented' in vals

    def test_normalize(self):
        result = IndicatorSuggestionStatusValue.normalize('approved')
        assert result == IndicatorSuggestionStatusValue.approved

    def test_normalize_legacy_pending_review(self):
        """Legacy 'pending review' maps to pending."""
        result = IndicatorSuggestionStatusValue.normalize('pending review')
        assert result == IndicatorSuggestionStatusValue.pending


@pytest.mark.unit
class TestIndicatorSuggestionTypeValue:
    """Tests for IndicatorSuggestionTypeValue enum."""

    def test_values(self):
        vals = IndicatorSuggestionTypeValue.values()
        assert 'correction' in vals
        assert 'improvement' in vals
        assert 'new_indicator' in vals
        assert 'other' in vals

    def test_normalize(self):
        result = IndicatorSuggestionTypeValue.normalize('correction')
        assert result == IndicatorSuggestionTypeValue.correction


@pytest.mark.unit
class TestNotificationCampaignStatusValue:
    """Tests for NotificationCampaignStatusValue enum."""

    def test_values(self):
        vals = NotificationCampaignStatusValue.values()
        assert 'draft' in vals
        assert 'scheduled' in vals
        assert 'sent' in vals
        assert 'failed' in vals
        assert 'cancelled' in vals

    def test_normalize(self):
        result = NotificationCampaignStatusValue.normalize('sent')
        assert result == NotificationCampaignStatusValue.sent


@pytest.mark.unit
class TestEmailDeliveryStatusValue:
    """Tests for EmailDeliveryStatusValue enum."""

    def test_values(self):
        vals = EmailDeliveryStatusValue.values()
        assert 'pending' in vals
        assert 'sent' in vals
        assert 'failed' in vals
        assert 'retrying' in vals

    def test_normalize(self):
        result = EmailDeliveryStatusValue.normalize('failed')
        assert result == EmailDeliveryStatusValue.failed


@pytest.mark.unit
class TestAIJobStatusValue:
    """Tests for AIJobStatusValue enum."""

    def test_values(self):
        vals = AIJobStatusValue.values()
        assert 'queued' in vals
        assert 'running' in vals
        assert 'completed' in vals
        assert 'failed' in vals
        assert 'cancel_requested' in vals
        assert 'cancelled' in vals

    def test_normalize(self):
        result = AIJobStatusValue.normalize('completed')
        assert result == AIJobStatusValue.completed


@pytest.mark.unit
class TestAIJobItemStatusValue:
    """Tests for AIJobItemStatusValue enum."""

    def test_values(self):
        vals = AIJobItemStatusValue.values()
        assert 'queued' in vals
        assert 'downloading' in vals
        assert 'processing' in vals
        assert 'completed' in vals
        assert 'failed' in vals
        assert 'cancelled' in vals

    def test_normalize(self):
        result = AIJobItemStatusValue.normalize('processing')
        assert result == AIJobItemStatusValue.processing


@pytest.mark.unit
class TestAIDocumentProcessingStatusValue:
    """Tests for AIDocumentProcessingStatusValue enum."""

    def test_values(self):
        vals = AIDocumentProcessingStatusValue.values()
        assert 'pending' in vals
        assert 'processing' in vals
        assert 'completed' in vals
        assert 'failed' in vals

    def test_normalize(self):
        result = AIDocumentProcessingStatusValue.normalize('completed')
        assert result == AIDocumentProcessingStatusValue.completed


@pytest.mark.unit
class TestAIReasoningTraceStatusValue:
    """Tests for AIReasoningTraceStatusValue enum."""

    def test_values(self):
        vals = AIReasoningTraceStatusValue.values()
        assert 'running' in vals
        assert 'completed' in vals
        assert 'timeout' in vals
        assert 'error' in vals
        assert 'cost_limit_exceeded' in vals
        assert 'max_iterations_exceeded' in vals

    def test_normalize(self):
        result = AIReasoningTraceStatusValue.normalize('error')
        assert result == AIReasoningTraceStatusValue.error


@pytest.mark.unit
class TestAITraceReviewStatusValue:
    """Tests for AITraceReviewStatusValue enum."""

    def test_values(self):
        vals = AITraceReviewStatusValue.values()
        assert 'pending' in vals
        assert 'in_review' in vals
        assert 'completed' in vals
        assert 'dismissed' in vals

    def test_normalize(self):
        result = AITraceReviewStatusValue.normalize('in_review')
        assert result == AITraceReviewStatusValue.in_review


@pytest.mark.unit
class TestAITraceReviewVerdictValue:
    """Tests for AITraceReviewVerdictValue enum."""

    def test_values(self):
        vals = AITraceReviewVerdictValue.values()
        assert 'correct' in vals
        assert 'partially_correct' in vals
        assert 'incorrect' in vals
        assert 'needs_improvement' in vals

    def test_normalize_valid(self):
        result = AITraceReviewVerdictValue.normalize('correct')
        assert result == AITraceReviewVerdictValue.correct

    def test_normalize_none(self):
        """normalize None returns None."""
        result = AITraceReviewVerdictValue.normalize(None)
        assert result is None

    def test_normalize_empty_string(self):
        """normalize empty string returns None."""
        result = AITraceReviewVerdictValue.normalize('')
        assert result is None

    def test_normalize_enum_instance(self):
        """normalize existing enum instance returns same."""
        result = AITraceReviewVerdictValue.normalize(AITraceReviewVerdictValue.correct)
        assert result == AITraceReviewVerdictValue.correct

    def test_normalize_string_value(self):
        """normalize string converts via _normalize_str_enum."""
        result = AITraceReviewVerdictValue.normalize('incorrect')
        assert result == AITraceReviewVerdictValue.incorrect


@pytest.mark.unit
class TestAIFormDataValidationStatusValue:
    """Tests for AIFormDataValidationStatusValue enum."""

    def test_values(self):
        vals = AIFormDataValidationStatusValue.values()
        assert 'completed' in vals
        assert 'failed' in vals
        assert 'pending' in vals

    def test_normalize(self):
        result = AIFormDataValidationStatusValue.normalize('failed')
        assert result == AIFormDataValidationStatusValue.failed


@pytest.mark.unit
class TestAIFormDataValidationVerdictValue:
    """Tests for AIFormDataValidationVerdictValue enum."""

    def test_values(self):
        vals = AIFormDataValidationVerdictValue.values()
        assert 'good' in vals
        assert 'discrepancy' in vals
        assert 'uncertain' in vals

    def test_normalize_valid(self):
        result = AIFormDataValidationVerdictValue.normalize('good')
        assert result == AIFormDataValidationVerdictValue.good

    def test_normalize_none(self):
        result = AIFormDataValidationVerdictValue.normalize(None)
        assert result is None

    def test_normalize_empty_string(self):
        result = AIFormDataValidationVerdictValue.normalize('')
        assert result is None

    def test_normalize_enum_instance(self):
        result = AIFormDataValidationVerdictValue.normalize(AIFormDataValidationVerdictValue.good)
        assert result == AIFormDataValidationVerdictValue.good

    def test_normalize_string(self):
        result = AIFormDataValidationVerdictValue.normalize('discrepancy')
        assert result == AIFormDataValidationVerdictValue.discrepancy


@pytest.mark.unit
class TestQuestionType:
    """Tests for QuestionType enum."""

    def test_members(self):
        """All expected members exist."""
        assert QuestionType.text.value == 'text'
        assert QuestionType.number.value == 'number'
        assert QuestionType.percentage.value == 'percentage'
        assert QuestionType.yesno.value == 'yesno'
        assert QuestionType.single_choice.value == 'single_choice'
        assert QuestionType.multiple_choice.value == 'multiple_choice'
        assert QuestionType.date.value == 'date'
        assert QuestionType.datetime.value == 'datetime'
        assert QuestionType.blank.value == 'blank'


@pytest.mark.unit
class TestSectionType:
    """Tests for SectionType enum."""

    def test_members(self):
        assert SectionType.standard.value == 'Standard'
        assert SectionType.dynamic_indicators.value == 'Dynamic Indicators'
        assert SectionType.repeat.value == 'Repeat'


@pytest.mark.unit
class TestFormItemType:
    """Tests for FormItemType enum."""

    def test_members(self):
        assert FormItemType.indicator.value == 'indicator'
        assert FormItemType.question.value == 'question'
        assert FormItemType.document_field.value == 'document_field'


@pytest.mark.unit
class TestEntityType:
    """Tests for EntityType enum."""

    def test_members(self):
        assert EntityType.country.value == 'country'
        assert EntityType.national_society.value == 'national_society'
        assert EntityType.ns_branch.value == 'ns_branch'
        assert EntityType.ns_subbranch.value == 'ns_subbranch'
        assert EntityType.ns_localunit.value == 'ns_localunit'
        assert EntityType.division.value == 'division'
        assert EntityType.department.value == 'department'
        assert EntityType.regional_office.value == 'regional_office'
        assert EntityType.cluster_office.value == 'cluster_office'

    def test_is_str_enum(self):
        """EntityType is a str enum (can compare to strings)."""
        assert EntityType.country == 'country'


@pytest.mark.unit
class TestNotificationType:
    """Tests for NotificationType enum."""

    def test_members(self):
        assert NotificationType.assignment_created.value == 'assignment_created'
        assert NotificationType.assignment_submitted.value == 'assignment_submitted'
        assert NotificationType.assignment_approved.value == 'assignment_approved'
        assert NotificationType.admin_message.value == 'admin_message'
        assert NotificationType.access_request_received.value == 'access_request_received'
        assert NotificationType.validation_questions.value == 'validation_questions'
